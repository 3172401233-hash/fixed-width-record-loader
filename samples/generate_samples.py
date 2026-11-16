"""多版布局样本生成器：按字节宽度精确构造 V2009 / V2015 日文件。运行：python -m samples.generate_samples"""

from __future__ import annotations

import os
from decimal import Decimal

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def pad(text: str, width: int, encoding: str) -> bytes:
    """按字节宽度右补空格；超宽直接报错，防止样本错位。"""
    raw = text.encode(encoding)
    if len(raw) > width:
        raise ValueError(f"{text!r} 编码后 {len(raw)} 字节，超出宽度 {width}")
    return raw + b" " * (width - len(raw))


def amt_leading(value: Decimal, width: int, scale: int) -> bytes:
    """符号位在前的定长金额，如 -0000012345。"""
    sign = b"-" if value < 0 else b"+"
    digits = f"{int(abs(value).scaleb(scale)):0{width - 1}d}".encode()
    return sign + digits


def amt_trailing(value: Decimal, width: int, scale: int) -> bytes:
    """符号位在后的定长金额，如 0000012345-。"""
    sign = b"-" if value < 0 else b"+"
    digits = f"{int(abs(value).scaleb(scale)):0{width - 1}d}".encode()
    return digits + sign


def v2009_header(date="20091231", batch="000001") -> bytes:
    return b"H" + pad(date, 8, "gbk") + pad(batch, 6, "gbk")


def v2009_detail(account: str, name: str, amount: Decimal, currency="CNY") -> bytes:
    return (b"D" + pad(account, 12, "gbk") + pad(name, 20, "gbk")
            + amt_leading(amount, 12, 2) + pad(currency, 3, "gbk"))


def v2009_trailer(count: int, total: Decimal) -> bytes:
    return b"T" + f"{count:06d}".encode() + amt_leading(total, 14, 2)


def build_v2009_normal() -> bytes:
    """正常文件：CRLF 行尾、中文名、正负金额混合。"""
    amounts = [Decimal("123.45"), Decimal("-50.00"), Decimal("0.05")]
    lines = [
        v2009_header(),
        v2009_detail("A00000000001", "张三", amounts[0]),
        v2009_detail("A00000000002", "李四海", amounts[1]),
        v2009_detail("A00000000003", "Wang Wu", amounts[2]),
        v2009_trailer(len(amounts), sum(amounts)),
    ]
    return b"\r\n".join(lines) + b"\r\n"


def build_v2009_bad_records() -> bytes:
    """含坏记录的文件：短行、非法金额、超长行；尾部只统计好记录。"""
    good = [Decimal("10.00"), Decimal("20.00")]
    lines = [
        v2009_header(),
        v2009_detail("A00000000001", "张三", good[0]),
        b"D" + pad("A00000000002", 12, "gbk") + pad("短行", 6, "gbk"),
        b"D" + pad("A00000000003", 12, "gbk") + pad("李四", 20, "gbk")
            + b"+0000ABCD000" + pad("CNY", 3, "gbk"),
        v2009_detail("A00000000004", "王五", good[1]),
        v2009_detail("A00000000005", "赵六", Decimal("5.00")) + b"EXTRA",
        v2009_trailer(len(good), sum(good)),
    ]
    return b"\r\n".join(lines) + b"\r\n"


def v2015_header(date="20150630", batch="00000001", channel="WEB") -> bytes:
    return b"H" + pad(date, 8, "utf-8") + pad(batch, 8, "utf-8") + pad(channel, 4, "utf-8")


def v2015_detail(account: str, name: str, amount: Decimal, fee: Decimal,
                 currency="CNY", memo: str | None = None) -> bytes:
    line = (b"D" + pad(account, 16, "utf-8") + pad(name, 30, "utf-8")
            + amt_trailing(amount, 13, 2) + f"{fee.scaleb(2):09.0f}".encode()
            + pad(currency, 3, "utf-8"))
    if memo is not None:
        line += pad(memo, 20, "utf-8")
    return line


def v2015_trailer(count: int, total: Decimal) -> bytes:
    return b"T" + f"{count:08d}".encode() + amt_trailing(total, 16, 2)


def build_v2015_normal() -> bytes:
    """正常文件：LF 行尾、UTF-8 中文、符号位在后、一条带补充字段的超长行。"""
    rows = [
        ("B000000000000001", "陈晓", Decimal("200.00"), Decimal("1.00"), None),
        ("B000000000000002", "欧阳娜娜", Decimal("-80.50"), Decimal("0.50"), "手续费优惠"),
    ]
    lines = [v2015_header()]
    lines += [v2015_detail(a, n, amt, fee, memo=m) for a, n, amt, fee, m in rows]
    lines.append(v2015_trailer(len(rows), sum(r[2] for r in rows)))
    return b"\n".join(lines) + b"\n"


def build_v2015_bad_trailer() -> bytes:
    """尾部合计与明细不符的文件，用于验证整文件拒绝。"""
    lines = [
        v2015_header(),
        v2015_detail("B000000000000001", "陈晓", Decimal("200.00"), Decimal("1.00")),
        v2015_trailer(1, Decimal("999.99")),
    ]
    return b"\n".join(lines) + b"\n"


BUILDERS = {
    "D20091231_V2009.dat": build_v2009_normal,
    "D20091231_V2009_bad.dat": build_v2009_bad_records,
    "D20150630_V2015.dat": build_v2015_normal,
    "D20150630_V2015_badtrailer.dat": build_v2015_bad_trailer,
}


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    for name, builder in BUILDERS.items():
        path = os.path.join(DATA_DIR, name)
        with open(path, "wb") as fh:
            fh.write(builder())
        print(f"written {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
