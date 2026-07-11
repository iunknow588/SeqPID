from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pid_mode_analysis import compare_pid_modes, summarize_mode_stability
from schemas import DailySample


class PIDModeAnalysisTest(unittest.TestCase):
    def _build_sample(self) -> DailySample:
        return DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[
                {
                    "window_id": "10",
                    "deal_amount": "3000000",
                    "signal_deal_buy_amount": "2000000",
                    "signal_deal_sell_amount": "1000000",
                    "CH_rule_t": "500000",
                    "Q_rule_t": "350000",
                    "R_seed_t": "150000",
                    "pi_max_price_impact_pct": "0.015",
                    "cb_cancel_order_ratio": "0.12",
                    "rs_burst_ratio": "0.55",
                },
                {
                    "window_id": "45",
                    "deal_amount": "2400000",
                    "signal_deal_buy_amount": "700000",
                    "signal_deal_sell_amount": "1700000",
                    "CH_rule_t": "-400000",
                    "Q_rule_t": "-300000",
                    "R_seed_t": "-200000",
                    "pi_max_price_impact_pct": "-0.011",
                    "cb_cancel_order_ratio": "0.08",
                    "rs_burst_ratio": "0.48",
                },
            ],
            feature_summary={},
            quality_flags={},
        )

    def test_compare_pid_modes_returns_dual_mode_metrics(self) -> None:
        rows = compare_pid_modes([self._build_sample()], {"pid_decomposer": {"mode": "baseline_4d"}})

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["stock_code"], "000001.SZ")
        self.assertIn("phi_tail_baseline_4d", row)
        self.assertIn("phi_tail_diag_5d", row)
        self.assertIn("beta_mix_consistency_gap", row)

    def test_summarize_mode_stability_labels_sign_flip_as_unstable(self) -> None:
        summary = summarize_mode_stability(
            [
                {
                    "stock_code": "000001.SZ",
                    "transaction_date": "20260707",
                    "mode": "baseline_4d",
                    "phi_tail": 0.5,
                    "theta_tail": -0.2,
                },
                {
                    "stock_code": "000001.SZ",
                    "transaction_date": "20260708",
                    "mode": "baseline_4d",
                    "phi_tail": -0.4,
                    "theta_tail": -0.21,
                },
            ],
            metrics=["phi_tail", "theta_tail"],
        )

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["phi_tail_stability"], "unstable")
        self.assertIn(summary[0]["theta_tail_stability"], {"stable", "mostly_stable"})


if __name__ == "__main__":
    unittest.main()
