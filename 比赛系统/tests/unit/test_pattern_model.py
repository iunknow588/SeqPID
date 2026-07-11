from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pattern_model import predict_pattern, refine_pattern_with_pid
from pid_decomposer import DecompositionResult
from schemas import DailySample


class PatternModelPidTest(unittest.TestCase):
    def test_pid_result_can_refine_pattern_label(self) -> None:
        sample = DailySample(
            stock_code="600000.SH",
            transaction_date="20260706",
            rows=[],
            feature_summary={
                "deal_amount": 250_000_000,
                "close_return": -0.02,
                "open_return": 0.0,
                "intraday_range": 0.03,
                "close_strength": 0.30,
                "cancel_ratio": 0.01,
                "burst_ratio": 0.15,
                "bid_support": 0.45,
                "ask_pressure": 0.55,
                "tail_ratio": 0.04,
                "last15_return": 0.0,
                "avg_trade_size": 20_000,
                "order_buy_ratio": 0.51,
                "directional_efficiency": 0.4,
                "reversal_strength": -0.02,
            },
        )
        pid_result = DecompositionResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            dominant_type="量化",
            dominant_intention="卖出",
            hot_money_ratio=0.25,
            quant_ratio=0.55,
            retail_ratio=0.20,
            damping_mean=0.06,
        )

        refined_label = refine_pattern_with_pid("盘中诱多", sample.feature_summary, pid_result)
        refined = predict_pattern(sample, {}, {}, pid_result)

        self.assertEqual(refined_label, "分时脉冲")
        self.assertEqual(refined.pattern_type, "分时脉冲")


if __name__ == "__main__":
    unittest.main()
