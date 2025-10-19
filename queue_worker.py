import threading, time
from models import transactions, rules
from rules_engine import threshold_rule, pattern_rule, composite_rule, ml_rule
from notifications import send_telegram_alert

queue = []

def process_transaction(tx):
    alerts = []
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.rule_type == "threshold":
            alert, reason = threshold_rule(tx, rule.params)
        elif rule.rule_type == "pattern":
            alert, reason = pattern_rule(tx, rule.params, transactions)
        elif rule.rule_type == "composite":
            alert, reason = composite_rule(tx, rule.params, transactions)
        elif rule.rule_type == "ml":
            alert, reason = ml_rule(tx, rule.params)
        else:
            continue
        if alert:
            alerts.append(reason)
    tx.alerts = alerts
    if alerts:
        tx.status = "alerted"
        for reason in alerts:
            send_telegram_alert(tx, reason)
    transactions.append(tx)

def worker():
    while True:
        if queue:
            tx = queue.pop(0)
            process_transaction(tx)
        time.sleep(0.1)

threading.Thread(target=worker, daemon=True).start()
