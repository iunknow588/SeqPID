from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pid_decomposer import PIDDecomposer
from schemas import DailySample


class PIDDecomposerTest(unittest.TestCase):
    def test_sparse_normalize_keeps_zero_windows_zero(self) -> None:
        decomposer = PIDDecomposer({})

        normalized = decomposer._adaptive_normalize(np.array([0.0, 10.0, 0.0, -5.0]))

        self.assertEqual(normalized[0], 0.0)
        self.assertEqual(normalized[2], 0.0)
        self.assertGreater(normalized[1], 0.0)
        self.assertLess(normalized[3], 0.0)

    def test_decompose_sample_returns_closed_pid_terms(self) -> None:
        sample = DailySample(
            stock_code="000001.SZ",
            transaction_date="20260710",
            rows=[
                {
                    "window_id": "10",
                    "deal_amount": "3000000",
                    "signal_deal_buy_amount": "2200000",
                    "signal_deal_sell_amount": "800000",
                    "cb_cancel_order_ratio": "0.10",
                    "rs_burst_ratio": "0.60",
                    "pi_max_price_impact_pct": "0.012",
                },
                {
                    "window_id": "45",
                    "deal_amount": "2500000",
                    "signal_deal_buy_amount": "400000",
                    "signal_deal_sell_amount": "2100000",
                    "cb_cancel_order_ratio": "0.08",
                    "rs_burst_ratio": "0.70",
                    "pi_max_price_impact_pct": "0.018",
                },
            ],
            feature_summary={},
        )
        decomposer = PIDDecomposer({})

        result = decomposer.decompose_sample(sample)

        self.assertEqual(len(result.c_p), 48)
        self.assertLessEqual(result.pid_closure_error, 1e-10)
        self.assertLessEqual(result.alloc_closure_error, 1e-10)
        self.assertIn(result.dominant_type, {"游资", "量化", "散户"})
        self.assertIn(result.dominant_intention, {"买入", "卖出", "中性"})

    def test_capital_sign_maps_to_intention(self) -> None:
        decomposer = PIDDecomposer({"pid_decomposer": {"capital_anchor_error_max": 999.0}})
        delta_p = np.zeros(48)
        u_ch = np.zeros(48)
        u_mix = np.zeros(48)
        ch_anchor = np.zeros(48)
        mix_qr = np.zeros(48)
        ch_anchor[-1] = 3.0
        mix_qr[-1] = 1.0

        result = decomposer._decompose_arrays(
            stock_code="000001.SZ",
            transaction_date="20260710",
            delta_p=delta_p,
            u_ch=u_ch,
            u_mix=u_mix,
            ch_anchor=ch_anchor,
            mix_qr=mix_qr,
        )

        self.assertEqual(result.dominant_type, "游资")
        self.assertEqual(result.dominant_intention, "买入")
        self.assertGreater(result.capital_ch[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
