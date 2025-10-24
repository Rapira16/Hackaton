import threading, time, json
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models import TransactionDB, RuleDB
from rules_engine import threshold_rule, pattern_rule, composite_rule, ml_rule
from notifications import send_telegram_alert, send_email_alert
from logger import log_event

queue = []  # глобальная очередь транзакций


class Transaction:
    def __init__(self, sender_account, receiver_account, amount, transaction_type, correlation_id=None):
        import uuid
        self.correlation_id = correlation_id if correlation_id else str(uuid.uuid4())
        self.sender_account = sender_account
        self.receiver_account = receiver_account
        self.amount = amount
        self.transaction_type = transaction_type
        self.timestamp = datetime.utcnow()
        self.status = "processed"  # по умолчанию processed
        self.alerts = []


def process_transaction(tx: Transaction):
    """
    Обрабатывает транзакцию:
    - применяет все включенные правила,
    - обновляет статус и alerts,
    - сохраняет изменения в БД,
    - отправляет уведомление Telegram, если нужно.
    """
    session = SessionLocal()
    try:
        # Получаем существующую запись (статус queued)
        tx_record = session.query(TransactionDB).filter(
            TransactionDB.correlation_id == tx.correlation_id
        ).first()

        if not tx_record:
            log_event("tx_not_found_in_db", tx, component="queue", extra={"level": "ERROR"})
            return

        # Получаем правила
        db_rules = session.query(RuleDB).filter(RuleDB.enabled == True).all()
        # История всех транзакций для pattern/composite
        history_transactions = session.query(TransactionDB).all()
        alerts = []

        # Применяем правила
        for rule in db_rules:
            try:
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
            except Exception as rule_error:
                log_event("rule_error", tx, component="queue",
                          extra={"error": str(rule_error), "rule_id": rule.id, "level": "ERROR"})
                continue

        tx.alerts = alerts
        tx.status = "alerted" if alerts else "processed"

        # Обновляем существующую запись
        tx_record.status = tx.status
        tx_record.alerts = "; ".join(tx.alerts)
        session.commit()
        log_event("db_commit", tx, component="queue")

        # Отправка уведомлений
        for reason in alerts:
            send_telegram_alert(tx, reason)
            send_email_alert(tx, reason)

    except IntegrityError as e:
        session.rollback()
        # Более детальная обработка IntegrityError
        error_msg = str(e).lower()
        if "unique" in error_msg and "correlation_id" in error_msg:
            log_event("duplicate_constraint_violation", tx, component="queue",
                      extra={"error": str(e), "level": "WARN", "reason": "duplicate_correlation_id_constraint"})
        else:
            log_event("integrity_error", tx, component="queue",
                      extra={"error": str(e), "level": "ERROR", "reason": "database_constraint_violation"})
    except Exception as e:
        session.rollback()
        log_event("db_error", tx, component="queue",
                  extra={"error": str(e), "level": "ERROR", "reason": "unexpected_error"})
    finally:
        session.close()


def worker():
    """
    Постоянный поток обработки транзакций из очереди.
    """
    while True:
        if queue:
            tx = queue.pop(0)
            log_event("start_processing", tx, component="queue")
            process_transaction(tx)
        time.sleep(0.1)


# Запуск worker в отдельном потоке
threading.Thread(target=worker, daemon=True).start()
