from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from batch_alerts import build_batch_warnings, collect_missing_symbols, format_incomplete_stock_warning
from schemas import DailySample


class BatchAlertsTest(unittest.TestCase):
    def test_collect_missing_symbols_uses_requested_order(self) -> None:
        samples = [
            DailySample("000001.SZ", "20260710", [], {}),
            DailySample("000003.SZ", "20260710", [], {}),
        ]
        missing = collect_missing_symbols(["000002.SZ", "000001.SZ", "000004.SZ"], samples)
        self.assertEqual(missing, ["000002.SZ", "000004.SZ"])

    def test_build_batch_warnings_combines_expected_messages(self) -> None:
        warnings = build_batch_warnings(
            samples=[],
            missing_symbols=["000002.SZ"],
            incomplete_stock_dirs={"000003.SZ": ["orders", "snapshots"]},
            imputed_symbols=["000002.SZ"],
        )
        self.assertEqual(len(warnings), 4)
        self.assertIn("No reference feature rows found", warnings[0])
        self.assertIn("Missing raw data for requested symbols: 000002.SZ", warnings[1])
        self.assertIn("000003.SZ(orders,snapshots)", warnings[2])
        self.assertIn("Imputed missing symbols with market-average defaults: 000002.SZ", warnings[3])

    def test_format_incomplete_stock_warning_sorts_symbols(self) -> None:
        warning = format_incomplete_stock_warning(
            {
                "000003.SZ": ["snapshots"],
                "000001.SZ": ["orders"],
            }
        )
        self.assertEqual(warning, "Skipped incomplete stock dirs: 000001.SZ(orders); 000003.SZ(snapshots)")


if __name__ == "__main__":
    unittest.main()
