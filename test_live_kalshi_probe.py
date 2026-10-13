"""Offline validation of bounded Kalshi public live integration probe.

All market calls are injected fixtures. Tests never use public internet,
sportsbook APIs, account credentials, or trade execution.
"""
import unittest

import pandas as pd

from live_kalshi_probe import prioritize_markets, run_probe


class LiveKalshiProbeTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame([
            {"league": "NFL", "ticker": "KXNFLGAME-26OCT11AAA-BBB",
             "event": "Test Match", "yes_bid_cents": 70, "no_bid_cents": 25,
             "volume": 100},
            {"league": "CFB", "ticker": "KXNCAAFGAME-26OCT13CC-DD",
             "event": "Second Match", "yes_bid_cents": 0, "no_bid_cents": 43,
             "volume": 20},
            {"league": "NFL", "ticker": "KXNFLGAME-26OCT11AAA-BBB",
             "event": "Duplicate", "yes_bid_cents": 70, "no_bid_cents": 25},
            {"league": "NFL", "ticker": "KXNFLSEASON-NOTGAME",
             "event": "Wrong market", "yes_bid_cents": 90, "no_bid_cents": 5},
            {"league": "CFB", "ticker": "KXCFB-TEST-MARKET",
             "event": "Fake", "yes_bid_cents": 99, "no_bid_cents": 0},
            {"league": "NFL", "ticker": "KXNFLGAME-26OCT11EMPTY-ONE",
             "event": "No bids", "yes_bid_cents": 0, "no_bid_cents": 0},
        ])

    def test_candidate_selection_is_exact_unique_game_series(self):
        routes = prioritize_markets(self.sample())
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0]["ticker"], "KXNFLGAME-26OCT11AAA-BBB")
        self.assertEqual(routes[0]["side"], "YES")
        self.assertEqual(routes[1]["side"], "NO")
        self.assertNotIn("KXCFB-TEST-MARKET", str(routes))

    def test_live_contract_readonly_fixture(self):
        calls = []
        def market_source(leagues, pages):
            calls.append(("events", tuple(leagues), pages))
            return self.sample()
        def metadata(t):
            calls.append(("market", t))
            return {"ticker": t, "status": "open"}
        def orderbook(t):
            calls.append(("book", t))
            return {"yes_bids": [[72, 5]], "no_bids": [[26, 12]]}
        result = run_probe(
            market_source=market_source,
            metadata_source=metadata,
            orderbook_source=orderbook,
        )
        self.assertEqual(result["status"], "READ_ONLY_BOOK_PARSED — NO EXIT SIGNAL")
        self.assertEqual(result["covered_shares"], 1)
        self.assertEqual(result["best_bid_cents"], 72)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["ledger_changes"], 0)
        self.assertEqual(result["sportsbook_requests"], 0)
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["source_quote_age_verified"])

    def test_closed_market_skips_orderbook_and_tries_next(self):
        calls = []
        def metadata(t):
            calls.append(("market", t))
            return {"ticker": t, "status": "closed" if "NFL" in t else "open"}
        def orderbook(t):
            calls.append(("book", t))
            return {"yes_bids": [[70, 3]], "no_bids": [[43, 4]]}
        result = run_probe(market_source=lambda l, p: self.sample(),
                           metadata_source=metadata, orderbook_source=orderbook)
        self.assertEqual(result["league"], "CFB")
        self.assertEqual(result["status"], "READ_ONLY_BOOK_PARSED — NO EXIT SIGNAL")
        self.assertEqual(sum(c[0] == "market" for c in calls), 2)
        self.assertEqual(sum(c[0] == "book" for c in calls), 1)

    def test_closed_or_missing_markets_cannot_claim_live_verified(self):
        empty = run_probe(market_source=lambda leagues, pages: pd.DataFrame(),
                          metadata_source=lambda t: self.fail("No metadata expected"),
                          orderbook_source=lambda t: self.fail("No book expected"))
        self.assertEqual(empty["status"], "NO OPEN WELL-QUOTED MARKETS FOUND")
        self.assertEqual(empty["markets_probed"], 0)
        self.assertNotIn("ticker", empty)

    def test_mismatched_ticker_is_not_successful(self):
        out = run_probe(market_source=lambda l, p: self.sample().head(1),
                        metadata_source=lambda t: {"ticker": "WRONG", "status": "open"},
                        orderbook_source=lambda t: self.fail("No order book for bad metadata"))
        self.assertNotIn("READ_ONLY_BOOK_PARSED", out["status"])
        self.assertEqual(out["markets_probed"], 1)
        self.assertEqual(out["sportsbook_requests"], 0)

    def test_explicit_no_side_live_probe_uses_no_bids(self):
        calls = []
        t = (self.now_for_audit() - __import__("datetime").timedelta(minutes=2)).isoformat()
        def meta(ticker):
            calls.append(("market", ticker))
            return {"ticker": ticker, "status": "active", "updated_time": t}
        def book(ticker):
            calls.append(("book", ticker))
            return {"yes_bids": [[92, 15]], "no_bids": [[43, 4]]}
        def series(ticker):
            calls.append(("series", ticker))
            return {"ticker": ticker, "fee_type": "quadratic_with_maker_fees",
                    "fee_multiplier": 1}
        out = run_probe(
            market_source=lambda leagues, pages: self.sample(),
            metadata_source=meta, orderbook_source=book,
            side_preference="NO", series_source=series)
        self.assertEqual(out["requested_held_side"], "NO")
        self.assertEqual(out["side"], "NO")
        self.assertEqual(out["league"], "CFB")
        self.assertEqual(out["best_bid_cents"], 43)
        self.assertEqual(out["covered_shares"], 1)
        self.assertIn("BOOK_PARSED", out["status"])
        self.assertEqual(out["series_fee_type"], "quadratic_with_maker_fees")
        self.assertEqual(out["series_fee_multiplier"], 1)
        self.assertFalse(out["fee_schedule_verified"])
        self.assertFalse(out["orderbook_level_age_verified"])
        self.assertEqual([x[0] for x in calls], ["market", "book", "series"])

    @staticmethod
    def now_for_audit():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)

    def test_no_side_candidate_requires_positive_no_bid(self):
        choices = prioritize_markets(self.sample(), side_preference="NO")
        self.assertEqual(len(choices), 2)
        self.assertTrue(all(x["side"] == "NO" for x in choices))
        self.assertEqual(choices[0]["ticker"], "KXNCAAFGAME-26OCT13CC-DD")
        with self.assertRaises(ValueError):
            prioritize_markets(self.sample(), side_preference="WRONG")

    def test_empty_held_side_book_remains_unverified(self):
        out = run_probe(market_source=lambda l, p: self.sample().head(1),
                        metadata_source=lambda t: {"ticker": t, "status": "open"},
                        orderbook_source=lambda t: {"yes_bids": [], "no_bids": [[99, 50]]})
        self.assertEqual(out["status"], "READ_ONLY_BOOK_EMPTY — NO EXIT SIGNAL")
        self.assertEqual(out["covered_shares"], 0)
        self.assertIsNone(out["best_bid_cents"])
        self.assertFalse(out["execution_verified"])

    def test_public_book_failure_does_not_create_position(self):
        out = run_probe(market_source=lambda l, p: self.sample().head(1),
                        metadata_source=lambda t: {"ticker": t, "status": "open"},
                        orderbook_source=lambda t: (_ for _ in ()).throw(RuntimeError("No data")))
        self.assertEqual(out["status"], "PUBLIC LOOKUP FAILED OR MARKETS CHANGED")
        self.assertEqual(out["ledger_changes"], 0)
        self.assertEqual(out["sportsbook_requests"], 0)


if __name__ == "__main__":
    unittest.main()
