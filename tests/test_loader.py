"""定长记录接入器的单元测试。"""

import os
import tempfile
import unittest
from decimal import Decimal

from fixedwidth.layouts import get_version
from fixedwidth.loader import FileLoader, UploadRegistry
from fixedwidth.parser import split_lines
from samples import generate_samples as gen


class CollectingSink:
    def __init__(self):
        self.calls = []

    def __call__(self, records, header, trailer):
        self.calls.append((records, header, trailer))


class SplitLinesTest(unittest.TestCase):
    def test_mixed_line_endings(self):
        data = b"aa\r\nbb\ncc\rdd"
        lines = split_lines(data)
        self.assertEqual([raw for _, raw in lines], [b"aa", b"bb", b"cc", b"dd"])

    def test_offsets_are_byte_positions(self):
        data = b"aa\r\nbbb\n"
        offsets = [off for off, _ in split_lines(data)]
        self.assertEqual(offsets, [0, 4])

    def test_trailing_blank_lines_ignored(self):
        self.assertEqual(len(split_lines(b"aa\n\n")), 1)


class V2009LoadTest(unittest.TestCase):
    def setUp(self):
        self.sink = CollectingSink()
        self.loader = FileLoader(get_version("V2009"), self.sink)

    def test_normal_gbk_crlf_file_commits(self):
        result = self.loader.load(gen.build_v2009_normal(), "D20091231.dat")
        self.assertTrue(result.committed, result.error)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.records[0]["name"], "张三")
        self.assertEqual(result.records[0]["amount"], Decimal("123.45"))
        self.assertEqual(result.records[1]["amount"], Decimal("-50.00"))

    def test_derived_fields(self):
        result = self.loader.load(gen.build_v2009_normal(), "D20091231.dat")
        rec = result.records[1]
        self.assertEqual(rec["amount_abs"], Decimal("50.00"))
        self.assertEqual(rec["amount_sign"], "NEG")
        self.assertEqual(result.records[2]["amount_sign"], "POS")

    def test_bad_records_isolated_with_offset_and_reason(self):
        result = self.loader.load(gen.build_v2009_bad_records(), "D20091231b.dat")
        self.assertTrue(result.committed, result.error)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(result.bad_records), 3)
        reasons = [b.reason for b in result.bad_records]
        self.assertTrue(any("短行" in r for r in reasons))
        self.assertTrue(any("金额格式非法" in r for r in reasons))
        self.assertTrue(any("超长行" in r for r in reasons))
        data = gen.build_v2009_bad_records()
        for bad in result.bad_records:
            self.assertEqual(data[bad.offset : bad.offset + len(bad.raw)], bad.raw)

    def test_multibyte_char_split_by_byte_slice(self):
        # 姓名第 20 字节落在 GBK 双字节字符中间，该字段解码失败
        name = "张三".encode("gbk") + b"\xd5" + b" " * 15
        line = (b"D" + gen.pad("A00000000009", 12, "gbk") + name
                + gen.amt_leading(Decimal("1.00"), 12, 2) + b"CNY")
        data = b"\r\n".join([
            gen.v2009_header(),
            gen.v2009_detail("A00000000001", "张三", Decimal("10.00")),
            line,
            gen.v2009_trailer(1, Decimal("10.00")),
        ]) + b"\r\n"
        result = self.loader.load(data, "D20091231c.dat")
        self.assertTrue(result.committed, result.error)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.bad_records), 1)
        self.assertIn("解码失败", result.bad_records[0].reason)

    def test_unknown_record_type_isolated(self):
        data = b"\r\n".join([
            gen.v2009_header(),
            b"X" + b"?" * 20,
            gen.v2009_detail("A00000000001", "张三", Decimal("10.00")),
            gen.v2009_trailer(1, Decimal("10.00")),
        ]) + b"\r\n"
        result = self.loader.load(data, "D20091231d.dat")
        self.assertTrue(result.committed, result.error)
        self.assertEqual(len(result.bad_records), 1)
        self.assertIn("未知记录类型", result.bad_records[0].reason)


class V2015LoadTest(unittest.TestCase):
    def setUp(self):
        self.sink = CollectingSink()
        self.loader = FileLoader(get_version("V2015"), self.sink)

    def test_normal_utf8_file_commits(self):
        result = self.loader.load(gen.build_v2015_normal(), "D20150630.dat")
        self.assertTrue(result.committed, result.error)
        self.assertEqual(result.records[0]["name"], "陈晓")
        self.assertEqual(result.records[1]["amount"], Decimal("-80.50"))

    def test_trailing_sign_negative_amount(self):
        result = self.loader.load(gen.build_v2015_normal(), "D20150630.dat")
        self.assertEqual(result.records[1]["amount_sign"], "NEG")

    def test_supplementary_field_on_overlong_line(self):
        result = self.loader.load(gen.build_v2015_normal(), "D20150630.dat")
        self.assertNotIn("memo", result.records[0])
        self.assertEqual(result.records[1]["memo"], "手续费优惠")

    def test_derived_net_amount_and_concat(self):
        result = self.loader.load(gen.build_v2015_normal(), "D20150630.dat")
        rec = result.records[0]
        self.assertEqual(rec["net_amount"], Decimal("199.00"))
        self.assertEqual(rec["account_name"], "B000000000000001|陈晓")


class TrailerValidationTest(unittest.TestCase):
    def test_bad_trailer_rejects_whole_file_atomically(self):
        sink = CollectingSink()
        loader = FileLoader(get_version("V2015"), sink)
        result = loader.load(gen.build_v2015_bad_trailer(), "D20150630x.dat")
        self.assertFalse(result.committed)
        self.assertEqual(result.status, "rejected")
        self.assertIn("尾部校验失败", result.error)
        self.assertEqual(sink.calls, [])  # 没有任何部分提交

    def test_missing_trailer_rejected(self):
        sink = CollectingSink()
        loader = FileLoader(get_version("V2009"), sink)
        data = gen.v2009_header() + b"\r\n" + gen.v2009_detail(
            "A00000000001", "张三", Decimal("10.00")) + b"\r\n"
        result = loader.load(data, "D20091231m.dat")
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.error, "缺少尾记录")
        self.assertEqual(sink.calls, [])


class ReuploadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry_path = os.path.join(self.tmp.name, "registry.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _loader(self, sink):
        return FileLoader(get_version("V2009"), sink,
                          UploadRegistry(self.registry_path))

    def test_same_filename_same_content_is_idempotent(self):
        sink = CollectingSink()
        data = gen.build_v2009_normal()
        first = self._loader(sink).load(data, "D20091231.dat")
        second = self._loader(sink).load(data, "D20091231.dat")
        self.assertTrue(first.committed)
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(sink.calls), 1)

    def test_same_filename_different_content_rejected(self):
        sink = CollectingSink()
        self._loader(sink).load(gen.build_v2009_normal(), "D20091231.dat")
        other = gen.build_v2009_bad_records()
        result = self._loader(sink).load(other, "D20091231.dat")
        self.assertEqual(result.status, "rejected")
        self.assertIn("内容不一致", result.error)
        self.assertEqual(len(sink.calls), 1)

    def test_registry_persists_across_instances(self):
        sink = CollectingSink()
        data = gen.build_v2009_normal()
        self._loader(sink).load(data, "D20091231.dat")
        result = self._loader(sink).load(data, "D20091231.dat")
        self.assertEqual(result.status, "duplicate")

    def test_rejected_file_not_registered(self):
        sink = CollectingSink()
        loader = FileLoader(get_version("V2015"), sink,
                            UploadRegistry(self.registry_path))
        bad = loader.load(gen.build_v2015_bad_trailer(), "D20150630.dat")
        self.assertEqual(bad.status, "rejected")
        retry = loader.load(gen.build_v2015_normal(), "D20150630.dat")
        self.assertTrue(retry.committed, retry.error)


if __name__ == "__main__":
    unittest.main()
