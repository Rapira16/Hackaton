from datetime import datetime
import uuid

transactions = []
rules = []

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

class Rule:
    def __init__(self, name, rule_type, enabled=True, params=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.rule_type = rule_type  # 'threshold', 'pattern', 'composite', 'ml'
        self.enabled = enabled
        self.params = params or {}
