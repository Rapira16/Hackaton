import requests, time
from logger import log_event

TELEGRAM_BOT_TOKEN = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
TELEGRAM_CHAT_ID = "1600738086"
sent_alerts = set()

def send_telegram_alert(tx, reason="New transaction received", retries=3):
    if tx.correlation_id in sent_alerts:
        log_event("notify_skipped", tx, component="notify", extra={"reason": "duplicate"})
        return
    msg = (
        f"🚨 *Transaction Alert!*\n"
        f"ID: `{tx.correlation_id}`\n"
        f"Sender: {tx.sender_account}\n"
        f"Receiver: {tx.receiver_account}\n"
        f"Amount: {tx.amount}\n"
        f"Type: {tx.transaction_type}\n"
        f"Reason: {reason}"
    )
    for attempt in range(1, retries+1):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=5
            )
            if r.status_code == 200:
                sent_alerts.add(tx.correlation_id)
                log_event("notify_sent", tx, component="notify", extra={"channel": "telegram"})
                return
            else:
                log_event("notify_retry", tx, component="notify", extra={"attempt": attempt, "status_code": r.status_code})
        except Exception as e:
            log_event("notify_error", tx, component="notify", extra={"attempt": attempt, "error": str(e), "level": "ERROR"})
        time.sleep(1)
