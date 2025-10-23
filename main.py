from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Text, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import threading, time, uuid, json, uvicorn, requests


DATABASE_URL = "sqlite:///fraud_system.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class TransactionDB(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sender_account = Column(String)
    receiver_account = Column(String)
    amount = Column(Float)
    transaction_type = Column(String)
    merchant_category = Column(String, nullable=True)
    location = Column(String, nullable=True)
    device_used = Column(String, nullable=True)
    is_fraud = Column(Boolean, default=False)
    fraud_type = Column(String, nullable=True)
    time_since_last_transaction = Column(Float, nullable=True)
    spending_deviation_score = Column(Float, nullable=True)
    velocity_score = Column(Float, nullable=True)
    geo_anomaly_score = Column(Float, nullable=True)
    payment_channel = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    device_hash = Column(String, nullable=True)
    status = Column(String, default="processed")
    alerts = Column(Text, default="")

class RuleDB(Base):
    __tablename__ = "rules"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    rule_type = Column(String)
    enabled = Column(Boolean, default=True)
    params = Column(Text)


Base.metadata.create_all(bind=engine)


class TransactionIn(BaseModel):
    sender_account: str = Field(..., min_length=1)
    receiver_account: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    transaction_type: str

    @field_validator("transaction_type")
    def validate_type(cls, v):
        if v not in ["payment", "withdrawal", "transfer", "deposit"]:
            raise ValueError("transaction_type must be one of: payment, withdrawal, transfer, deposit")
        return v

class RuleIn(BaseModel):
    name: str
    rule_type: str
    value: float = 0


app = FastAPI()
templates = Jinja2Templates(directory="templates")
ALLOWED_TYPES = ["payment", "withdrawal", "transfer", "deposit"]


TELEGRAM_BOT_TOKEN = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
TELEGRAM_CHAT_ID = "1600738086"

def send_telegram_alert(tx, reason: str = "New transaction received"):
    msg = (
        f"🚨 *Transaction Alert!*\n"
        f"ID: `{tx.correlation_id}`\n"
        f"Sender: {tx.sender_account}\n"
        f"Receiver: {tx.receiver_account}\n"
        f"Amount: {tx.amount}\n"
        f"Type: {tx.transaction_type}\n"
        f"Reason: {reason}"
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        )
        if r.status_code != 200:
            print("⚠️ Telegram send error:", r.text)
        else:
            print("✅ Telegram alert sent.")
    except Exception as e:
        print("Telegram error:", e)


queue = []

class Transaction:
    def __init__(self, sender_account, receiver_account, amount, transaction_type):
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
        send_telegram_alert(tx, "Transaction added to DB")
    except Exception as e:
        session.rollback()
        print("DB error:", e)
    finally:
        session.close()

def worker():
    while True:
        if queue:
            tx = queue.pop(0)
            process_transaction(tx)
        time.sleep(0.1)

threading.Thread(target=worker, daemon=True).start()


@app.post("/transactions")
async def create_transaction(payload: TransactionIn):
    if payload.transaction_type not in ALLOWED_TYPES or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid data")

    tx = Transaction(
        sender_account=payload.sender_account,
        receiver_account=payload.receiver_account,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
    )

    queue.append(tx)
    return {"status": "queued", "correlation_id": tx.correlation_id}

@app.post("/rules/add")
async def add_rule(payload: RuleIn):
    session = SessionLocal()
    try:
        params = json.dumps({"value": payload.value})
        rule = RuleDB(
            id=str(uuid.uuid4()),
            name=payload.name,
            rule_type=payload.rule_type,
            enabled=True,
            params=params,
        )
        session.add(rule)
        session.commit()
        print(f"✅ Rule added: {payload.name}")
        return {"status": "ok", "rule_id": rule.id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    finally:
        session.close()

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    session = SessionLocal()
    transactions = session.query(TransactionDB).order_by(TransactionDB.timestamp.desc()).limit(50).all()
    rules = session.query(RuleDB).all()
    session.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "transactions": transactions, "rules": rules},
    )

if __name__ == "__main__":
    print("✅ Starting FastAPI Fraud Detection System...")
    uvicorn.run(app, host="127.0.0.1", port=8000)