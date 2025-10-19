import requests

def send_telegram_alert(tx, reason):
    bot_token = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
    chat_id = "1600738086"
    msg = f"ALERT: {tx.correlation_id}\nSender: {tx.sender_account}\nAmount: {tx.amount}\nReason: {reason}"
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                      data={"chat_id": chat_id, "text": msg})
    except Exception as e:
        print("Telegram error:", e)
