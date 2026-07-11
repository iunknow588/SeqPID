from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from capital_model import predict_capitals
from pid_decomposer import DecompositionResult
from schemas import DailySample
from state_feature_builder import build_state_features


class StateFeatureBuilderTest(unittest.TestCase):
    def test_rule_base_keeps_structural_capital_fields_empty(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[{"window_id": "0", "CH_rule_t": "100", "Q_rule_t": "50", "R_seed_t": "-20"}],
            feature_summary={},
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            mode="rule_base",
        )

        feature = build_state_features(sample, pid_result)[0]

        self.assertFalse(feature.is_structural_output)
        self.assertEqual(feature.capital_ch_rule_approx, 100.0)
        self.assertEqual(feature.capital_q_rule_approx, 50.0)
        self.assertEqual(feature.capital_retail_rule_approx, -20.0)
        self.assertIsNone(feature.capital_ch)
        self.assertIsNone(feature.capital_q)
        self.assertIsNone(feature.capital_retail)

    def test_structural_mode_exposes_rule_errors(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[{"window_id": "0", "CH_rule_t": "100", "Q_rule_t": "50", "R_seed_t": "20"}],
            feature_summary={},
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            mode="baseline_4d",
            capital_ch=np.array([90.0] + [0.0] * 47),
            capital_q=np.array([25.0] + [0.0] * 47),
            capital_retail=np.array([10.0] + [0.0] * 47),
        )

        feature = build_state_features(sample, pid_result)[0]

        self.assertTrue(feature.is_structural_output)
        self.assertEqual(feature.capital_ch, 90.0)
        self.assertEqual(feature.rule_error_q, 0.5)
        self.assertEqual(feature.rule_error_retail, 0.5)

    def test_capital_model_debug_info_includes_state_feature_contract(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[{"window_id": "47", "CH_rule_t": "10", "Q_rule_t": "5", "R_seed_t": "0"}],
            feature_summary={},
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            mode="baseline_4d",
            dominant_type="娓歌祫",
            dominant_intention="涔板叆",
            hot_money_ratio=0.7,
            quant_ratio=0.2,
            retail_ratio=0.1,
            capital_ch=np.array([0.0] * 47 + [9.0]),
            capital_q=np.array([0.0] * 47 + [4.0]),
            capital_retail=np.array([0.0] * 48),
        )

        result = predict_capitals(sample, {}, {}, pid_result)[0]

        self.assertEqual(result.debug_info["mode_name"], "baseline_4d")
        self.assertTrue(result.debug_info["is_structural_output"])
        self.assertEqual(result.debug_info["dominant_source"], "capital_external_force")
        self.assertFalse(result.debug_info["display_fields_used_for_dominant"])
        self.assertEqual(result.debug_info["CH_rule_tail"], 10.0)
        self.assertEqual(result.debug_info["capital_ch_tail"], 9.0)


if __name__ == "__main__":
    unittest.main()
