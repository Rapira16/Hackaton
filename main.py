from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models import Transaction, transactions, rules, Rule
from queue_worker import queue
import uvicorn
from pydantic import BaseModel, Field, field_validator


class TransactionIn(BaseModel):
    sender_account: str = Field(..., min_length=1)
    receiver_account: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    transaction_type: str

    @field_validator("transaction_type")
    def validate_type(cls, v):
        if v not in ["payment", "withdrawal", "transfer"]:
            raise ValueError("transaction_type must be one of: payment, withdrawal, transfer")
        return v


class RuleIn(BaseModel):
    name: str
    rule_type: str
    value: float = 0

app = FastAPI()
templates = Jinja2Templates(directory="templates")

ALLOWED_TYPES = ["payment", "withdrawal", "transfer"]

@app.post("/transactions")
async def create_transaction(payload: TransactionIn):
    if payload.transaction_type not in ALLOWED_TYPES or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid data")
    tx = Transaction(payload.sender_account, payload.receiver_account, payload.amount, payload.transaction_type)
    queue.append(tx)
    return {"status": "queued", "correlation_id": tx.correlation_id}

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, "transactions": transactions, "rules": rules})

@app.post("/rules/add")
async def add_rule(payload: RuleIn):
    params = {"value": payload.value}
    rule = Rule(payload.name, payload.rule_type, params=params)
    rules.append(rule)
    return {"status": "ok", "rule_id": rule.id}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
