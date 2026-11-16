"""错误类型：解析失败与坏记录。"""

from __future__ import annotations

from dataclasses import dataclass


class ParseError(Exception):
    """单条记录解析失败，message 即为失败原因。"""


@dataclass
class BadRecord:
    """被隔离的坏记录，携带原始字节偏移与原因。"""

    offset: int  # 该行在文件中的起始字节偏移（0 基）
    line_no: int  # 行号（1 基）
    reason: str
    raw: bytes

    def __str__(self) -> str:  # pragma: no cover - 便于日志打印
        preview = self.raw[:40]
        return f"line {self.line_no} @byte {self.offset}: {self.reason} raw={preview!r}"
