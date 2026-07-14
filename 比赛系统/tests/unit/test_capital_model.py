from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from capital_model import predict_capitals
from pid_decomposer import DecompositionResult
from schemas import DailySample


class CapitalModelTest(unittest.TestCase):
    def test_baseline_4d_mixed_pool_requires_rule_flow_for_non_hot_label(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[
                {"window_id": "1", "CH_rule_t": "10000", "Q_rule_t": "90000", "R_seed_t": "20000"},
                {"window_id": "2", "CH_rule_t": "-5000", "Q_rule_t": "80000", "R_seed_t": "10000"},
            ],
            feature_summary={
                "raw_order_age_recovered_count": 200,
                "raw_order_age_missing_count": 20,
            },
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            mode="baseline_4d",
            dominant_type="unknown",
            dominant_intention="买入",
            hot_money_ratio=0.20,
            quant_ratio=0.55,
            retail_ratio=0.25,
        )

        result = predict_capitals(sample, {}, {}, pid_result)[0]

        self.assertEqual(result.capital_type, "量化")
        self.assertEqual(result.debug_info["capital_type_source"], "rule_flow_required_for_mixed_pool")
        self.assertFalse(result.debug_info["external_force_is_formal_type"])

    def test_rule_flow_override_uses_recovered_retail_lifecycle_signal(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[
                {"window_id": "1", "CH_rule_t": "10000", "Q_rule_t": "20000", "R_seed_t": "160000"},
                {"window_id": "2", "CH_rule_t": "-5000", "Q_rule_t": "10000", "R_seed_t": "140000"},
            ],
            feature_summary={
                "raw_order_age_recovered_count": 290,
                "raw_order_age_missing_count": 10,
            },
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            dominant_type="量化",
            dominant_intention="卖出",
            hot_money_ratio=0.22,
            quant_ratio=0.41,
            retail_ratio=0.37,
        )

        result = predict_capitals(sample, {}, {}, pid_result)[0]

        self.assertEqual(result.capital_type, "散户")
        self.assertEqual(result.capital_intention, "买入")
        self.assertEqual(result.debug_info["capital_type_source"], "rule_flow_override")
        self.assertEqual(result.debug_info["structural_capital_type"], "量化")
        self.assertEqual(result.debug_info["rule_flow_capital_type"], "散户")


if __name__ == "__main__":
    unittest.main()
