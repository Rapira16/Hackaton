from datetime import datetime, timedelta

def threshold_rule(tx, params):
    field = params.get("field", "amount")
    op = params.get("operator", ">")
    value = params.get("value", 100000)
    val = getattr(tx, field, 0)
    if op == ">" and val > value:
        return True, f"{field} {val} > {value}"
    if op == ">=" and val >= value:
        return True, f"{field} {val} >= {value}"
    if op == "<" and val < value:
        return True, f"{field} {val} < {value}"
    if op == "<=" and val <= value:
        return True, f"{field} {val} <= {value}"
    if op == "==" and val == value:
        return True, f"{field} {val} == {value}"
    if op == "!=" and val != value:
        return True, f"{field} {val} != {value}"
    return False, ""

def pattern_rule(tx, params, history):
    N = params.get("N", 3)
    T = params.get("minutes", 5)
    recent = [t for t in history if t.sender_account == tx.sender_account and
              t.timestamp > datetime.utcnow() - timedelta(minutes=T)]
    if len(recent) >= N:
        return True, f"{len(recent)} tx in last {T} min"
    return False, ""

def composite_rule(tx, params, history):
    # Простейший AND из threshold + pattern
    t_alert, t_msg = threshold_rule(tx, params.get("threshold", {}))
    p_alert, p_msg = pattern_rule(tx, params.get("pattern", {}), history)
    if t_alert and p_alert:
        return True, f"Composite Alert: {t_msg} + {p_msg}"
    return False, ""

def ml_rule(tx, params):
    # Заглушка: если amount > threshold, то вероятность fraud
    threshold = params.get("threshold", 0.8)
    prob = min(tx.amount / 200000, 1.0)  # условная вероятность
    if prob > threshold:
        return True, f"ML probability {prob:.2f} > {threshold}"
    return False, ""
