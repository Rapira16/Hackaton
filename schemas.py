from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
import re

# -------------------- Схема транзакции --------------------
class TransactionIn(BaseModel):
    sender_account: str = Field(..., min_length=5, max_length=34, description="Идентификатор счёта отправителя")
    receiver_account: str = Field(..., min_length=5, max_length=34, description="Идентификатор счёта получателя")
    amount: float = Field(..., gt=0, description="Сумма транзакции, должна быть > 0")
    transaction_type: str = Field(..., description="Тип транзакции: payment, withdrawal, transfer, deposit")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Момент совершения транзакции")
    correlation_id: str = Field(None, description="Уникальный идентификатор транзакции (опционально, для тестирования)")

    # ✅ Проверка формата счетов
    @field_validator("sender_account", "receiver_account")
    def validate_account_format(cls, v, field):
        pattern = r"^[A-Z0-9]{5,34}$"  # Например, IBAN-подобный формат (только буквы/цифры)
        if not re.match(pattern, v):
            raise ValueError(f"{field.name} должен содержать только заглавные буквы и цифры, длина 5–34 символа")
        return v

    # ✅ Проверка типа транзакции
    @field_validator("transaction_type")
    def validate_type(cls, v):
        allowed = ["payment", "withdrawal", "transfer", "deposit"]
        if v not in allowed:
            raise ValueError(f"transaction_type должен быть одним из: {', '.join(allowed)}")
        return v

    # ✅ Проверка timestamp (не из будущего)
    @field_validator("timestamp")
    def validate_timestamp(cls, v):
        now = datetime.now(timezone.utc)
        if v > now:
            raise ValueError("timestamp не может быть из будущего")
        return v

# -------------------- Схема правила --------------------
class RuleIn(BaseModel):
    name: str = Field(..., description="Название правила")
    rule_type: str = Field(..., description="Тип правила: threshold, pattern, composite, ml")
    value: float = Field(0, description="Значение порога или параметр правила")
