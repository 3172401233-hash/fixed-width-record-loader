"""文件级加载：布局选择、尾部校验、原子提交与重传幂等。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal

from .derived import apply_derived
from .errors import BadRecord, ParseError
from .layout import LayoutVersion
from .parser import parse_record, split_lines


class UploadRegistry:
    """按文件名登记已处理文件的摘要，保证相同文件名重传的幂等性。"""

    def __init__(self, path=None):
        self.path = path
        self._entries = {}
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self._entries = json.load(fh)

    def check(self, filename, digest):
        """返回 'new' / 'duplicate' / 'conflict'。"""
        known = self._entries.get(filename)
        if known is None:
            return "new"
        return "duplicate" if known == digest else "conflict"

    def register(self, filename, digest):
        self._entries[filename] = digest
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._entries, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)


@dataclass
class LoadResult:
    status: str  # committed | rejected | duplicate
    filename: str
    version: str
    records: list = field(default_factory=list)
    bad_records: list = field(default_factory=list)
    header: dict | None = None
    trailer: dict | None = None
    error: str | None = None

    @property
    def committed(self):
        return self.status == "committed"


class FileLoader:
    """按布局版本加载日文件。

    sink: 提交回调，签名为 sink(records, header, trailer)。
          只有在尾部校验通过后才调用，失败时整文件不落库。
    """

    def __init__(self, version, sink, registry=None):
        self.version = version
        self.sink = sink
        self.registry = registry or UploadRegistry()

    def load(self, data, filename):
        v = self.version
        digest = hashlib.sha256(data).hexdigest()
        check = self.registry.check(filename, digest)
        if check == "duplicate":
            return LoadResult("duplicate", filename, v.version,
                              error="相同文件名且内容一致的重传，已幂等跳过")
        if check == "conflict":
            return LoadResult("rejected", filename, v.version,
                              error="相同文件名但内容不一致，拒绝覆盖已提交批次")

        result = LoadResult("rejected", filename, v.version)
        details = []
        total = Decimal("0")

        for line_no, (offset, raw) in enumerate(split_lines(data), start=1):
            type_code = self._type_code(raw)
            layout = v.layout_for(type_code) if type_code is not None else None
            if layout is None:
                result.bad_records.append(BadRecord(
                    offset, line_no, f"未知记录类型 {type_code!r}", raw))
                continue
            try:
                record = parse_record(raw, layout, v.encoding)
                if layout.record_type == v.detail_type:
                    apply_derived(record, v.derived)
            except ParseError as exc:
                result.bad_records.append(BadRecord(offset, line_no, str(exc), raw))
                continue

            if layout.record_type == v.header_type:
                result.header = record
            elif layout.record_type == v.trailer_type:
                result.trailer = record
            else:
                details.append(record)
                total += record[v.detail_amount_field]

        error = self._validate(result, details, total)
        if error is not None:
            result.error = error
            return result

        # 尾部校验通过才提交：在此之前任何数据都不落库
        self.sink(details, result.header, result.trailer)
        self.registry.register(filename, digest)
        result.status = "committed"
        result.records = details
        return result

    def _type_code(self, raw):
        v = self.version
        chunk = raw[v.type_start : v.type_start + v.type_length]
        if len(chunk) < v.type_length:
            return None
        try:
            return chunk.decode(v.encoding)
        except UnicodeDecodeError:
            return None

    def _validate(self, result, details, total):
        v = self.version
        if result.header is None:
            return "缺少头记录"
        if result.trailer is None:
            return "缺少尾记录"
        declared_count = result.trailer[v.trailer_count_field]
        if declared_count != len(details):
            return (f"尾部校验失败：声明笔数 {declared_count}，"
                    f"实际解析明细 {len(details)} 笔")
        declared_total = result.trailer[v.trailer_amount_field]
        if declared_total != total:
            return (f"尾部校验失败：声明合计 {declared_total}，"
                    f"实际明细合计 {total}")
        return None
