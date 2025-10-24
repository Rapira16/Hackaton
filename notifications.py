import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests, time
from logger import log_event

def send_telegram_alert(tx, reason):
    bot_token = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
    chat_id = "1600738086"
    msg = f"ALERT: {tx.correlation_id}\nSender: {tx.sender_account}\nAmount: {tx.amount}\nReason: {reason}"
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                      data={"chat_id": chat_id, "text": msg})
    except Exception as e:
        print("Telegram error:", e)


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


def send_email_alert(tx, reason="New transaction received", retries=3):
    # Конфигурация SMTP сервера Mail.ru
    EMAIL_HOST = "smtp.mail.ru"  # SMTP сервер для отправки писем
    EMAIL_PORT = 587  # Порт для защищенного соединения
    EMAIL_USER = "bot_hackaton@mail.ru"  # Email отправителя (ваш аккаунт)
    EMAIL_PASSWORD = "lxHGo5vvjWpooIpy6GSy"  # Пароль приложения Mail.ru

    # Разные email адреса для отправителя и получателя:
    SENDER_EMAIL = "bot_hackaton@mail.ru"  # Email отправителя уведомлений
    RECIPIENT_EMAIL = "EnderBro_2005@mail.ru"  # Email получателя уведомлений (администратора)

    sent_alerts = set()  # Множество для отслеживания уже отправленных уведомлений

    # Проверка на дубликаты
    if tx.correlation_id in sent_alerts:
        log_event("notify_skipped", tx, component="notify", extra={"reason": "duplicate"})
        return

    # Формирование сообщения
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

    # HTML версия сообщения для лучшего форматирования
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

    # Попытки отправки с повторением при ошибках
    for attempt in range(1, retries + 1):
        try:
            # Создание MIME сообщения
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SENDER_EMAIL  # От кого письмо
            msg['To'] = RECIPIENT_EMAIL  # Кому письмо

            # Добавляем обе версии сообщения (текстовую и HTML)
            part1 = MIMEText(body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)

            # Отправка через SMTP сервер
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()  # Включаем шифрование TLS
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)

            # Отмечаем как отправленное
            sent_alerts.add(tx.correlation_id)
            log_event("notify_sent", tx, component="notify",
                      extra={"channel": "email", "recipient": RECIPIENT_EMAIL})
            return

        except Exception as e:
            log_event("notify_error", tx, component="notify",
                      extra={"attempt": attempt, "error": str(e), "level": "ERROR"})
            if attempt < retries:
                time.sleep(2)