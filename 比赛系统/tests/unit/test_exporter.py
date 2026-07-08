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

from exporter import (
    build_submit_zip,
    export_batch_diagnostics,
    export_market_pid_snapshot,
    export_market_regime_report,
    export_pattern_reco,
    export_predict_result,
    validate_submission_files,
)
from schemas import MarketPidSnapshot, PatternResult, PredictResult


class ExporterTest(unittest.TestCase):
    def test_export_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_pattern_reco(
                [PatternResult("stock1", "20260710", "pattern", "explanation")],
                base / "pattern_reco.csv",
            )
            export_predict_result(
                [PredictResult("stock1", "20260710", "鏁ｆ埛", "intent_a")],
                base / "predict_result.csv",
            )
            zip_path = build_submit_zip(base)

            self.assertTrue(Path(zip_path).exists())
            with (base / "pattern_reco.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[0], ["stock_code", "transaction_date", "pattern_type", "pattern_explanation"])
            self.assertEqual(rows[1][0], "stock1")

    def test_predict_result_supports_extended_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_predict_result(
                [PredictResult("000001.SZ", "20260710", "type", "intent", 0.8, 0.7, {"k": "v"})],
                base / "predict_result.csv",
            )
            with (base / "predict_result.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[1], ["000001.SZ", "20260710", "type", "intent"])

    def test_submission_date_override_rewrites_transaction_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_pattern_reco(
                [PatternResult("stock1", "20260710", "pattern", "explanation")],
                base / "pattern_reco.csv",
                submit_date_override="20260706",
            )
            export_predict_result(
                [PredictResult("stock1", "20260710", "鏁ｆ埛", "intent_a")],
                base / "predict_result.csv",
                submit_date_override="20260706",
            )
            with (base / "pattern_reco.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                pattern_rows = list(csv.reader(fh))
            with (base / "predict_result.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                predict_rows = list(csv.reader(fh))
            self.assertEqual(pattern_rows[1][1], "20260706")
            self.assertEqual(predict_rows[1][1], "20260706")

    def test_validate_submission_files_rejects_mismatched_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_pattern_reco(
                [PatternResult("stock1", "20260710", "pattern", "explanation")],
                base / "pattern_reco.csv",
            )
            export_predict_result([], base / "predict_result.csv")

            with self.assertRaises(ValueError):
                validate_submission_files(base / "pattern_reco.csv", base / "predict_result.csv")

    def test_export_market_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snapshot = MarketPidSnapshot(
                trade_date="20260710",
                up_count=10,
                down_count=5,
                breadth_ratio=2.0,
                breadth_balance=0.3333,
                p_mean=0.12,
                p_median=0.11,
                p_std=0.05,
                i_mean=0.22,
                i_median=0.20,
                i_std=0.08,
                d_mean=0.31,
                d_median=0.30,
                d_std=0.09,
                market_regime="strong_uptrend",
                diagnostics={"sample_count": 15},
            )
            export_market_pid_snapshot(snapshot, base / "market_pid_snapshot.csv")
            export_market_regime_report(snapshot, base / "market_regime_report.md")

            self.assertTrue((base / "market_pid_snapshot.csv").exists())
            self.assertTrue((base / "market_regime_report.md").exists())

    def test_export_batch_diagnostics_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snapshot = MarketPidSnapshot(
                trade_date="20260710",
                up_count=10,
                down_count=5,
                breadth_ratio=2.0,
                breadth_balance=0.3333,
                p_mean=0.12,
                p_median=0.11,
                p_std=0.05,
                i_mean=0.22,
                i_median=0.20,
                i_std=0.08,
                d_mean=0.31,
                d_median=0.30,
                d_std=0.09,
                market_regime="strong_uptrend",
                diagnostics={"sample_count": 2},
            )
            json_path, csv_path = export_batch_diagnostics(
                snapshot,
                [PatternResult("stock1", "20260710", "pattern_a", "desc"), PatternResult("stock2", "20260710", "pattern_b", "desc")],
                [
                    PredictResult("stock1", "20260710", "鏁ｆ埛", "intent_a"),
                    PredictResult("stock2", "20260710", "娓歌祫", "intent_b"),
                ],
                base,
            )
            self.assertTrue(Path(json_path).exists())
            self.assertTrue(Path(csv_path).exists())
            with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[0], ["category", "label", "count", "ratio"])

    def test_validate_submission_files_rejects_duplicate_stock_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_pattern_reco(
                [
                    PatternResult("stock1", "20260710", "pattern", "explanation"),
                    PatternResult("stock2", "20260710", "pattern", "explanation"),
                ],
                base / "pattern_reco.csv",
            )
            export_predict_result(
                [
                    PredictResult("stock1", "20260710", "鏁ｆ埛", "intent_a"),
                    PredictResult("stock1", "20260710", "娓歌祫", "intent_b"),
                ],
                base / "predict_result.csv",
            )

            with self.assertRaises(ValueError):
                validate_submission_files(base / "pattern_reco.csv", base / "predict_result.csv")


if __name__ == "__main__":
    unittest.main()
