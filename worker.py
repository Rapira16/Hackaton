import threading, time, json
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models import TransactionDB, RuleDB
from rules_engine import threshold_rule, pattern_rule, composite_rule, ml_rule
from notifications import send_telegram_alert
from logger import log_event

queue = []


class Transaction:
    def __init__(self, sender_account, receiver_account, amount, transaction_type):
        import uuid
        self.correlation_id = str(uuid.uuid4())
        self.sender_account = sender_account
        self.receiver_account = receiver_account
        self.amount = amount
        self.transaction_type = transaction_type
        self.timestamp = datetime.utcnow()
        self.status = "processed"
        self.alerts = []


def process_transaction(tx):
    session = SessionLocal()
    try:
        # Проверяем дубликат еще раз на случай race condition
        existing_tx = session.query(TransactionDB).filter(
            TransactionDB.correlation_id == tx.correlation_id
        ).first()

        if existing_tx:
            log_event("duplicate_skipped", tx, component="queue",
                      extra={"level": "WARN", "reason": "duplicate_in_db"})
            return

        db_rules = session.query(RuleDB).filter(RuleDB.enabled == True).all()
        history_transactions = session.query(TransactionDB).all()
        alerts = []

        for rule in db_rules:
            params = json.loads(rule.params)
            if rule.rule_type == "threshold":
                alert, reason = threshold_rule(tx, params)
            elif rule.rule_type == "pattern":
                alert, reason = pattern_rule(tx, params, history_transactions)
            elif rule.rule_type == "composite":
                alert, reason = composite_rule(tx, params, history_transactions)
            elif rule.rule_type == "ml":
                alert, reason = ml_rule(tx, params)
            else:
                continue
            if alert:
                alerts.append(reason)

        tx.alerts = alerts
        if alerts:
            tx.status = "alerted"

        tx_record = TransactionDB(
            correlation_id=tx.correlation_id,
            sender_account=tx.sender_account,
            receiver_account=tx.receiver_account,
            amount=tx.amount,
            transaction_type=tx.transaction_type,
            timestamp=tx.timestamp,
            status=tx.status,
            alerts="; ".join(tx.alerts),
        )
        session.add(tx_record)
        session.commit()
        log_event("db_commit", tx, component="queue")

        for reason in alerts:
            send_telegram_alert(tx, reason)

    except IntegrityError as e:
        session.rollback()
        log_event("db_integrity_error", tx, component="queue",
                  extra={"error": str(e), "level": "ERROR", "reason": "duplicate_constraint"})
    except Exception as e:
        session.rollback()
        log_event("db_error", tx, component="queue",
                  extra={"error": str(e), "level": "ERROR"})
    finally:
        session.close()


def worker():
    while True:
        if queue:
            tx = queue.pop(0)
            log_event("start_processing", tx, component="queue")
            process_transaction(tx)
        time.sleep(0.1)


threading.Thread(target=worker, daemon=True).start()