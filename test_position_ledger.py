"""Offline, deterministic tests of manual PAPER fills, exits and CSV restore."""
import csv
import io
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd

from position_ledger import (
    COLUMNS, empty_ledger, export_ledger, import_ledger, ledger_summary,
    open_positions, record_entry, record_exit, validate_ledger,
)


class PaperPositionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 11, 13, 0, tzinfo=timezone.utc)
        self.entries = empty_ledger()

    def buy(self, ledger=None, **overrides):
        params = dict(league="CFB", event="Alpha vs Beta", outcome_team="Alpha",
                      ticker="KXCFB-ALPHA-BETA", side="YES", shares=5,
                      price_cents=60, fee_usd="0.10", bankroll=500,
                      recorded_at=self.start,
                      notes="Manually entered hypothetical fill")
        params.update(overrides)
        return record_entry(self.entries if ledger is None else ledger, **params)

    def test_entry_not_inferred_from_scans(self):
        self.assertEqual(ledger_summary(self.entries)["positions_total"], 0)
        filled = self.buy()
        summary = ledger_summary(filled)
        self.assertEqual(summary["transactions"], 1)
        self.assertEqual(summary["open_positions"], 1)
        self.assertEqual(summary["remaining_shares"], 5)
        self.assertAlmostEqual(summary["open_cost_usd"], 3.10)
        self.assertFalse(summary["has_exits"])
        self.assertAlmostEqual(summary["realized_net_usd"], 0.0)
        self.assertEqual(open_positions(filled).iloc[0]["entry_cents"], 60)

    def test_partial_and_final_exit_correctly_allocate_entry_fees(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        ledger = record_exit(ledger, pid, shares=2, price_cents=75,
                             fee_usd="0.04", recorded_at=self.start + timedelta(minutes=1))
        summary = ledger_summary(ledger)
        self.assertEqual(summary["open_positions"], 1)
        self.assertEqual(summary["remaining_shares"], 3)
        self.assertAlmostEqual(summary["open_cost_usd"], 1.86)
        # 2*0.75-0.04-(2/5*3.10) = 0.22
        self.assertAlmostEqual(summary["realized_net_usd"], 0.22)
        ledger = record_exit(ledger, pid, shares=3, price_cents=40,
                             fee_usd="0.03", recorded_at=self.start + timedelta(minutes=2))
        summary = ledger_summary(ledger)
        self.assertEqual(summary["closed_positions"], 1)
        self.assertEqual(summary["open_positions"], 0)
        self.assertEqual(summary["remaining_shares"], 0)
        self.assertEqual(summary["open_cost_usd"], 0)
        # 1.20-.03-1.86 = -0.69 => overall -0.47
        self.assertAlmostEqual(summary["realized_net_usd"], -0.47)

    def test_over_sell_or_duplicate_entry_rejected(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        with self.assertRaisesRegex(ValueError, "more shares"):
            record_exit(ledger, pid, shares=6, price_cents=80, fee_usd="0.01")
        with self.assertRaisesRegex(ValueError, "Position ID already"):
            validate_ledger(pd.concat([ledger, ledger], ignore_index=True).assign(
                transaction_id=["f"*32, "e"*32]))

    def test_fraudulent_csv_exit_side_rejected(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        ledger = record_exit(ledger, pid, shares=2, price_cents=80,
                             fee_usd="0.04", recorded_at=self.start + timedelta(minutes=2))
        altered = ledger.copy()
        altered.loc[1, "side"] = "NO"
        with self.assertRaisesRegex(ValueError, "does not exactly match"):
            validate_ledger(altered)

    def test_timestamp_regression_and_exit_without_entry_rejected(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        with self.assertRaisesRegex(ValueError, "timestamp before"):
            record_exit(ledger, pid, shares=1, price_cents=80, fee_usd=0,
                        recorded_at=self.start - timedelta(minutes=1))
        exit_row = ledger.iloc[0].to_dict()
        exit_row.update({
            "transaction_id": "a"*32, "position_id": "b"*32,
            "action": "EXIT", "shares": 1
        })
        with self.assertRaisesRegex(ValueError, "Exit without an entry"):
            validate_ledger(pd.DataFrame([exit_row], columns=COLUMNS))

    def test_single_position_and_split_same_ticker_capped(self):
        with self.assertRaisesRegex(ValueError, "1%"):
            self.buy(shares=9)
        ledger = self.buy(shares=5)
        with self.assertRaisesRegex(ValueError, "per-market"):
            self.buy(ledger, shares=4, fee_usd=0,
                     recorded_at=self.start + timedelta(minutes=1))
        # An unrelated market remains possible if within total exposure.
        ledger = self.buy(ledger, shares=4, fee_usd=0,
                          ticker="KXCFB-GAMMA-DELTA",
                          event="Gamma vs Delta", outcome_team="Gamma",
                          recorded_at=self.start + timedelta(minutes=2))
        self.assertEqual(ledger_summary(ledger)["open_positions"], 2)

    def test_total_exposure_including_other_and_queued_capped(self):
        with self.assertRaisesRegex(ValueError, "3%"):
            self.buy(other_exposure=12.50)
        with self.assertRaisesRegex(ValueError, "3%"):
            self.buy(queued_exposure=13.0)
        self.assertEqual(ledger_summary(self.buy(other_exposure=3.0))["open_positions"], 1)

    def test_exit_never_triggers_trade_or_buy_checks(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        ledger = record_exit(ledger, pid, shares=5, price_cents=95,
                             fee_usd=0, recorded_at=self.start + timedelta(minutes=10))
        self.assertEqual(ledger_summary(ledger)["closed_positions"], 1)
        self.assertEqual(ledger_summary(ledger)["open_cost_usd"], 0)

    def test_roundtrip_export_import_preserves_events_and_ids(self):
        ledger = self.buy()
        pid = open_positions(ledger).iloc[0]["position_id"]
        ledger = record_exit(ledger, pid, shares=3, price_cents=85, fee_usd="0.05",
                             recorded_at=self.start + timedelta(minutes=1))
        raw = export_ledger(ledger)
        imported = import_ledger(raw)
        pd.testing.assert_frame_equal(validate_ledger(ledger), imported)
        self.assertEqual(export_ledger(imported), raw)
        self.assertEqual(ledger_summary(imported), ledger_summary(ledger))

    def test_empty_csv_roundtrip(self):
        raw = export_ledger(empty_ledger())
        self.assertEqual(ledger_summary(import_ledger(raw))["transactions"], 0)

    def test_duplicate_ids_and_csv_tampering_fail(self):
        ledger = self.buy()
        duplicated = pd.concat([ledger, ledger], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Duplicate transaction ID"):
            validate_ledger(duplicated)
        with self.assertRaisesRegex(ValueError, "wrong columns"):
            import_ledger(b"position_id,side\nfake,YES\n")
        with self.assertRaisesRegex(ValueError, "version"):
            altered = ledger.copy()
            altered.loc[0, "schema_version"] = "200"
            validate_ledger(altered)
        with self.assertRaisesRegex(ValueError, "Malformed CSV"):
            import_ledger(export_ledger(ledger) + b"extra,trailing,unstructured,record\n")

    def test_price_fee_quantity_and_formula_validation(self):
        for kwargs in (
            {"shares": 0}, {"shares": 1.5}, {"price_cents": 0},
            {"price_cents": 100}, {"price_cents": 54.5}, {"fee_usd": "-0.01"},
            {"fee_usd": "NaN"}, {"ticker": "bad ticker"},
            {"event": "=SUM(A1)"}, {"notes": "+evil"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.buy(**kwargs)

    def test_no_duplicate_opposing_side_cap_evasion(self):
        ledger = self.buy(shares=5)
        with self.assertRaisesRegex(ValueError, "per-market"):
            self.buy(ledger, shares=5, fee_usd=0, side="NO",
                     recorded_at=self.start + timedelta(minutes=1))

    def test_fail_closed_on_missing_ledger_fields(self):
        with self.assertRaisesRegex(ValueError, "columns"):
            validate_ledger(pd.DataFrame([{"ticker": "FAKE"}]))
        with self.assertRaises(ValueError):
            import_ledger("not bytes")
        with self.assertRaisesRegex(ValueError, "below 2 MB"):
            import_ledger(b"x" * 2_000_001)


if __name__ == "__main__":
    unittest.main()
