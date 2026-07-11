from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_pid import attach_market_relative_metrics, estimate_market_pid
from pid_decomposer import DecompositionResult
from schemas import DailySample, PatternResult, PredictResult


class MarketPidTest(unittest.TestCase):
    def test_market_pid_prefers_pid_components_over_capital_fields(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[],
            feature_summary={
                "net_direction": 0.2,
                "burst_ratio": 0.1,
                "cancel_ratio": 0.1,
                "price_impact": 0.01,
                "tail_ratio": 0.1,
                "bid_support": 0.2,
                "ask_pressure": 0.1,
            },
        )
        pid_result = DecompositionResult(
            stock_code="000001.SZ",
            transaction_date="20260710",
            c_p=np.array([0.0, 0.15]),
            c_i=np.array([0.0, 0.25]),
            c_d=np.array([0.0, -0.35]),
            capital_ch=np.array([0.0, -0.9]),
            capital_q=np.array([0.0, 0.9]),
            capital_retail=np.array([0.0, 0.9]),
        )

        snapshot = estimate_market_pid(
            samples=[sample],
            pid_results={sample.stock_code: pid_result},
            pattern_results=[],
            predict_results=[],
            config={},
        )

        self.assertAlmostEqual(snapshot.p_median, 0.15)
        self.assertAlmostEqual(snapshot.i_median, 0.25)
        self.assertAlmostEqual(snapshot.d_median, 0.35)
        self.assertEqual(sample.quality_flags["market_pid_source"], "pid_components")
        self.assertEqual(snapshot.diagnostics["pid_component_source_count"], 1)
        self.assertEqual(snapshot.diagnostics["heuristic_fallback_source_count"], 0)

    def test_market_pid_fallback_marks_source(self) -> None:
        sample = DailySample(
            stock_code="000002.SZ",
            transaction_date="20260710",
            rows=[],
            feature_summary={
                "net_direction": 0.4,
                "burst_ratio": 0.3,
                "cancel_ratio": 0.2,
                "price_impact": 0.01,
                "tail_ratio": 0.1,
                "bid_support": 0.3,
                "ask_pressure": 0.1,
            },
        )
        predict_result = PredictResult(
            stock_code="000002.SZ",
            transaction_date="20260710",
            capital_type="游资",
            capital_intention="买入",
        )
        pattern_result = PatternResult(
            stock_code="000002.SZ",
            transaction_date="20260710",
            pattern_type="大单吸筹",
            pattern_explanation="test",
        )

        snapshot = estimate_market_pid(
            samples=[sample],
            pid_results={},
            pattern_results=[pattern_result],
            predict_results=[predict_result],
            config={},
        )
        attach_market_relative_metrics([sample], [predict_result], snapshot)

        self.assertEqual(sample.quality_flags["market_pid_source"], "heuristic_fallback")
        self.assertEqual(snapshot.diagnostics["heuristic_fallback_source_count"], 1)
        self.assertEqual(predict_result.debug_info["market_pid_source"], "heuristic_fallback")


if __name__ == "__main__":
    unittest.main()
