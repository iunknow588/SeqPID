from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import csv

import sys

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from schema_probe import probe_input_schema


class SchemaProbeTest(unittest.TestCase):
    def test_probe_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = probe_input_schema(tmp, "20260710")
            self.assertIn("trades", result.summary["missing_file_keys"])
            self.assertFalse(result.summary["order_lifetime_ms_detected"])
            self.assertIn("reference_features", result.files)

    def test_probe_per_stock_dirs_with_chinese_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "000001.SZ"
            base.mkdir(parents=True, exist_ok=True)
            for name, header in [
                ("逐笔成交.csv", ["万得代码", "自然日", "时间", "成交价格", "成交数量"]),
                ("逐笔委托.csv", ["万得代码", "自然日", "时间", "委托代码", "委托价格", "委托数量"]),
                ("行情.csv", ["万得代码", "自然日", "时间", "申买价1", "申卖价1"]),
            ]:
                with (base / name).open("w", encoding="gb18030", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(header)
                    writer.writerow(["000001.SZ", "20260710", "93000000", "1", "100"])

            result = probe_input_schema(Path(tmp), "20260710")
            self.assertEqual(result.summary["layout"], "per_stock_dirs")
            self.assertEqual(result.summary["sample_stock_dir"], "000001.SZ")
            self.assertTrue(result.files["trades"].exists)
            self.assertTrue(result.files["orders"].exists)
            self.assertTrue(result.files["snapshots"].exists)


if __name__ == "__main__":
    unittest.main()
