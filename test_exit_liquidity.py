"""Offline tests for held-side Kalshi bid depth — NO network or trading."""
import unittest
from datetime import datetime, timedelta, timezone

from edge_engine import taker_fee
from exit_liquidity import (
    estimate_exit, review_public_position, snapshot_integrity, _bid_levels,
)


class ExitDepthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 11, 16, 30, tzinfo=timezone.utc)
        self.position = {
            "position_id": "a" * 32, "ticker": "KXNCAAFGAME-EXAMPLE",
            "side": "YES", "remaining_shares": 4,
            "remaining_cost_usd": 2.48,
        }
        self.market = {"ticker": self.position["ticker"], "status": "open"}
        self.book = {
            "yes_bids": [[72, 3], [70, 1], [66, 20]],
            "no_bids": [[95, 300]],
        }

    def test_selling_yes_uses_yes_bids_not_no_asks(self):
        result = estimate_exit(self.position, self.market, self.book, observed_at=self.now)
        self.assertEqual(result["best_bid_cents"], 72)
        self.assertEqual(result["side"], "YES")
        self.assertTrue(result["depth_complete"])
        self.assertEqual(result["covered_shares"], 4)
        self.assertEqual(result["remaining_after_review"], 0)
        self.assertAlmostEqual(result["gross_proceeds_usd"], 2.86)
        fee = taker_fee(72, 3) + taker_fee(70, 1)
        self.assertAlmostEqual(result["estimated_exit_fee_usd"], fee)
        self.assertAlmostEqual(result["net_proceeds_usd"], 2.86-fee)
        self.assertAlmostEqual(result["hypothetical_net_pnl_usd"], 2.86-fee-2.48)
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["fee_schedule_verified"])
        self.assertIn("NOT a guaranteed fill", result["reason"])

    def test_selling_no_uses_no_bids_not_yes_bids(self):
        pos = dict(self.position, side="NO")
        book = {"yes_bids": [[99, 300]], "no_bids": [[57, 4]]}
        r = estimate_exit(pos, self.market, book, requested_shares=2, observed_at=self.now)
        self.assertEqual(r["best_bid_cents"], 57)
        self.assertEqual(r["covered_shares"], 2)
        self.assertEqual(r["requested_shares"], 2)
        self.assertAlmostEqual(r["gross_proceeds_usd"], 1.14)

    def test_partial_sell_uses_proportion_of_remaining_basis(self):
        r = estimate_exit(self.position, self.market, self.book, requested_shares=2,
                          observed_at=self.now)
        self.assertEqual(r["remaining_after_review"], 2)
        self.assertAlmostEqual(r["allocated_entry_cost_usd"], 1.24)
        fee = taker_fee(72, 2)
        self.assertAlmostEqual(r["hypothetical_net_pnl_usd"], 1.44-fee-1.24)

    def test_insufficient_depth_never_values_missing_shares(self):
        book = {"yes_bids": [[72, 2]], "no_bids": [[99, 300]]}
        r = estimate_exit(self.position, self.market, book, observed_at=self.now)
        self.assertFalse(r["depth_complete"])
        self.assertEqual(r["covered_shares"], 2)
        self.assertEqual(r["remaining_after_review"], 2)
        self.assertAlmostEqual(r["gross_proceeds_usd"], 1.44)
        self.assertIn("ONLY 2/4 shares", r["reason"])
        self.assertIn("UNVERIFIED", r["status"])

    def test_no_held_side_bids_no_value(self):
        r = estimate_exit(self.position, self.market,
                          {"yes_bids": [], "no_bids": [[99, 100]]},
                          observed_at=self.now)
        self.assertIsNone(r["best_bid_cents"])
        self.assertEqual(r["covered_shares"], 0)
        self.assertIsNone(r["hypothetical_net_pnl_usd"])
        self.assertIn("No resting bids", r["reason"])

    def test_malformed_orderbook_and_fractional_shares_fail_closed(self):
        for raw in ([[70.5, .25]], [[float("nan"), 2]], [[90, float("inf")]],
                    [[91, -1]], [[105, 3]], "bad", None):
            with self.subTest(raw=raw):
                book = {"yes_bids": raw, "no_bids": []}
                r = estimate_exit(self.position, self.market, book, observed_at=self.now)
                self.assertEqual(r["status"], "UNVERIFIED — NO EXIT SIGNAL")
                self.assertIsNone(r["net_proceeds_usd"])

    def test_metadata_mismatch_or_closed_market_never_fetches_book(self):
        for market in ({"ticker": "WRONG", "status": "open"},
                       {"ticker": self.position["ticker"], "status": "closed"}):
            calls = []
            r = review_public_position(
                self.position, market_fetch=lambda t: market,
                book_fetch=lambda t: calls.append(t), observed_at=self.now)
            self.assertEqual(calls, [])
            self.assertIsNone(r["net_proceeds_usd"])
            self.assertIn("UNVERIFIED", r["status"])

    def test_one_manually_triggered_request_path_no_sportsbook(self):
        calls = []
        def market_fetch(ticker):
            calls.append(("market", ticker))
            return self.market
        def book_fetch(ticker):
            calls.append(("book", ticker))
            return self.book
        r = review_public_position(self.position, market_fetch=market_fetch,
                                   book_fetch=book_fetch, observed_at=self.now)
        self.assertEqual(calls, [("market", self.position["ticker"]),
                                 ("book", self.position["ticker"])])
        self.assertEqual(r["covered_shares"], 4)

    def test_failed_get_or_fake_ticker_gives_no_signal(self):
        def fail(_):
            raise OSError("public feed unavailable")
        r = review_public_position(self.position, market_fetch=fail,
                                   book_fetch=lambda _: self.book, observed_at=self.now)
        self.assertIn("lookup failed", r["reason"])
        self.assertIsNone(r["best_bid_cents"])
        self.assertFalse(r["execution_verified"])

    def test_stale_snapshot_and_changed_position_fail_integrity(self):
        r = estimate_exit(self.position, self.market, self.book, observed_at=self.now)
        fresh, msg = snapshot_integrity(r, self.position,
                                        now=self.now + timedelta(seconds=20))
        self.assertTrue(fresh)
        self.assertIn("NOT verified", msg)
        stale, msg = snapshot_integrity(r, self.position,
                                        now=self.now + timedelta(minutes=4))
        self.assertFalse(stale)
        self.assertIn("stale", msg)
        changed = dict(self.position, remaining_shares=2)
        check, msg = snapshot_integrity(r, changed, now=self.now)
        self.assertFalse(check)
        self.assertIn("changed", msg)

    def test_more_than_held_quantity_rejected_and_not_sent(self):
        calls=[]
        r = review_public_position(self.position, requested_shares=5,
                                   market_fetch=lambda t: calls.append(t),
                                   book_fetch=lambda t: calls.append(t), observed_at=self.now)
        self.assertEqual(calls, [])
        self.assertIn("requested quantity", r["reason"].lower())

    def test_sort_and_aggregate_bid_levels_descending(self):
        r = _bid_levels({"yes_bids": [[50, 2], [60, 2], [60, 3]],
                         "no_bids": []}, "YES")
        self.assertEqual([(float(p), q) for p, q in r], [(60.0, 5), (50.0, 2)])


if __name__ == "__main__":
    unittest.main()
