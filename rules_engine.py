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
    
    pattern_type = params.get("pattern_type", "count")
    
    if pattern_type == "series":
        return _detect_series_pattern(tx, params, history)
    elif pattern_type == "aggregates":
        return _detect_aggregate_pattern(tx, params, history)
    elif pattern_type == "micro_transactions":
        return _detect_micro_transactions_pattern(tx, params, history)
    elif pattern_type == "burst":
        return _detect_burst_pattern(tx, params, history)
    elif pattern_type == "round_amounts":
        return _detect_round_amounts_pattern(tx, params, history)
    
    return False, ""

def _detect_series_pattern(tx, params, history):
    sender = getattr(tx, 'sender_account', None)
    if not sender:
        return False, ""
    
    series_window = params.get("series_window_minutes", 30)
    min_series_count = params.get("min_series_count", 5)
    max_interval = params.get("max_interval_minutes", 2)
    
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=series_window)
    
    recent_txs = [t for t in history 
                  if getattr(t, 'sender_account', None) == sender 
                  and getattr(t, 'timestamp', now) >= window_start]
    
    if len(recent_txs) < min_series_count:
        return False, ""
    
    recent_txs.sort(key=lambda t: getattr(t, 'timestamp', now))
    
    series = []
    current_series = [recent_txs[0]]
    
    for i in range(1, len(recent_txs)):
        prev_time = getattr(recent_txs[i-1], 'timestamp', now)
        curr_time = getattr(recent_txs[i], 'timestamp', now)
        interval = (curr_time - prev_time).total_seconds() / 60
        
        if interval <= max_interval:
            current_series.append(recent_txs[i])
        else:
            if len(current_series) >= min_series_count:
                series.append(current_series)
            current_series = [recent_txs[i]]
    
    if len(current_series) >= min_series_count:
        series.append(current_series)
    
    if series:
        max_series_len = max(len(s) for s in series)
        return True, f"Series detected: {len(series)} series, max length {max_series_len}"
    
    return False, ""

def _detect_aggregate_pattern(tx, params, history):
    sender = getattr(tx, 'sender_account', None)
    if not sender:
        return False, ""
    
    window_minutes = params.get("window_minutes", 60)
    min_count = params.get("min_count", 10)
    amount_threshold = params.get("amount_threshold", 1000)
    aggregate_type = params.get("aggregate_type", "sum")
    
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)
    
    recent_txs = [t for t in history 
                  if getattr(t, 'sender_account', None) == sender 
                  and getattr(t, 'timestamp', now) >= window_start]
    
    if len(recent_txs) < min_count:
        return False, ""
    
    amounts = [getattr(t, 'amount', 0) for t in recent_txs]
    
    if aggregate_type == "sum":
        total = sum(amounts)
        if total > amount_threshold:
            return True, f"High total: {total} > {amount_threshold}"
    
    elif aggregate_type == "avg":
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount > amount_threshold:
            return True, f"High average: {avg_amount:.2f} > {amount_threshold}"
    
    elif aggregate_type == "median":
        sorted_amounts = sorted(amounts)
        n = len(sorted_amounts)
        median = sorted_amounts[n//2] if n % 2 == 1 else (sorted_amounts[n//2-1] + sorted_amounts[n//2]) / 2
        if median > amount_threshold:
            return True, f"High median: {median:.2f} > {amount_threshold}"
    
    return False, ""

def _detect_micro_transactions_pattern(tx, params, history):
    sender = getattr(tx, 'sender_account', None)
    if not sender:
        return False, ""
    
    window_minutes = params.get("window_minutes", 30)
    min_count = params.get("min_count", 8)
    max_amount = params.get("max_amount", 1000)
    min_total = params.get("min_total", 5000)
    
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)
    
    recent_txs = [t for t in history 
                  if getattr(t, 'sender_account', None) == sender 
                  and getattr(t, 'timestamp', now) >= window_start]
    
    micro_txs = [t for t in recent_txs if getattr(t, 'amount', 0) <= max_amount]
    
    if len(micro_txs) >= min_count:
        total_amount = sum(getattr(t, 'amount', 0) for t in micro_txs)
        if total_amount >= min_total:
            return True, f"Micro-transactions: {len(micro_txs)} tx, total {total_amount}"
    
    return False, ""

def _detect_burst_pattern(tx, params, history):
    sender = getattr(tx, 'sender_account', None)
    if not sender:
        return False, ""
    
    burst_window = params.get("burst_window_minutes", 5)
    burst_threshold = params.get("burst_threshold", 10)
    normal_window = params.get("normal_window_minutes", 60)
    normal_multiplier = params.get("normal_multiplier", 3)
    
    now = datetime.utcnow()
    
    burst_start = now - timedelta(minutes=burst_window)
    burst_txs = [t for t in history 
                 if getattr(t, 'sender_account', None) == sender 
                 and getattr(t, 'timestamp', now) >= burst_start]
    
    if len(burst_txs) < burst_threshold:
        return False, ""
    
    normal_start = now - timedelta(minutes=normal_window)
    normal_txs = [t for t in history 
                  if getattr(t, 'sender_account', None) == sender 
                  and getattr(t, 'timestamp', now) >= normal_start]
    
    normal_txs = [t for t in normal_txs 
                  if getattr(t, 'timestamp', now) < burst_start]
    
    normal_rate = len(normal_txs) / (normal_window - burst_window) if normal_window > burst_window else 0
    burst_rate = len(burst_txs) / burst_window
    
    if burst_rate > normal_rate * normal_multiplier:
        return True, f"Burst detected: {len(burst_txs)} tx in {burst_window}min (rate: {burst_rate:.1f}/min)"
    
    return False, ""

def _detect_round_amounts_pattern(tx, params, history):
    sender = getattr(tx, 'sender_account', None)
    if not sender:
        return False, ""
    
    window_minutes = params.get("window_minutes", 60)
    min_count = params.get("min_count", 5)
    round_threshold = params.get("round_threshold", 0.95)
    
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)
    
    recent_txs = [t for t in history 
                  if getattr(t, 'sender_account', None) == sender 
                  and getattr(t, 'timestamp', now) >= window_start]
    
    if len(recent_txs) < min_count:
        return False, ""
    
    round_amounts = 0
    for t in recent_txs:
        amount = getattr(t, 'amount', 0)
        amount_str = str(int(amount))
        if len(amount_str) >= 2:
            trailing_zeros = len(amount_str) - len(amount_str.rstrip('0'))
            roundness = trailing_zeros / len(amount_str)
            if roundness >= round_threshold:
                round_amounts += 1
    
    if round_amounts >= min_count:
        return True, f"Round amounts: {round_amounts}/{len(recent_txs)} transactions"
    
    return False, ""

def composite_rule(tx, params, history):
    t_alert, t_msg = threshold_rule(tx, params.get("threshold", {}))
    p_alert, p_msg = pattern_rule(tx, params.get("pattern", {}), history)
    if t_alert and p_alert:
        return True, f"Composite Alert: {t_msg} + {p_msg}"
    
    if params.get("or", False):
        if t_alert or p_alert:
            return True, f"Composite Alert: {t_msg} OR {p_msg}"
        return False, ""
    
    if params.get("not", False):
        if not t_alert and not p_alert:
            return True, f"Composite Alert: NOT {t_msg} AND NOT {p_msg}"
        return False, ""
    
    rules = params.get("rules", [])
    if rules:
        sorted_rules = sorted(rules, key=lambda x: x.get("priority", 0), reverse=True)
        
        alerts = []
        messages = []
        
        for rule_config in sorted_rules:
            rule_type = rule_config.get("type")
            rule_params = rule_config.get("params", {})
            group_id = rule_config.get("group", "default")
            
            if rule_type == "threshold":
                alert, msg = threshold_rule(tx, rule_params)
            elif rule_type == "pattern":
                alert, msg = pattern_rule(tx, rule_params, history)
            elif rule_type == "ml":
                alert, msg = ml_rule(tx, rule_params)
            elif rule_type == "composite":
                alert, msg = composite_rule(tx, rule_params, history)
            else:
                continue
            
            if alert:
                alerts.append((group_id, alert, rule_config.get("priority", 0)))
                messages.append(f"[{group_id}] {msg}")
        
        unique_groups = set(group_id for group_id, alert, priority in alerts if alert)
        
        if unique_groups:
            strategy = params.get("group_strategy", "any")
            
            if strategy == "any":
                return True, f"Grouped Alert - Groups: {', '.join(unique_groups)} | Details: {'; '.join(messages)}"
            elif strategy == "all":
                expected_groups = set(rule.get("group", "default") for rule in rules)
                if unique_groups == expected_groups:
                    return True, f"Grouped Alert - All groups triggered: {', '.join(unique_groups)}"
            elif strategy == "majority":
                expected_groups = set(rule.get("group", "default") for rule in rules)
                if len(unique_groups) >= len(expected_groups) // 2 + 1:
                    return True, f"Grouped Alert - Majority groups: {', '.join(unique_groups)}"
        
        high_priority_alerts = [alert for group_id, alert, priority in alerts if priority >= params.get("high_priority_threshold", 8)]
        if high_priority_alerts:
            return True, f"High Priority Alert: {'; '.join(messages)}"
    
    return False, ""

def ml_rule(tx, params):
    threshold = params.get("threshold", 0.8)
    prob = min(tx.amount / 200000, 1.0)
    if prob > threshold:
        return True, f"ML probability {prob:.2f} > {threshold}"
    return False, ""
