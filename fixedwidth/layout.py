"""布局定义：版本、记录布局与字段规格。

注意：所有 start / length 一律以字节为单位，不是字符数。
多字节编码（如 GBK/UTF-8 中文）下，先按字节切片再按字段解码，
切片落在多字节字符中间会导致该字段解码失败并被隔离为坏记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    """单个字段的字节级规格。"""

    name: str
    start: int  # 起始字节偏移（0 基）
    length: int  # 宽度，单位：字节
    type: str = "str"  # str | int | decimal
    sign: str = "none"  # none | leading | trailing（符号位位置）
    scale: int = 0  # 无小数点时的隐含小数位
    optional: bool = False  # 允许全空白
    encoding: str | None = None  # 字段级编码覆盖（混合编码场景）

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class RecordLayout:
    """一种记录类型（头/明细/尾）的布局。"""

    record_type: str
    fields: tuple
    supplementary: tuple = ()  # 仅当物理行超出基础长度时才解析

    @property
    def base_length(self) -> int:
        return max(f.end for f in self.fields)

    @property
    def max_length(self) -> int:
        ends = [f.end for f in self.fields + self.supplementary]
        return max(ends)


@dataclass(frozen=True)
class DerivedRule:
    """派生字段规则。

    op:
      - abs:    绝对值，source 为单字段
      - sub:    差值，source 为 [被减数, 减数]
      - concat: 拼接，source 为多字段，sep 为连接符
      - sign:   符号标记，输出 POS / NEG / ZERO
    """

    name: str
    op: str
    source: tuple
    sep: str = ""


@dataclass(frozen=True)
class LayoutVersion:
    """一个布局版本：编码、记录类型定位、各记录布局与派生规则。"""

    version: str
    encoding: str  # 文件级默认编码
    type_start: int  # 记录类型码的字节偏移
    type_length: int  # 记录类型码的字节宽度
    layouts: dict
    header_type: str
    detail_type: str
    trailer_type: str
    trailer_count_field: str  # 尾记录中的明细笔数字段
    trailer_amount_field: str  # 尾记录中的金额合计字段
    detail_amount_field: str  # 明细中的金额字段（用于合计校验）
    derived: tuple = field(default_factory=tuple)

    def layout_for(self, type_code: str):
        return self.layouts.get(type_code)
