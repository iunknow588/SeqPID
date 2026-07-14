from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pid_decomposer import PIDDecomposer, create_pid_decomposer
from pid_decomposer_4d import PIDDecomposer4D
from pid_decomposer_5d import PIDDecomposer5D
from schemas import DailySample


class PIDDecomposerTest(unittest.TestCase):
    def test_create_pid_decomposer_selects_concrete_module(self) -> None:
        self.assertIsInstance(create_pid_decomposer({"pid_decomposer": {"mode": "baseline_4d"}}), PIDDecomposer4D)
        self.assertIsInstance(create_pid_decomposer({"pid_decomposer": {"mode": "diag_5d"}}), PIDDecomposer5D)
        self.assertIsInstance(create_pid_decomposer({"pid_decomposer": {"mode": "full_5d"}}), PIDDecomposer5D)

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
        self.assertIn(result.mode, {"rule_base", "baseline_4d", "diag_5d", "full_5d"})
        self.assertTrue(np.array_equal(result.phi, result.inertia))
        self.assertTrue(np.array_equal(result.theta, result.damping))
        self.assertEqual(result.dominant_source, "capital_external_force")
        self.assertFalse(result.display_fields_used_for_dominant)
        self.assertIn(result.dominant_type, {"游资", "量化", "散户"})
        self.assertIn(result.dominant_intention, {"买入", "卖出", "中性"})

    def test_rule_anchor_does_not_override_external_force_capital(self) -> None:
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
        self.assertEqual(result.dominant_intention, "中性")
        self.assertEqual(result.capital_ch[-1], 0.0)

    def test_external_force_identity_closes_to_p_term(self) -> None:
        decomposer = PIDDecomposer({})
        delta_p = np.zeros(48)
        delta_p[10] = 0.01
        u_ch = np.zeros(48)
        u_mix = np.zeros(48)
        u_ch[9] = 2.0
        u_mix[9] = -1.0

        result = decomposer._decompose_arrays(
            stock_code="000001.SZ",
            transaction_date="20260710",
            delta_p=delta_p,
            u_ch=u_ch,
            u_mix=u_mix,
            ch_anchor=np.full(48, np.nan),
            mix_qr=np.full(48, np.nan),
        )

        self.assertLessEqual(result.capital_cp_identity_error, 1e-10)
        self.assertLessEqual(result.capital_ci_identity_error, 1e-10)
        self.assertLessEqual(result.capital_cd_identity_error, 1e-10)
        self.assertLessEqual(result.capital_identity_error, 1e-10)
        self.assertTrue(
            np.allclose(
                result.capital_ch + result.capital_mix,
                result.c_p,
            )
        )

    def test_baseline_4d_does_not_force_quant_or_retail_structural_label(self) -> None:
        decomposer = PIDDecomposer({})

        dominant = decomposer._determine_dominant(
            np.array([0.0, 0.1, 0.0]),
            np.array([0.0, 0.4, 0.3]),
            np.array([0.0, 0.2, 0.1]),
        )

        self.assertEqual(dominant["dominant_type"], "unknown")

    def test_mv_ratio_requested_applies_when_float_mv_available(self) -> None:
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
                    "float_mv": "150000000",
                }
            ],
            feature_summary={},
        )
        decomposer = PIDDecomposer({"u_source_type": "mv_ratio"})

        result = decomposer.decompose_sample(sample)

        self.assertEqual(result.u_basis_effective, "mv_ratio")
        self.assertTrue(result.mv_ratio_input_requested)
        self.assertTrue(result.mv_ratio_input_applied)
        self.assertAlmostEqual(result.u_ch_mv_ratio[10], result.u_ch_amount_ratio[10] * 3000000 / 150000000, places=12)

    def test_mv_ratio_requested_falls_back_without_float_mv(self) -> None:
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
                }
            ],
            feature_summary={},
        )
        decomposer = PIDDecomposer({"u_source_type": "mv_ratio"})

        result = decomposer.decompose_sample(sample)

        self.assertEqual(result.u_basis_effective, "amount")
        self.assertTrue(result.mv_ratio_input_requested)
        self.assertFalse(result.mv_ratio_input_applied)
        self.assertTrue(any("mv_ratio input requested" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
