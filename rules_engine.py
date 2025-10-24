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
    
    pattern_type = params.get("pattern_type", "basic")
    
    if pattern_type == "time_window_aggregate":
        N = params.get("N", 3)
        T = params.get("minutes", 5)
        field = params.get("field", "amount")
        agg_op = params.get("aggregate", "count")
        agg_value = params.get("aggregate_value", None)
        
        recent = [t for t in history if t.sender_account == tx.sender_account and
                  t.timestamp > datetime.utcnow() - timedelta(minutes=T)]
        
        if len(recent) < N:
            return False, ""
        
        if agg_op == "count":
            result = len(recent)
            if result >= N:
                return True, f"{result} tx in last {T} min"
        
        elif agg_op == "sum":
            total = sum(getattr(t, field, 0) for t in recent)
            if agg_value is not None and total >= agg_value:
                return True, f"Total {field} {total} >= {agg_value} in last {T} min"
        
        elif agg_op == "avg":
            avg_val = sum(getattr(t, field, 0) for t in recent) / len(recent)
            if agg_value is not None and avg_val >= agg_value:
                return True, f"Average {field} {avg_val:.2f} >= {agg_value} in last {T} min"
    
    elif pattern_type == "sequence":
        sequence_length = params.get("sequence_length", 3)
        max_interval_minutes = params.get("max_interval_minutes", 2)
        field = params.get("field", "amount")
        field_op = params.get("field_operator", ">")
        field_value = params.get("field_value", 0)
        
        user_txs = [t for t in history if t.sender_account == tx.sender_account]
        user_txs.sort(key=lambda x: x.timestamp)
        
        if len(user_txs) < sequence_length:
            return False, ""
        
        for i in range(len(user_txs) - sequence_length + 1):
            sequence = user_txs[i:i + sequence_length]
            
            valid_sequence = True
            for j in range(1, len(sequence)):
                time_diff = (sequence[j].timestamp - sequence[j-1].timestamp).total_seconds() / 60
                if time_diff > max_interval_minutes:
                    valid_sequence = False
                    break
            
            if valid_sequence:
                field_checks = []
                for t in sequence:
                    val = getattr(t, field, 0)
                    if field_op == ">" and val > field_value:
                        field_checks.append(True)
                    elif field_op == ">=" and val >= field_value:
                        field_checks.append(True)
                    elif field_op == "<" and val < field_value:
                        field_checks.append(True)
                    elif field_op == "<=" and val <= field_value:
                        field_checks.append(True)
                    elif field_op == "==" and val == field_value:
                        field_checks.append(True)
                    else:
                        field_checks.append(False)
                
                if all(field_checks):
                    return True, f"Sequence of {sequence_length} tx with {field} {field_op} {field_value}"
    
    return False, ""

def composite_rule(tx, params, history):
    expression = params.get("expression", "")
    rules_config = params.get("rules", {})
    
    if not expression or not rules_config:
        t_alert, t_msg = threshold_rule(tx, params.get("threshold", {}))
        p_alert, p_msg = pattern_rule(tx, params.get("pattern", {}), history)
        if t_alert and p_alert:
            return True, f"Composite Alert: {t_msg} + {p_msg}"
        return False, ""
    
    try:
        result, message = evaluate_boolean_expression(tx, history, expression, rules_config)
        return result, message
    except Exception as e:
        return False, f"Composite rule error: {str(e)}"


def evaluate_boolean_expression(tx, history, expression, rules_config):
    import re
    
    tokens = tokenize_expression(expression)
    
    result, message = parse_and_evaluate(tx, history, tokens, rules_config)
    
    return result, message


def tokenize_expression(expression):
    """Разбивает выражение на токены."""
    import re
    
    patterns = [
        (r'\bAND\b', 'AND'),
        (r'\bOR\b', 'OR'), 
        (r'\bNOT\b', 'NOT'),
        (r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', 'RULE'),
        (r'\(', 'LPAREN'),
        (r'\)', 'RPAREN'),
        (r'\s+', 'SPACE')
    ]
    
    tokens = []
    pos = 0
    
    while pos < len(expression):
        matched = False
        for pattern, token_type in patterns:
            match = re.match(pattern, expression[pos:])
            if match:
                if token_type != 'SPACE':
                    tokens.append((token_type, match.group()))
                pos += len(match.group())
                matched = True
                break
        
        if not matched:
            raise ValueError(f"Неизвестный символ в позиции {pos}: '{expression[pos]}'")
    
    return tokens


def parse_and_evaluate(tx, history, tokens, rules_config):
    """Парсит и вычисляет булево выражение."""
    
    def evaluate_rule(rule_name):
        """Вычисляет отдельное правило."""
        if rule_name not in rules_config:
            raise ValueError(f"Правило '{rule_name}' не найдено в конфигурации")
        
        rule_config = rules_config[rule_name]
        rule_type = rule_config.get("type", "threshold")
        
        if rule_type == "threshold":
            return threshold_rule(tx, rule_config.get("params", {}))
        elif rule_type == "pattern":
            return pattern_rule(tx, rule_config.get("params", {}), history)
        elif rule_type == "ml":
            return ml_rule(tx, rule_config.get("params", {}))
        elif rule_type == "composite":
            return composite_rule(tx, rule_config.get("params", {}), history)
        else:
            raise ValueError(f"Неизвестный тип правила: {rule_type}")
    
    def parse_expression():
        """Парсит выражение с учетом приоритетов."""
        return parse_or_expression()
    
    def parse_or_expression():
        """Парсит OR выражения (низший приоритет)."""
        left = parse_and_expression()
        
        while tokens and tokens[0][0] == 'OR':
            tokens.pop(0)
            right = parse_and_expression()
            left_result, left_msg = left
            right_result, right_msg = right
            
            result = left_result or right_result
            if result:
                if left_result and right_result:
                    message = f"({left_msg}) OR ({right_msg})"
                elif left_result:
                    message = left_msg
                else:
                    message = right_msg
            else:
                message = f"({left_msg}) OR ({right_msg})"
            
            left = (result, message)
        
        return left
    
    def parse_and_expression():
        """Парсит AND выражения (средний приоритет)."""
        left = parse_not_expression()
        
        while tokens and tokens[0][0] == 'AND':
            tokens.pop(0)
            right = parse_not_expression()
            left_result, left_msg = left
            right_result, right_msg = right
            
            result = left_result and right_result
            if result:
                message = f"({left_msg}) AND ({right_msg})"
            else:
                message = f"({left_msg}) AND ({right_msg})"
            
            left = (result, message)
        
        return left
    
    def parse_not_expression():
        """Парсит NOT выражения (высший приоритет)."""
        if tokens and tokens[0][0] == 'NOT':
            tokens.pop(0)
            operand = parse_primary_expression()
            result, message = operand
            
            not_result = not result
            not_message = f"NOT ({message})"
            
            return (not_result, not_message)
        else:
            return parse_primary_expression()
    
    def parse_primary_expression():
        """Парсит первичные выражения (правила и группировки)."""
        if not tokens:
            raise ValueError("Неожиданный конец выражения")
        
        token_type, token_value = tokens[0]
        
        if token_type == 'LPAREN':
            tokens.pop(0)
            result = parse_expression()
            if not tokens or tokens[0][0] != 'RPAREN':
                raise ValueError("Ожидается закрывающая скобка")
            tokens.pop(0)
            return result
        
        elif token_type == 'RULE':
            tokens.pop(0)
            return evaluate_rule(token_value)
        
        else:
            raise ValueError(f"Неожиданный токен: {token_value}")
    
    result, message = parse_expression()
    
    if tokens:
        raise ValueError(f"Неожиданные токены в конце: {[t[1] for t in tokens]}")
    
    return result, message

def ml_rule(tx, params):
    threshold = params.get("threshold", 0.8)
    prob = min(tx.amount / 200000, 1.0)
    if prob > threshold:
        return True, f"ML probability {prob:.2f} > {threshold}"
    return False, ""
