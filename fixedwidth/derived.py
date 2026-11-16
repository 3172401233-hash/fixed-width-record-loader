"""派生字段计算。"""

from __future__ import annotations

from decimal import Decimal

from .errors import ParseError
from .layout import DerivedRule


def apply_derived(record: dict, rules) -> None:
    """就地计算派生字段；规则引用缺失字段时抛 ParseError。"""
    for rule in rules:
        record[rule.name] = _eval(rule, record)


def _eval(rule: DerivedRule, record: dict):
    missing = [s for s in rule.source if s not in record]
    if missing:
        raise ParseError(f"派生字段 {rule.name} 缺少来源字段：{', '.join(missing)}")
    values = [record[s] for s in rule.source]
    if rule.op == "abs":
        return abs(values[0])
    if rule.op == "sub":
        result = values[0]
        for v in values[1:]:
            result -= v if v is not None else Decimal("0")
        return result
    if rule.op == "concat":
        return rule.sep.join(str(v) for v in values)
    if rule.op == "sign":
        v = values[0]
        if v > 0:
            return "POS"
        if v < 0:
            return "NEG"
        return "ZERO"
    raise ParseError(f"派生字段 {rule.name} 未知规则 {rule.op!r}")  # pragma: no cover
