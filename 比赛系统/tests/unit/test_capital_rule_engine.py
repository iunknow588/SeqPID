from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import capital_rule_engine


class CapitalRuleEngineTest(unittest.TestCase):
    def test_large_active_event_goes_to_ch_rule(self) -> None:
        event = capital_rule_engine.build_rule_event(
            event_time="93000000",
            signed_amount=600000.0,
            side="buy",
            scene="continuous",
            is_active=True,
            is_large=True,
        )
        feature = capital_rule_engine.initialize_rule_window_feature(0)

        capital_rule_engine.apply_event_to_window(feature, event)

        self.assertEqual(event.capital_type_rule, "hot_money")
        self.assertEqual(feature.CH_rule_t, 600000.0)
        self.assertEqual(feature.Q_rule_t, 0.0)
        self.assertEqual(feature.R_seed_t, 0.0)

    def test_passive_age_threshold_splits_quant_and_retail(self) -> None:
        quant = capital_rule_engine.build_rule_event(
            event_time="100000000",
            signed_amount=120000.0,
            side="buy",
            scene="continuous",
            is_active=False,
            is_large=False,
            order_age_minutes=5.0,
        )
        retail = capital_rule_engine.build_rule_event(
            event_time="100500000",
            signed_amount=-80000.0,
            side="sell",
            scene="continuous",
            is_active=False,
            is_large=False,
            order_age_minutes=5.1,
        )
        feature = capital_rule_engine.initialize_rule_window_feature(1)

        capital_rule_engine.apply_event_to_window(feature, quant)
        capital_rule_engine.apply_event_to_window(feature, retail)

        self.assertEqual(quant.capital_type_rule, "quant")
        self.assertEqual(retail.capital_type_rule, "retail")
        self.assertEqual(feature.Q_rule_t, 120000.0)
        self.assertEqual(feature.R_seed_t, -80000.0)

    def test_missing_order_age_falls_back_to_low_conf_quant(self) -> None:
        event = capital_rule_engine.build_rule_event(
            event_time="92500000",
            signed_amount=50000.0,
            side="buy",
            scene="call_auction",
            is_active=False,
            is_large=False,
            order_age_minutes=None,
        )
        feature = capital_rule_engine.initialize_rule_window_feature(2)

        capital_rule_engine.apply_event_to_window(feature, event)

        self.assertEqual(event.capital_type_rule, "quant")
        self.assertEqual(event.fallback_reason, "order_age_missing")
        self.assertEqual(feature.Q_rule_t, 50000.0)


if __name__ == "__main__":
    unittest.main()
