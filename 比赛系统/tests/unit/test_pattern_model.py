from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pattern_model import predict_pattern, refine_pattern_with_pid, render_pattern_explanation
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

        self.assertEqual(refined_label, "量化T0")
        self.assertEqual(refined.pattern_type, "量化T0")
        self.assertIn(refined.pattern_type, {"量化T0", "散户博弈", "尾盘突袭", "日内套利", "大单吸筹"})
        self.assertTrue(refined.pattern_explanation)
        self.assertGreaterEqual(refined.pattern_score, 0.0)
        self.assertGreaterEqual(refined.pattern_primary_score, 0.0)
        self.assertGreaterEqual(refined.pattern_second_score, 0.0)
        self.assertTrue(refined.pattern_source)
        self.assertIsInstance(refined.pattern_pid_adjusted, bool)

    def test_pattern_result_uses_submit_labels_only(self) -> None:
        sample = DailySample(
            stock_code="600001.SH",
            transaction_date="20260706",
            rows=[],
            feature_summary={
                "deal_amount": 900_000_000,
                "close_return": 0.04,
                "open_return": 0.02,
                "intraday_range": 0.09,
                "close_strength": 0.82,
                "cancel_ratio": 0.02,
                "burst_ratio": 0.26,
                "bid_support": 0.62,
                "ask_pressure": 0.18,
                "tail_ratio": 0.18,
                "last15_return": 0.018,
                "avg_trade_size": 16_000,
                "order_buy_ratio": 0.62,
                "directional_efficiency": 0.75,
                "reversal_strength": 0.01,
            },
        )
        result = predict_pattern(sample, {"pattern_low_conf_threshold": 0.1, "pattern_margin_threshold": 0.01}, {"pattern_labels_submit": ["量化T0", "散户博弈", "尾盘突袭", "日内套利", "大单吸筹"]})

        self.assertIn(result.pattern_type, {"量化T0", "散户博弈", "尾盘突袭", "日内套利", "大单吸筹"})
        self.assertTrue(result.pattern_explanation)

    def test_pattern_explanation_template_matches_submit_style(self) -> None:
        summary = {
            "deal_amount": 900_000_000,
            "close_return": 0.035,
            "open_return": 0.0,
            "intraday_range": 0.06,
            "close_strength": 0.88,
            "cancel_ratio": 0.02,
            "burst_ratio": 0.22,
            "bid_support": 0.60,
            "ask_pressure": 0.20,
            "tail_ratio": 0.18,
            "last15_return": 0.016,
            "avg_trade_size": 18_000,
            "order_buy_ratio": 0.64,
            "directional_efficiency": 0.70,
            "reversal_strength": 0.01,
        }

        explanation = render_pattern_explanation("尾盘突袭", summary)

        self.assertIn("下午2点半", explanation)
        self.assertIn("集中拉升", explanation)
        self.assertLessEqual(len(explanation), 80)

    def test_pattern_explanation_can_imply_dominant_capital_type(self) -> None:
        cases = [
            (
                "量化T0",
                {
                    "deal_amount": 220_000_000,
                    "close_return": 0.002,
                    "intraday_range": 0.04,
                    "close_strength": 0.50,
                    "burst_ratio": 0.16,
                    "tail_ratio": 0.04,
                    "last15_return": 0.0,
                    "avg_trade_size": 3_000,
                    "order_buy_ratio": 0.50,
                    "directional_efficiency": 0.62,
                },
                ["量化", "程序化", "T0"],
            ),
            (
                "散户博弈",
                {
                    "deal_amount": 120_000_000,
                    "close_return": 0.001,
                    "intraday_range": 0.025,
                    "close_strength": 0.52,
                    "burst_ratio": 0.04,
                    "tail_ratio": 0.03,
                    "last15_return": 0.0,
                    "avg_trade_size": 2_500,
                    "order_buy_ratio": 0.52,
                    "directional_efficiency": 0.18,
                },
                ["散户", "小单"],
            ),
            (
                "大单吸筹",
                {
                    "deal_amount": 700_000_000,
                    "close_return": 0.026,
                    "intraday_range": 0.05,
                    "close_strength": 0.75,
                    "burst_ratio": 0.12,
                    "tail_ratio": 0.05,
                    "last15_return": 0.002,
                    "avg_trade_size": 24_000,
                    "order_buy_ratio": 0.62,
                    "directional_efficiency": 0.62,
                },
                ["大单", "买单", "吸收筹码"],
            ),
        ]

        for label, summary, keywords in cases:
            with self.subTest(label=label):
                explanation = render_pattern_explanation(label, summary)
                self.assertTrue(any(keyword in explanation for keyword in keywords), explanation)

    def test_pattern_explanation_reflects_execution_style(self) -> None:
        early_large_buy = {
            "deal_amount": 800_000_000,
            "close_return": 0.032,
            "open_return": 0.022,
            "intraday_range": 0.055,
            "close_strength": 0.74,
            "burst_ratio": 0.18,
            "tail_ratio": 0.04,
            "last15_return": 0.001,
            "avg_trade_size": 26_000,
            "order_buy_ratio": 0.63,
            "directional_efficiency": 0.68,
        }
        quant_small_t0 = {
            "deal_amount": 260_000_000,
            "close_return": 0.001,
            "open_return": 0.0,
            "intraday_range": 0.045,
            "close_strength": 0.50,
            "burst_ratio": 0.16,
            "tail_ratio": 0.03,
            "last15_return": 0.0,
            "avg_trade_size": 3_500,
            "order_buy_ratio": 0.50,
            "directional_efficiency": 0.62,
        }

        early_explanation = render_pattern_explanation("大单吸筹", early_large_buy)
        quant_explanation = render_pattern_explanation("量化T0", quant_small_t0)

        self.assertIn("早盘", early_explanation)
        self.assertIn("大单", early_explanation)
        self.assertIn("小单", quant_explanation)
        self.assertIn("T0", quant_explanation)


if __name__ == "__main__":
    unittest.main()
