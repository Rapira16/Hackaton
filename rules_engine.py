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
