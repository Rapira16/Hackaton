from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models import Transaction, transactions, rules, Rule
from queue_worker import queue
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

ALLOWED_TYPES = ["payment", "withdrawal", "transfer"]

@app.post("/transactions")
async def create_transaction(sender_account: str = Form(...),
                             receiver_account: str = Form(...),
                             amount: float = Form(...),
                             transaction_type: str = Form(...)):
    if transaction_type not in ALLOWED_TYPES or amount <= 0:
        return {"status": "error", "message": "Invalid data"}
    tx = Transaction(sender_account, receiver_account, amount, transaction_type)
    queue.append(tx)
    return {"status": "queued", "correlation_id": tx.correlation_id}

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, "transactions": transactions, "rules": rules})

@app.post("/rules/add")
async def add_rule(name: str = Form(...), rule_type: str = Form(...), value: float = Form(0)):
    params = {"value": value}
    rule = Rule(name, rule_type, params=params)
    rules.append(rule)
    return {"status": "ok", "rule_id": rule.id}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
