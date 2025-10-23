from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from io import StringIO
import csv, json, uuid
from datetime import datetime
from database import Base, engine, SessionLocal
from models import TransactionDB, RuleDB, RuleHistory
from schemas import TransactionIn, RuleIn
from worker import queue, Transaction
from logger import log_event

# -------------------- Инициализация --------------------
app = FastAPI(title="Fraud Detection System")
templates = Jinja2Templates(directory="templates")
ALLOWED_TYPES = ["payment", "withdrawal", "transfer", "deposit"]

# Создаём таблицы, если не существуют
Base.metadata.create_all(bind=engine)

# -------------------- API --------------------

@app.post("/transactions")
async def create_transaction(payload: TransactionIn):
    """Создаёт новую транзакцию и добавляет её в очередь на обработку."""
    if payload.transaction_type not in ALLOWED_TYPES or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid data")

    # Создаем транзакцию
    tx = Transaction(
        sender_account=payload.sender_account,
        receiver_account=payload.receiver_account,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
    )

    # Проверяем на дубликат correlation_id в БД
    session = SessionLocal()
    try:
        existing_tx = session.query(TransactionDB).filter(
            TransactionDB.correlation_id == tx.correlation_id
        ).first()

        if existing_tx:
            log_event("duplicate_rejected", tx, component="ingest",
                      extra={"level": "WARN", "reason": "duplicate_correlation_id"})
            raise HTTPException(
                status_code=409,
                detail=f"Transaction with correlation_id {tx.correlation_id} already exists"
            )
    finally:
        session.close()

    # Проверяем на дубликат в очереди
    duplicate_in_queue = any(queued_tx.correlation_id == tx.correlation_id for queued_tx in queue)
    if duplicate_in_queue:
        log_event("duplicate_rejected", tx, component="ingest",
                  extra={"level": "WARN", "reason": "duplicate_in_queue"})
        raise HTTPException(
            status_code=409,
            detail=f"Transaction with correlation_id {tx.correlation_id} is already in queue"
        )

    # Добавляем в очередь
    queue.append(tx)
    log_event("queued", tx, component="ingest")
    return {"status": "queued", "correlation_id": tx.correlation_id}

@app.post("/rules/add")
async def add_rule(payload: RuleIn):
    """Добавление нового правила."""
    session = SessionLocal()
    try:
        params = json.dumps({
            "field": "amount",
            "operator": ">",
            "value": payload.value
        })
        rule = RuleDB(
            id=str(uuid.uuid4()),
            name=payload.name,
            rule_type=payload.rule_type,
            enabled=True,
            params=params,
        )
        session.add(rule)
        session.commit()

        history = RuleHistory(
            rule_id=rule.id,
            action="create",
            new_values=json.dumps({
                "name": rule.name,
                "rule_type": rule.rule_type,
                "params": params
            })
        )
        session.add(history)
        session.commit()
        return {"status": "ok", "rule_id": rule.id}
    finally:
        session.close()


@app.post("/rules/edit/{rule_id}")
async def edit_rule(rule_id: str, payload: RuleIn):
    """Редактирование существующего правила."""
    session = SessionLocal()
    try:
        rule = session.query(RuleDB).filter(RuleDB.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        old_values = json.dumps({
            "name": rule.name,
            "rule_type": rule.rule_type,
            "params": rule.params
        })

        rule.name = payload.name
        rule.rule_type = payload.rule_type
        if payload.rule_type == "threshold":
            rule.params = json.dumps({"field": "amount", "operator": ">", "value": payload.value})
        else:
            rule.params = json.dumps({"value": payload.value})

        session.add(rule)
        session.commit()

        history = RuleHistory(
            rule_id=rule.id,
            action="update",
            old_values=old_values,
            new_values=json.dumps({
                "name": rule.name,
                "rule_type": rule.rule_type,
                "params": rule.params
            })
        )
        session.add(history)
        session.commit()
        return {"status": "ok"}
    finally:
        session.close()


@app.post("/rules/delete/{rule_id}")
async def delete_rule(rule_id: str):
    """Удаление правила."""
    session = SessionLocal()
    try:
        rule = session.query(RuleDB).filter(RuleDB.id == rule_id).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        old_values = json.dumps({
            "name": rule.name,
            "rule_type": rule.rule_type,
            "params": rule.params
        })
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


# -------------------- Admin UI --------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Главная панель администратора."""
    session = SessionLocal()
    try:
        transactions = session.query(TransactionDB).order_by(TransactionDB.timestamp.desc()).limit(50).all()
        rules = session.query(RuleDB).all()
    finally:
        session.close()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "transactions": transactions, "rules": rules}
    )


@app.get("/admin/transactions", response_class=HTMLResponse)
async def list_transactions(request: Request, page: int = 1, per_page: int = 20, status: str = None):
    """Пагинированный список транзакций."""
    session = SessionLocal()
    try:
        query = session.query(TransactionDB).order_by(TransactionDB.timestamp.desc())
        if status:
            query = query.filter(TransactionDB.status == status)
        total = query.count()
        transactions = query.offset((page-1)*per_page).limit(per_page).all()
    finally:
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
    """Подробности транзакции."""
    session = SessionLocal()
    try:
        tx = session.query(TransactionDB).filter(TransactionDB.correlation_id == correlation_id).first()
    finally:
        session.close()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return templates.TemplateResponse("transaction_detail.html", {"request": request, "tx": tx})


@app.get("/admin/stats", response_class=HTMLResponse)
async def stats(request: Request):
    """Статистика по обработке транзакций."""
    session = SessionLocal()
    try:
        total = session.query(TransactionDB).count()
        alerted = session.query(TransactionDB).filter(TransactionDB.status == "alerted").count()
        processed = session.query(TransactionDB).filter(TransactionDB.status == "processed").count()
    finally:
        session.close()
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "total": total,
        "alerted": alerted,
        "processed": processed
    })


@app.get("/admin/export")
async def export_csv():
    """Экспорт транзакций в CSV."""
    session = SessionLocal()
    try:
        transactions = session.query(TransactionDB).all()
    finally:
        session.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["correlation_id", "sender", "receiver", "amount", "type", "status", "alerts", "timestamp"])
    for tx in transactions:
        writer.writerow([
            tx.correlation_id,
            tx.sender_account,
            tx.receiver_account,
            tx.amount,
            tx.transaction_type,
            tx.status,
            tx.alerts,
            tx.timestamp
        ])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"}
    )


# -------------------- Запуск --------------------
if __name__ == "__main__":
    import uvicorn
    print("✅ Starting FastAPI Fraud Detection System...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
