from __future__ import annotations

import csv
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import load_label_dict, load_runtime_config
from scheduler import _build_pid_rows_from_trades, run_daily_batch


SCHEDULER_SOURCE = (SRC_DIR / "scheduler.py").read_text(encoding="utf-8")
RAW_FILENAMES = re.findall(r'stock_dir / "([^"]+)"', SCHEDULER_SOURCE)[:3]
ALL_ROW_GET_KEYS = sorted(set(re.findall(r'row\.get\("([^"]+)"', SCHEDULER_SOURCE)))


class SchedulerTest(unittest.TestCase):
    def test_build_pid_rows_splits_large_active_and_mix_pool(self) -> None:
        rows = _build_pid_rows_from_trades(
            [
                {
                    "时间": "93000000",
                    "成交价格": "100",
                    "成交数量": "6000",
                    "BS标志": "B",
                },
                {
                    "时间": "93010000",
                    "成交价格": "100",
                    "成交数量": "1000",
                    "BS标志": "B",
                },
                {
                    "时间": "93020000",
                    "成交价格": "100",
                    "成交数量": "1500",
                    "BS标志": "S",
                },
                {
                    "时间": "93030000",
                    "成交价格": "100",
                    "成交数量": "2000",
                },
            ],
            {"species_rules": {"large_order_amount_threshold": 500_000}},
        )

        first_window = rows[0]
        self.assertEqual(first_window["signed_large_active_amount"], 600000.0)
        self.assertEqual(first_window["signed_mix_qr_amount"], -50000.0)
        self.assertEqual(first_window["large_active_buy_amount"], 600000.0)
        self.assertEqual(first_window["small_passive_buy_amount"], 100000.0)
        self.assertEqual(first_window["small_passive_sell_amount"], 150000.0)
        self.assertEqual(first_window["deal_amount"], 1050000.0)

    def test_build_pid_rows_uses_quote_to_infer_active_side(self) -> None:
        rows = _build_pid_rows_from_trades(
            [
                {
                    "时间": "93000000",
                    "成交价格": "10.20",
                    "成交数量": "60000",
                    "BS标志": "B",
                },
                {
                    "时间": "93010000",
                    "成交价格": "10.05",
                    "成交数量": "60000",
                    "BS标志": "B",
                },
                {
                    "时间": "93020000",
                    "成交价格": "9.98",
                    "成交数量": "60000",
                    "BS标志": "S",
                },
            ],
            {"species_rules": {"large_order_amount_threshold": 500_000}},
            quote_rows=[
                {
                    "时间": "92959000",
                    "申买价1": "10.00",
                    "申卖价1": "10.20",
                }
            ],
        )

        first_window = rows[0]
        self.assertEqual(first_window["signed_large_active_amount"], 13200.0)
        self.assertEqual(first_window["large_active_buy_amount"], 612000.0)
        self.assertEqual(first_window["large_active_sell_amount"], 598800.0)
        self.assertEqual(first_window["signed_mix_qr_amount"], 603000.0)
        self.assertEqual(first_window["small_passive_buy_amount"], 603000.0)

    def _write_csv_with_rows(self, path: Path, rows: list[dict[str, str]]) -> None:
        headers = list(ALL_ROW_GET_KEYS)
        with path.open("w", encoding="gb18030", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in headers})

    def _write_raw_stock_dir(self, stock_dir: Path, trade_date: str, close_price: int = 102000) -> None:
        trade_file, order_file, quote_file = [stock_dir / name for name in RAW_FILENAMES]

        self._write_csv_with_rows(
            trade_file,
            [
                {
                    "閺冨爼妫?": "93000000",
                    "閹存劒姘︽禒閿嬬壐": "100000",
                    "閹存劒姘﹂弫浼村櫤": "100",
                },
                {
                    "閺冨爼妫?": "145500000",
                    "閹存劒姘︽禒閿嬬壐": str(close_price),
                    "閹存劒姘﹂弫浼村櫤": "200",
                },
            ],
        )
        self._write_csv_with_rows(
            order_file,
            [
                {
                    "閺冨爼妫?": "93000000",
                    "婵梹澧猾璇茬€?": "0",
                    "婵梹澧禒锝囩垳": "B",
                }
            ],
        )
        self._write_csv_with_rows(
            quote_file,
            [
                {
                    "閺冨爼妫?": "93000000",
                    "閹存劒姘︽禒?": "101000",
                    "瀵偓閻╂ü鐜?": "100500",
                    "閺堚偓妤傛ü鐜?": "101000",
                    "閺堚偓娴ｅ簼鐜?": "100000",
                    "閸撳秵鏁归惄?": "100000",
                    "娑撳﹥瀹氶崫浣侯潚閺?": "3200",
                    "娑撳绌奸崫浣侯潚閺?": "1500",
                    "閹镐礁閽╅崫浣侯潚閺?": "300",
                },
                {
                    "閺冨爼妫?": "145500000",
                    "閹存劒姘︽禒?": str(close_price),
                    "瀵偓閻╂ü鐜?": "100500",
                    "閺堚偓妤傛ü鐜?": str(close_price),
                    "閺堚偓娴ｅ簼鐜?": "100000",
                    "閸撳秵鏁归惄?": "100000",
                    "娑撳﹥瀹氶崫浣侯潚閺?": "3300",
                    "娑撳绌奸崫浣侯潚閺?": "1400",
                    "閹镐礁閽╅崫浣侯潚閺?": "300",
                },
            ],
        )

    def test_batch_with_reference_features_emits_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir = base / "outputs"

            csv_path = input_dir / "reference_features.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "date",
                        "symbol",
                        "window_id",
                        "deal_amount",
                        "signal_deal_buy_amount",
                        "signal_deal_sell_amount",
                        "cb_cancel_order_ratio",
                        "rs_burst_ratio",
                        "pi_max_price_impact_pct",
                        "obp_at_best_bid_ratio",
                        "obp_at_best_ask_ratio",
                    ]
                )
                writer.writerow(["20260710", "000001.SZ", "10", "3000000", "2200000", "800000", "0.10", "0.60", "0.012", "0.55", "0.30"])
                writer.writerow(["20260710", "000001.SZ", "45", "2500000", "2100000", "400000", "0.08", "0.70", "0.018", "0.60", "0.25"])
                writer.writerow(["20260710", "000002.SZ", "12", "1800000", "700000", "1100000", "0.48", "0.10", "0.004", "0.33", "0.34"])

            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                stock_limit=None,
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 2)
            self.assertTrue((output_dir / "pattern_reco.csv").exists())
            self.assertTrue((output_dir / "predict_result.csv").exists())
            self.assertTrue((output_dir / "market_pid_snapshot.csv").exists())
            self.assertTrue((output_dir / "market_regime_report.md").exists())
            self.assertTrue((output_dir / "batch_diagnostics.json").exists())
            self.assertTrue((output_dir / "label_distribution.csv").exists())
            self.assertIsNotNone(result["market_pid_snapshot"])

            with (output_dir / "predict_result.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], ["stock_code", "transaction_date", "capital_type", "capital_intention"])
            self.assertEqual(rows[1][0], "000001.SZ")
            self.assertTrue(rows[1][2])

            with (output_dir / "pattern_reco.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                pattern_rows = list(csv.reader(fh))
            self.assertEqual(len(pattern_rows), 3)
            self.assertTrue(pattern_rows[1][2])

    def test_batch_with_per_stock_dir_raw_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            stock_dir = input_dir / "000001.SZ"
            stock_dir.mkdir(parents=True, exist_ok=True)
            output_dir = base / "outputs"
            self._write_raw_stock_dir(stock_dir, "20260710")

            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                stock_limit=None,
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 1)
            self.assertTrue((output_dir / "pattern_reco.csv").exists())
            self.assertTrue((output_dir / "predict_result.csv").exists())
            self.assertTrue((output_dir / "batch_diagnostics.json").exists())
            self.assertTrue((output_dir / "label_distribution.csv").exists())

    def test_batch_skips_incomplete_stock_dirs_and_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            complete_dir = input_dir / "000001.SZ"
            incomplete_dir = input_dir / "000002.SZ"
            complete_dir.mkdir(parents=True, exist_ok=True)
            incomplete_dir.mkdir(parents=True, exist_ok=True)
            output_dir = base / "outputs"

            self._write_raw_stock_dir(complete_dir, "20260710")
            self._write_raw_stock_dir(incomplete_dir, "20260710")
            (incomplete_dir / RAW_FILENAMES[1]).unlink()

            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 1)
            self.assertEqual(result["incomplete_stock_dirs"], {"000002.SZ": ["orders"]})
            self.assertTrue(any("000002.SZ(orders)" in warning for warning in result["warnings"]))

    def test_batch_profile_returns_performance_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            stock_dir = input_dir / "000001.SZ"
            stock_dir.mkdir(parents=True, exist_ok=True)
            output_dir = base / "outputs"
            self._write_raw_stock_dir(stock_dir, "20260710")

            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                enable_submit_zip=True,
                profile_enabled=True,
            )

            self.assertIsNotNone(result["performance_summary"])
            assert result["performance_summary"] is not None
            self.assertEqual(result["performance_summary"]["processed_samples"], 1)
            self.assertIn("total_seconds", result["performance_summary"])
            self.assertTrue(result["performance_summary"]["top_slowest_samples"])

    def test_batch_with_stock_offset_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            stock_a = input_dir / "000001.SZ"
            stock_b = input_dir / "000002.SZ"
            stock_a.mkdir(parents=True, exist_ok=True)
            stock_b.mkdir(parents=True, exist_ok=True)
            self._write_raw_stock_dir(stock_a, "20260710", close_price=102000)
            self._write_raw_stock_dir(stock_b, "20260710", close_price=98000)
            output_dir = base / "outputs"

            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                stock_limit=1,
                stock_offset=1,
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 1)
            with (output_dir / "pattern_reco.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[1][0], "000002.SZ")

    def test_batch_with_stock_list_file_filters_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            stock_a = input_dir / "000001.SZ"
            stock_b = input_dir / "000002.SZ"
            stock_a.mkdir(parents=True, exist_ok=True)
            stock_b.mkdir(parents=True, exist_ok=True)
            self._write_raw_stock_dir(stock_a, "20260710", close_price=102000)
            self._write_raw_stock_dir(stock_b, "20260710", close_price=98000)

            stock_list_file = base / "stock_list.csv"
            with stock_list_file.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["stock_code", "name"])
                writer.writerow(["000002.SZ", "example"])

            output_dir = base / "outputs"
            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                stock_list_file=stock_list_file,
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 1)
            self.assertEqual(result["stock_universe_size"], 1)
            with (output_dir / "predict_result.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[0] == "000002.SZ" for row in rows[1:]))

    def test_batch_with_stock_list_file_warns_missing_symbols_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "raw"
            stock_a = input_dir / "000001.SZ"
            stock_a.mkdir(parents=True, exist_ok=True)
            self._write_raw_stock_dir(stock_a, "20260710", close_price=102000)

            stock_list_file = base / "stock_list.csv"
            with stock_list_file.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["stock_code", "name"])
                writer.writerow(["000002.SZ", "missing"])
                writer.writerow(["000001.SZ", "present"])

            output_dir = base / "outputs"
            result = run_daily_batch(
                trade_date="20260710",
                input_dir=input_dir,
                output_dir=output_dir,
                config=load_runtime_config(ROOT / "configs" / "dev.yaml"),
                label_dict=load_label_dict(ROOT / "configs" / "label_dict.yaml"),
                stock_list_file=stock_list_file,
                enable_submit_zip=True,
            )

            self.assertEqual(result["sample_count"], 1)
            self.assertEqual(result["output_count"], 2)
            self.assertEqual(result["missing_symbols"], ["000002.SZ"])
            self.assertEqual(result["incomplete_stock_dirs"], {})
            self.assertTrue(any("Missing raw data for requested symbols: 000002.SZ" in warning for warning in result["warnings"]))
            with (output_dir / "predict_result.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(len(rows), 3)
            self.assertEqual({row[0] for row in rows[1:]}, {"000001.SZ", "000002.SZ"})


if __name__ == "__main__":
    unittest.main()
