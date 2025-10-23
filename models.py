from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, Integer
from datetime import datetime
import uuid
from database import Base

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
