from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Text, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import threading, time, uuid, json, uvicorn, requests, logging, csv
from io import StringIO

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO, format='%(message)s')

# -------------------- База данных --------------------
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
    status = Column(String, default="processed")
    alerts = Column(Text, default="")

class RuleDB(Base):
    __tablename__ = "rules"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    rule_type = Column(String)
    enabled = Column(Boolean, default=True)
    params = Column(Text)

class RuleHistory(Base):
    __tablename__ = "rule_history"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String)
    action = Column(String)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    changed_by = Column(String, default="admin")
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# -------------------- Pydantic схемы --------------------
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

# -------------------- FastAPI --------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")
ALLOWED_TYPES = ["payment", "withdrawal", "transfer", "deposit"]

# -------------------- Telegram уведомления --------------------
TELEGRAM_BOT_TOKEN = "7963185721:AAEkRJWokbTdx2W74RBd5UnWnuKY_A4VNyU"
TELEGRAM_CHAT_ID = "1600738086"
sent_alerts = set()  # дедупликация

def log_event(stage, tx, component="ingest", extra=None):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "stage": stage,
        "component": component,
        "correlation_id": tx.correlation_id,
        "sender": tx.sender_account,
        "receiver": tx.receiver_account,
        "amount": tx.amount,
        "transaction_type": tx.transaction_type,
        "status": tx.status,
        "alerts": tx.alerts,
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

# -------------------- Очередь и воркер --------------------
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
        log_event("db_commit", tx, component="queue")
        send_telegram_alert(tx, "Transaction processed")
    except Exception as e:
        session.rollback()
        log_event("db_error", tx, component="queue", extra={"error": str(e), "level": "ERROR"})
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

# -------------------- REST Endpoints --------------------
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
    log_event("queued", tx, component="ingest")
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
        # Логируем историю
        history = RuleHistory(
            rule_id=rule.id,
            action="create",
            new_values=json.dumps({"name": rule.name, "rule_type": rule.rule_type, "params": params})
        )
        session.add(history)
        session.commit()
        log_event("rule_added", tx=Transaction("system","system",0,"system"), component="rules", extra={"rule_name": payload.name})
        return {"status": "ok", "rule_id": rule.id}
    finally:
        session.close()

@app.post("/rules/edit/{rule_id}")
async def edit_rule(rule_id: str, payload: RuleIn):
    session = SessionLocal()
    try:
        rule = session.query(RuleDB).filter(RuleDB.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        old_values = json.dumps({"name": rule.name, "rule_type": rule.rule_type, "params": rule.params})
        rule.name = payload.name
        rule.rule_type = payload.rule_type
        rule.params = json.dumps({"value": payload.value})
        session.add(rule)
        session.commit()
        history = RuleHistory(
            rule_id=rule.id,
            action="update",
            old_values=old_values,
            new_values=json.dumps({"name": rule.name, "rule_type": rule.rule_type, "params": rule.params})
        )
        session.add(history)
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()

@app.post("/rules/delete/{rule_id}")
async def delete_rule(rule_id: str):
    session = SessionLocal()
    try:
        rule = session.query(RuleDB).filter(RuleDB.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        old_values = json.dumps({"name": rule.name, "rule_type": rule.rule_type, "params": rule.params})
        session.delete(rule)
        session.commit()
        history = RuleHistory(
            rule_id=rule_id,
            action="delete",
            old_values=old_values,
        )
        session.add(history)
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    session = SessionLocal()
    transactions = session.query(TransactionDB).order_by(TransactionDB.timestamp.desc()).limit(50).all()
    rules = session.query(RuleDB).all()
    session.close()
    return templates.TemplateResponse("admin.html", {"request": request, "transactions": transactions, "rules": rules})

@app.get("/admin/transactions", response_class=HTMLResponse)
async def list_transactions(request: Request, page: int = 1, per_page: int = 20, status: str = None):
    session = SessionLocal()
    query = session.query(TransactionDB).order_by(TransactionDB.timestamp.desc())
    if status:
        query = query.filter(TransactionDB.status == status)
    total = query.count()
    transactions = query.offset((page-1)*per_page).limit(per_page).all()
    session.close()
    return templates.TemplateResponse("transactions.html", {
        "request": request,
        "transactions": transactions,
        "page": page,
        "per_page": per_page,
        "total": total,
        "status": status
    })

@app.get("/admin/transaction/{correlation_id}", response_class=HTMLResponse)
async def transaction_detail(request: Request, correlation_id: str):
    session = SessionLocal()
    tx = session.query(TransactionDB).filter(TransactionDB.correlation_id == correlation_id).first()
    session.close()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return templates.TemplateResponse("transaction_detail.html", {"request": request, "tx": tx})

@app.get("/admin/stats", response_class=HTMLResponse)
async def stats(request: Request):
    session = SessionLocal()
    total = session.query(TransactionDB).count()
    alerted = session.query(TransactionDB).filter(TransactionDB.status=="alerted").count()
    processed = session.query(TransactionDB).filter(TransactionDB.status=="processed").count()
    session.close()
    return templates.TemplateResponse("stats.html", {"request": request, "total": total, "alerted": alerted, "processed": processed})

@app.get("/admin/export")
async def export_csv():
    session = SessionLocal()
    transactions = session.query(TransactionDB).all()
    session.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["correlation_id","sender","receiver","amount","type","status","alerts","timestamp"])
    for tx in transactions:
        writer.writerow([tx.correlation_id, tx.sender_account, tx.receiver_account, tx.amount, tx.transaction_type, tx.status, tx.alerts, tx.timestamp])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition":"attachment; filename=transactions.csv"})

if __name__ == "__main__":
    print("✅ Starting FastAPI Fraud Detection System...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
