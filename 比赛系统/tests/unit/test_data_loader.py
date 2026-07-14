from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import data_loader


class DataLoaderTest(unittest.TestCase):
    def test_looks_like_stock_symbol_accepts_common_forms(self) -> None:
        self.assertTrue(data_loader.looks_like_stock_symbol("000001"))
        self.assertTrue(data_loader.looks_like_stock_symbol("600000.SH"))
        self.assertTrue(data_loader.looks_like_stock_symbol("300001.sz"))
        self.assertFalse(data_loader.looks_like_stock_symbol(""))
        self.assertFalse(data_loader.looks_like_stock_symbol("symbol"))

    def test_required_file_detection_uses_declared_raw_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stock_dir = Path(tmp) / "000001"
            stock_dir.mkdir()

            for filename in data_loader.REQUIRED_STOCK_FILES.values():
                (stock_dir / filename).write_text("", encoding="utf-8")

            self.assertTrue(data_loader.is_stock_dir(stock_dir))
            self.assertEqual(data_loader.get_missing_required_files(stock_dir), [])

            (stock_dir / data_loader.REQUIRED_STOCK_FILES["orders"]).unlink()
            self.assertFalse(data_loader.is_stock_dir(stock_dir))
            self.assertEqual(data_loader.get_missing_required_files(stock_dir), ["orders"])

    def test_filter_stock_dirs_preserves_input_order_and_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stock_dirs = [base / "000002", base / "000001", base / "600000.SH"]
            for stock_dir in stock_dirs:
                stock_dir.mkdir()

            filtered = data_loader.filter_stock_dirs(stock_dirs, {"000001", "600000.SH"})

            self.assertEqual([item.name for item in filtered], ["000001", "600000.SH"])

    def test_read_csv_rows_filters_trade_date_with_ascii_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "rows.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["trade_date", "value"])
                writer.writeheader()
                writer.writerow({"trade_date": "20260105", "value": "keep"})
                writer.writerow({"trade_date": "20260106", "value": "drop"})

            rows = data_loader.read_csv_rows(csv_path, "20260105")

            self.assertEqual(rows, [{"trade_date": "20260105", "value": "keep"}])

    def test_read_csv_rows_with_quality_marks_null_filled_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "nulls.csv"
            csv_path.write_bytes(b"\x00" * 16)

            rows, report = data_loader.read_csv_rows_with_quality(csv_path, "20260105")

            self.assertEqual(rows, [])
            self.assertEqual(report["quality_status"], "null_filled")
            self.assertEqual(report["reason_code"], "null_filled_raw_file")

    def test_read_csv_rows_with_quality_marks_no_effective_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "rows.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["trade_date", "value"])
                writer.writeheader()
                writer.writerow({"trade_date": "20260106", "value": "drop"})

            rows, report = data_loader.read_csv_rows_with_quality(csv_path, "20260105")

            self.assertEqual(rows, [])
            self.assertEqual(report["quality_status"], "no_effective_rows")
            self.assertEqual(report["reason_code"], "no_effective_rows")

    def test_find_stock_basics_file_prefers_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            configured = base / "custom_basics.csv"
            configured.write_text("symbol,float_shares\n000001.SZ,123456\n", encoding="utf-8")

            found = data_loader.find_stock_basics_file(base, {"stock_basics_file": str(configured)})

            self.assertEqual(found, configured)

    def test_load_stock_mv_metadata_reads_float_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "stock_basics.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["symbol", "float_shares"])
                writer.writeheader()
                writer.writerow({"symbol": "000001.SZ", "float_shares": "1500000"})
                writer.writerow({"symbol": "000002.SZ", "float_shares": "0"})

            rows = data_loader.load_stock_mv_metadata(csv_path)

            self.assertEqual(rows, {"000001.SZ": {"float_shares": 1500000.0}})


if __name__ == "__main__":
    unittest.main()
