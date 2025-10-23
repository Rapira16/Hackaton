import logging, json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(message)s')

def log_event(stage, tx, component="system", extra=None):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "stage": stage,
        "component": component,
        "correlation_id": getattr(tx, "correlation_id", None),
        "sender": getattr(tx, "sender_account", None),
        "receiver": getattr(tx, "receiver_account", None),
        "amount": getattr(tx, "amount", None),
        "transaction_type": getattr(tx, "transaction_type", None),
        "status": getattr(tx, "status", None),
        "alerts": getattr(tx, "alerts", None),
    }
    if extra:
        entry.update(extra)
    level = extra.get("level", "INFO") if extra else "INFO"
    if level == "INFO":
        logging.info(json.dumps(entry))
    elif level == "WARN":
        logging.warning(json.dumps(entry))
    elif level == "ERROR":
        logging.error(json.dumps(entry))
