from pydantic import BaseModel, Field, field_validator

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
