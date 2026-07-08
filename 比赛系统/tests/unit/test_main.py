from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import main


class MainPathResolutionTest(unittest.TestCase):
    def test_infer_trade_date_from_path(self) -> None:
        self.assertEqual(main._infer_trade_date_from_path(r"C:\level-2-ana\data\20260706"), "20260706")

    def test_resolve_input_dir_prefers_date_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "20260706"
            stock_dir = target / "000001.SZ"
            stock_dir.mkdir(parents=True, exist_ok=True)
            for name in ("a.csv", "b.csv", "c.csv"):
                (stock_dir / name).write_text("", encoding="utf-8")

            resolved = main._resolve_input_dir(str(base), "20260706")

            self.assertEqual(resolved, target)

    def test_resolve_input_dir_prefers_nested_trade_date_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "20260130" / "20260130"
            target.mkdir(parents=True, exist_ok=True)
            (target / "reference_features.csv").write_text("date,symbol\n", encoding="utf-8")

            resolved = main._resolve_input_dir(str(base), "20260130")

            self.assertEqual(resolved, target)

    def test_resolve_stock_list_file_prefers_official_sample_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir = base / "data"
            input_dir = data_dir / "20260706"
            input_dir.mkdir(parents=True, exist_ok=True)
            official = data_dir / "百只股票样本.csv"
            official.write_text("股票代码\n603316.SH\n", encoding="utf-8-sig")

            resolved = main._resolve_stock_list_file(None, input_dir)

            self.assertEqual(resolved, official)

    def test_resolve_stock_list_file_prefers_explicit_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "20260706"
            input_dir.mkdir(parents=True, exist_ok=True)
            explicit = base / "custom.csv"
            explicit.write_text("stock_code\n000001.SZ\n", encoding="utf-8-sig")
            (base / "百只股票样本.csv").write_text("股票代码\n603316.SH\n", encoding="utf-8-sig")

            resolved = main._resolve_stock_list_file(str(explicit), input_dir)

            self.assertEqual(resolved, explicit)


if __name__ == "__main__":
    unittest.main()
