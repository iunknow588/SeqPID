from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from order_lifecycle import OrderLifecycleResolver, time_value_to_seconds


class OrderLifecycleTest(unittest.TestCase):
    def test_direct_order_id_recovers_order_age(self) -> None:
        resolver = OrderLifecycleResolver(
            [
                {
                    "time": "93000000",
                    "order_id": "S1",
                    "side": "S",
                    "price": "100",
                    "volume": "1000",
                    "order_type": "A",
                }
            ]
        )

        result = resolver.lookup_order_age_minutes(
            {"sell_order_id": "S1"},
            trade_time_seconds=time_value_to_seconds("93600000"),
            active_sign=0,
            side_sign=1,
            trade_price="100",
            trade_volume=100,
        )

        self.assertTrue(result.lifecycle_recovered)
        self.assertEqual(result.recovery_method, "direct_order_id")
        self.assertEqual(result.order_age_minutes, 6.0)

    def test_fifo_price_queue_consumes_cancelled_and_filled_orders(self) -> None:
        resolver = OrderLifecycleResolver(
            [
                {"time": "93000000", "order_id": "A", "side": "S", "price": "100", "volume": "100", "order_type": "A"},
                {"time": "93100000", "order_id": "B", "side": "S", "price": "100", "volume": "100", "order_type": "A"},
                {"time": "93200000", "order_id": "A", "side": "S", "price": "100", "volume": "100", "order_type": "D"},
            ]
        )

        result = resolver.lookup_order_age_minutes(
            {},
            trade_time_seconds=time_value_to_seconds("93800000"),
            active_sign=0,
            side_sign=1,
            trade_price="100",
            trade_volume=100,
        )

        self.assertTrue(result.lifecycle_recovered)
        self.assertEqual(result.recovery_method, "fifo_price_queue")
        self.assertEqual(result.recovery_confidence, "medium")
        self.assertEqual(result.order_age_minutes, 7.0)

    def test_fifo_price_queue_normalizes_raw_level2_price(self) -> None:
        resolver = OrderLifecycleResolver(
            [
                {"time": "93000000", "order_id": "A", "side": "S", "price": "205800", "volume": "100", "order_type": "A"},
            ]
        )

        result = resolver.lookup_order_age_minutes(
            {},
            trade_time_seconds=time_value_to_seconds("93600000"),
            active_sign=0,
            side_sign=1,
            trade_price="20.58",
            trade_volume=100,
        )

        self.assertTrue(result.lifecycle_recovered)
        self.assertEqual(result.recovery_method, "fifo_price_queue")
        self.assertEqual(result.order_age_minutes, 6.0)

    def test_shenzhen_cancel_trade_removes_order_before_fifo_match(self) -> None:
        resolver = OrderLifecycleResolver(
            [
                {"time": "93000000", "order_id": "A", "side": "S", "price": "100", "volume": "100", "order_type": "A"},
                {"time": "93100000", "order_id": "B", "side": "S", "price": "100", "volume": "100", "order_type": "A"},
            ],
            [
                {"time": "93200000", "成交代码": "C", "叫卖序号": "A", "成交价格": "100", "成交数量": "100"},
            ],
        )

        result = resolver.lookup_order_age_minutes(
            {},
            trade_time_seconds=time_value_to_seconds("93800000"),
            active_sign=0,
            side_sign=1,
            trade_price="100",
            trade_volume=100,
        )

        self.assertTrue(result.lifecycle_recovered)
        self.assertEqual(result.recovery_method, "fifo_price_queue")
        self.assertEqual(result.order_age_minutes, 7.0)

    def test_unresolved_lifecycle_returns_low_confidence(self) -> None:
        resolver = OrderLifecycleResolver([])

        result = resolver.lookup_order_age_minutes(
            {},
            trade_time_seconds=time_value_to_seconds("93800000"),
            active_sign=0,
            side_sign=1,
            trade_price="100",
            trade_volume=100,
        )

        self.assertFalse(result.lifecycle_recovered)
        self.assertEqual(result.recovery_method, "order_lifecycle_unresolved")
        self.assertEqual(result.recovery_confidence, "low")
        self.assertIsNone(result.order_age_minutes)


if __name__ == "__main__":
    unittest.main()
