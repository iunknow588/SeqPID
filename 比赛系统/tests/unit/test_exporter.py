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
    export_pid_tail_diagnostics,
    export_pid_daily_diag,
    export_pid_daily_diag_records,
    export_pid_window_diag,
    build_submit_zip,
    export_batch_diagnostics,
    export_market_pid_validation_report,
    export_market_pid_snapshot,
    export_market_regime_report,
    export_pattern_reco,
    export_predict_result,
    export_replay_validation_report,
    validate_submission_files,
)
from schemas import MarketPidSnapshot, PatternResult, PredictResult
from pid_decomposer import DecompositionResult


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

    def test_export_validation_reports(self) -> None:
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

            market_report = export_market_pid_validation_report(snapshot, base)
            replay_report = export_replay_validation_report(
                {
                    "trade_date": "20260710",
                    "sample_count": 2,
                    "output_count": 2,
                    "imputed_output_count": 0,
                    "warnings": [],
                    "missing_symbols": [],
                    "incomplete_stock_dirs": {},
                    "performance_summary": {"total_seconds": 1.2},
                },
                base,
            )

            self.assertTrue(Path(market_report).exists())
            self.assertTrue(Path(replay_report).exists())
            self.assertIn("Market PID Validation Report", Path(market_report).read_text(encoding="utf-8"))
            self.assertIn("100 Stock Replay Report", Path(replay_report).read_text(encoding="utf-8"))

    def test_export_pid_tail_diagnostics_includes_beta_mix_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = DecompositionResult(
                stock_code="000001.SZ",
                transaction_date="20260710",
            )
            result.mode = "baseline_4d"
            result.beta_mix[-1] = 0.123456
            result.beta_q[-1] = 0.111111
            result.beta_retail[-1] = 0.012345
            export_pid_tail_diagnostics([result], base / "pid_tail_diagnostics.csv")

            with (base / "pid_tail_diagnostics.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertIn("beta_mix_tail", rows[0])
            beta_mix_index = rows[0].index("beta_mix_tail")
            self.assertEqual(rows[1][beta_mix_index], "0.123456")

    def test_export_pid_standard_diag_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = DecompositionResult(stock_code="000001.SZ", transaction_date="20260710")
            result.mode = "baseline_4d"
            result.kf_converged = True
            result.c_p[-1] = 0.2
            result.c_i[-1] = 0.03
            result.c_d[-1] = -0.01
            result.eps[-1] = 0.005
            result.capital_ch[-1] = 0.12
            result.capital_q[-1] = 0.05
            result.capital_retail[-1] = 0.03
            result.capital_mix[-1] = 0.08
            result.price_basis[-1] = 10.0
            result.u_ch_amount_ratio[-1] = 0.02
            result.u_q_amount_ratio[-1] = 0.01
            result.u_retail_amount_ratio[-1] = 0.006
            result.u_mix_amount_ratio[-1] = 0.016
            cfg = {
                "q_type": "window_index",
                "u_source_type": "mv_ratio",
                "estimator_method": "kalman_filter_realtime",
                "m_slow_method": "ewma_realtime",
                "mode_switch": {"lambda_switch": 0.1, "lambda_jump": 1.0, "lambda_error": 10.0},
            }

            export_pid_window_diag([result], base / "pid_window_diag.csv", cfg)
            export_pid_daily_diag([result], base / "pid_daily_diag.csv", cfg)

            with (base / "pid_window_diag.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                window_rows = list(csv.reader(fh))
            with (base / "pid_daily_diag.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                daily_rows = list(csv.reader(fh))

            self.assertIn("state_space_contract", window_rows[0])
            self.assertIn("y_hat_next", window_rows[0])
            self.assertIn("beta_norm_ch_diag", window_rows[0])
            self.assertIn("m_eff_source_type", window_rows[0])
            self.assertIn("data_leakage_check", daily_rows[0])
            self.assertIn("lambda_switch", daily_rows[0])
            self.assertIn("beta_norm_unit", daily_rows[0])
            self.assertEqual(daily_rows[1][daily_rows[0].index("data_leakage_check")], "pass")
            self.assertEqual(daily_rows[1][daily_rows[0].index("m_eff_uncertainty_flag")], "true")
            self.assertEqual(daily_rows[1][daily_rows[0].index("m_eff_rank_eligible")], "false")
            self.assertEqual(daily_rows[1][daily_rows[0].index("beta_norm_unit")], "amount_response")
            self.assertEqual(daily_rows[1][daily_rows[0].index("m_eff_source_type")], "amount_ratio_proxy")
            self.assertIn("sample_origin", daily_rows[0])
            self.assertEqual(daily_rows[1][daily_rows[0].index("sample_origin")], "raw")
            self.assertEqual(window_rows[-1][window_rows[0].index("beta_norm_ch_diag")], "0.6")
            self.assertEqual(window_rows[-1][window_rows[0].index("m_eff_ch_diag")], "1.666667")

    def test_export_pid_daily_diag_records_preserves_warning_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_pid_daily_diag_records(
                [
                    {
                        "trade_date": "20260710",
                        "symbol": "000001.SZ",
                        "mode_name": "baseline_4d",
                        "warnings": "KF did not converge",
                        "warning_count": 1,
                    }
                ],
                base / "pid_daily_diag.csv",
                {},
            )

            with (base / "pid_daily_diag.csv").open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))

            self.assertEqual(rows[1][rows[0].index("warnings")], "KF did not converge")

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
