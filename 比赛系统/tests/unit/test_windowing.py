from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import windowing


class WindowingTest(unittest.TestCase):
    def test_time_to_window_id_handles_session_boundaries(self) -> None:
        cases = {
            "092959000": None,
            "093000000": 0,
            "112959000": 23,
            "113000000": None,
            "125959000": None,
            "130000000": 24,
            "145959000": 47,
            "150000000": 47,
        }
        for raw_time, expected in cases.items():
            with self.subTest(raw_time=raw_time):
                self.assertEqual(windowing.time_to_window_id(raw_time), expected)

    def test_initialize_pid_buckets_uses_stable_schema(self) -> None:
        buckets = windowing.initialize_pid_buckets(window_count=2)

        self.assertEqual([bucket["window_id"] for bucket in buckets], ["0", "1"])
        self.assertEqual(buckets[0]["deal_amount"], 0.0)
        self.assertEqual(buckets[0]["signed_large_active_amount"], 0.0)
        self.assertEqual(buckets[0]["CH_rule_t"], 0.0)
        self.assertEqual(buckets[0]["Q_rule_t"], 0.0)
        self.assertEqual(buckets[0]["R_seed_t"], 0.0)
        self.assertEqual(buckets[0]["window_trade_count"], 0)
        self.assertEqual(buckets[0]["active_inferred_count"], 0)


if __name__ == "__main__":
    unittest.main()
