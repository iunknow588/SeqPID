from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from batch_reporting import build_batch_result, build_batch_summary, build_performance_summary
from schemas import PatternResult, PredictResult


class BatchReportingTest(unittest.TestCase):
    def test_build_batch_summary_counts_warnings(self) -> None:
        summary = build_batch_summary("20260710", sample_count=3, output_count=4, warnings=["a", "b"])
        self.assertEqual(summary["warning_count"], 2)
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["output_count"], 4)

    def test_build_performance_summary_returns_none_when_disabled(self) -> None:
        summary = build_performance_summary(
            profile_enabled=False,
            total_seconds=1.0,
            sample_build_seconds=0.1,
            pattern_seconds=0.2,
            capital_seconds=0.3,
            market_seconds=0.4,
            export_seconds=0.5,
            sample_timings=[],
            processed_samples=1,
            imputed_predict_count=0,
            skipped_incomplete_samples=0,
            round_seconds=lambda value: round(value, 6),
        )
        self.assertIsNone(summary)

    def test_build_batch_result_keeps_counts_and_paths(self) -> None:
        result = build_batch_result(
            trade_date="20260710",
            sample_count=2,
            pattern_results=[PatternResult("000001.SZ", "20260710", "A", "x")],
            predict_results=[PredictResult("000001.SZ", "20260710", "游资", "买入")],
            market_snapshot=None,
            market_snapshot_path=None,
            market_report_path=None,
            market_validation_report_path="mvr.md",
            replay_validation_report_path="rvr.md",
            diagnostics_json_path="diag.json",
            distribution_csv_path="dist.csv",
            submit_zip="submit.zip",
            warnings=["w1"],
            imputed_output_count=1,
            stock_offset=3,
            stock_limit=10,
            stock_list_file="list.csv",
            stock_universe_size=8,
            missing_symbols=["000002.SZ"],
            incomplete_stock_dirs={"000003.SZ": ["orders"]},
            performance_summary={"total_seconds": 1.2},
        )
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["output_count"], 1)
        self.assertEqual(result["stock_offset"], 3)
        self.assertEqual(result["stock_list_file"], "list.csv")
        self.assertEqual(result["performance_summary"]["total_seconds"], 1.2)


if __name__ == "__main__":
    unittest.main()
