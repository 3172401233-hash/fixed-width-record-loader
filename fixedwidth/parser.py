"""字节级行切分与单记录解析。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .errors import ParseError
from .layout import FieldSpec, RecordLayout

_NUM_RE = re.compile(r"^[0-9]*(\.[0-9]+)?$")


def split_lines(data: bytes):
    """按 CRLF / LF / CR 切分，返回 [(起始字节偏移, 原始行字节)]，跳过末尾空行。"""
    lines = []
    start = 0
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x0D or b == 0x0A:  # CR 或 LF
            lines.append((start, data[start:i]))
            if b == 0x0D and i + 1 < n and data[i + 1] == 0x0A:
                i += 2  # CRLF
            else:
                i += 1
            start = i
        else:
            i += 1
    if start < n:  # 末行无换行符
        lines.append((start, data[start:n]))
    return [(off, raw) for off, raw in lines if raw != b""]


def _decode(raw: bytes, spec: FieldSpec, default_encoding: str) -> str:
    encoding = spec.encoding or default_encoding
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(
            f"字段 {spec.name} 解码失败（{encoding}，字节 {exc.start} 处）："
            f"可能切在多字节字符中间或编码不符"
        ) from exc


def _parse_decimal(text: str, spec: FieldSpec) -> Decimal:
    text = text.strip()
    negative = False
    if spec.sign == "leading" and text[:1] in ("+", "-"):
        negative = text[0] == "-"
        text = text[1:]
    elif spec.sign == "trailing" and text[-1:] in ("+", "-"):
        negative = text[-1] == "-"
        text = text[:-1]
    text = text.strip()
    if not text or not _NUM_RE.match(text):
        raise ParseError(f"字段 {spec.name} 金额格式非法：{text!r}")
    try:
        if "." not in text and spec.scale > 0:
            value = Decimal(text or "0").scaleb(-spec.scale)
        else:
            value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - 正则已兜底
        raise ParseError(f"字段 {spec.name} 金额格式非法：{text!r}") from exc
    return -value if negative else value


def _parse_int(text: str, spec: FieldSpec) -> int:
    text = text.strip()
    if not re.match(r"^[+-]?[0-9]+$", text):
        raise ParseError(f"字段 {spec.name} 整数格式非法：{text!r}")
    return int(text)


def parse_record(raw: bytes, layout: RecordLayout, default_encoding: str) -> dict:
    """按布局解析一条物理行。失败抛 ParseError。"""
    base = layout.base_length
    if len(raw) < base:
        raise ParseError(f"短行：期望至少 {base} 字节，实际 {len(raw)} 字节")
    has_extra = len(raw) > base
    if has_extra and not layout.supplementary:
        raise ParseError(f"超长行：期望 {base} 字节，实际 {len(raw)} 字节，且本布局无补充字段")
    if len(raw) > layout.max_length:
        raise ParseError(f"超长行：超出布局最大长度 {layout.max_length} 字节（实际 {len(raw)}）")

    record = {"record_type": layout.record_type}
    specs = list(layout.fields)
    if has_extra:
        specs += [s for s in layout.supplementary if len(raw) >= s.end]
    for spec in specs:
        chunk = raw[spec.start : spec.end]
        text = _decode(chunk, spec, default_encoding)
        if spec.type == "str":
            value = text.strip()
            if not value and not spec.optional:
                raise ParseError(f"字段 {spec.name} 为必填但内容为空")
        elif spec.type == "int":
            if not text.strip() and spec.optional:
                value = None
            else:
                value = _parse_int(text, spec)
        elif spec.type == "decimal":
            if not text.strip() and spec.optional:
                value = None
            else:
                value = _parse_decimal(text, spec)
        else:  # pragma: no cover - 布局配置错误
            raise ParseError(f"字段 {spec.name} 未知类型 {spec.type!r}")
        record[spec.name] = value
    return record
