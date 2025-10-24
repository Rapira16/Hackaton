# notifications.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests, time
from logger import log_event

# -------------------- Настройки Telegram --------------------
TELEGRAM_BOT_TOKEN = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
TELEGRAM_CHAT_ID = "1600738086"
sent_telegram_alerts = set()

def send_telegram_alert(tx, reason="New transaction received", retries=3):
    if tx.correlation_id in sent_telegram_alerts:
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
                sent_telegram_alerts.add(tx.correlation_id)
                log_event("notify_sent", tx, component="notify", extra={"channel": "telegram"})
                return
            else:
                log_event("notify_retry", tx, component="notify", extra={"attempt": attempt, "status_code": r.status_code})
        except Exception as e:
            log_event("notify_error", tx, component="notify", extra={"attempt": attempt, "error": str(e), "level": "ERROR"})
        time.sleep(1)


# -------------------- Настройки Email --------------------
EMAIL_HOST = "smtp.mail.ru"
EMAIL_PORT = 587
EMAIL_USER = "bot_hackaton@mail.ru"
EMAIL_PASSWORD = "lxHGo5vvjWpooIpy6GSy"  # App Password

SENDER_EMAIL = "bot_hackaton@mail.ru"
RECIPIENT_EMAIL = "dmitrijsuhanov713@gmail.com"

sent_email_alerts = set()

def send_email_alert(tx, reason="New transaction received", retries=3):
    global sent_email_alerts
    if tx.correlation_id in sent_email_alerts:
        log_event("notify_skipped", tx, component="notify", extra={"reason": "duplicate"})
        return

    subject = "🚨 Transaction Alert!"
    body = (
        f"Transaction Alert!\n"
        f"ID: {tx.correlation_id}\n"
        f"Sender: {tx.sender_account}\n"
        f"Receiver: {tx.receiver_account}\n"
        f"Amount: {tx.amount}\n"
        f"Type: {tx.transaction_type}\n"
        f"Reason: {reason}"
    )

    html_body = f"""
    <html>
      <head>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 20px; }}
          .alert {{ color: #d63031; font-weight: bold; font-size: 18px; }}
          .info {{ margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 4px solid #74b9ff; }}
          .label {{ font-weight: bold; color: #2d3436; }}
        </style>
      </head>
      <body>
        <div class="alert">🚨 Transaction Alert!</div>
        <div class="info">
          <p><span class="label">ID:</span> {tx.correlation_id}</p>
          <p><span class="label">Sender:</span> {tx.sender_account}</p>
          <p><span class="label">Receiver:</span> {tx.receiver_account}</p>
          <p><span class="label">Amount:</span> {tx.amount}</p>
          <p><span class="label">Type:</span> {tx.transaction_type}</p>
          <p><span class="label">Reason:</span> {reason}</p>
          <p><span class="label">Time:</span> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
      </body>
    </html>
    """

    for attempt in range(1, retries + 1):
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SENDER_EMAIL
            msg['To'] = RECIPIENT_EMAIL

            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)

            sent_email_alerts.add(tx.correlation_id)
            log_event("notify_sent", tx, component="notify", extra={"channel": "email", "recipient": RECIPIENT_EMAIL})
            return

        except Exception as e:
            log_event("notify_error", tx, component="notify", extra={"attempt": attempt, "error": str(e), "level": "ERROR"})
            if attempt < retries:
                time.sleep(2)
