"""内置布局版本：V2009（GBK）与 V2015（UTF-8，含补充字段）。字段宽度单位均为字节。"""

from .layout import DerivedRule, FieldSpec, LayoutVersion, RecordLayout


def v2009() -> LayoutVersion:
    """2009 版：GBK 编码，金额符号位在前，无补充字段。"""
    header = RecordLayout("H", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("file_date", 1, 8),
        FieldSpec("batch_no", 9, 6),
    ))
    detail = RecordLayout("D", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("account", 1, 12),
        FieldSpec("name", 13, 20),
        FieldSpec("amount", 33, 12, "decimal", sign="leading", scale=2),
        FieldSpec("currency", 45, 3),
    ))
    trailer = RecordLayout("T", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("detail_count", 1, 6, "int"),
        FieldSpec("total_amount", 7, 14, "decimal", sign="leading", scale=2),
    ))
    return LayoutVersion(
        version="V2009",
        encoding="gbk",
        type_start=0,
        type_length=1,
        layouts={"H": header, "D": detail, "T": trailer},
        header_type="H",
        detail_type="D",
        trailer_type="T",
        trailer_count_field="detail_count",
        trailer_amount_field="total_amount",
        detail_amount_field="amount",
        derived=(
            DerivedRule("amount_abs", "abs", ("amount",)),
            DerivedRule("amount_sign", "sign", ("amount",)),
        ),
    )


def v2015() -> LayoutVersion:
    """2015 版：UTF-8 编码，金额符号位在后，支持超长行的补充字段。"""
    header = RecordLayout("H", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("file_date", 1, 8),
        FieldSpec("batch_no", 9, 8),
        FieldSpec("channel", 17, 4),
    ))
    detail = RecordLayout("D", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("account", 1, 16),
        FieldSpec("name", 17, 30),
        FieldSpec("amount", 47, 13, "decimal", sign="trailing", scale=2),
        FieldSpec("fee", 60, 9, "decimal", scale=2),
        FieldSpec("currency", 69, 3),
    ), supplementary=(
        FieldSpec("memo", 72, 20, optional=True),
    ))
    trailer = RecordLayout("T", (
        FieldSpec("record_type", 0, 1),
        FieldSpec("detail_count", 1, 8, "int"),
        FieldSpec("total_amount", 9, 16, "decimal", sign="trailing", scale=2),
    ))
    return LayoutVersion(
        version="V2015",
        encoding="utf-8",
        type_start=0,
        type_length=1,
        layouts={"H": header, "D": detail, "T": trailer},
        header_type="H",
        detail_type="D",
        trailer_type="T",
        trailer_count_field="detail_count",
        trailer_amount_field="total_amount",
        detail_amount_field="amount",
        derived=(
            DerivedRule("net_amount", "sub", ("amount", "fee")),
            DerivedRule("amount_sign", "sign", ("amount",)),
            DerivedRule("account_name", "concat", ("account", "name"), sep="|"),
        ),
    )


VERSIONS = {"V2009": v2009, "V2015": v2015}


def get_version(name: str) -> LayoutVersion:
    try:
        return VERSIONS[name]()
    except KeyError:
        raise ValueError(f"未知布局版本 {name!r}，可选：{', '.join(VERSIONS)}") from None
