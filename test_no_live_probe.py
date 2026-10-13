"""Offline NO-side real-public-data smoke test (no API calls)."""
import unittest
from datetime import datetime, timedelta, timezone
import pandas as pd
from no_live_probe import prioritize_no_contracts, run_no_probe


class RealNoProbeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 16, tzinfo=timezone.utc)
        self.market_rows = pd.DataFrame([
            {"league":"CFB","ticker":"KXNCAAFGAME-26OCT15FOOBAR-BAR","no_bid_cents":59},
            {"league":"NFL","ticker":"KXNFLGAME-26OCT18ABC-ABC","no_bid_cents":41},
            {"league":"NFL","ticker":"KXNFLGAME-26OCT18ABC-ABC","no_bid_cents":40},
            {"league":"NFL","ticker":"KXNFLSEASON-FAKE","no_bid_cents":90},
            {"league":"CFB","ticker":"KXCFB-TEST-MARKET","no_bid_cents":99},
            {"league":"CFB","ticker":"KXNCAAFGAME-ZERO","no_bid_cents":0},
        ])

    def test_selects_no_side_only_and_dedupes(self):
        paths = prioritize_no_contracts(self.market_rows)
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0]["league"], "CFB")
        self.assertEqual(paths[0]["series_ticker"], "KXNCAAFGAME")
        self.assertEqual(paths[1]["league"], "NFL")

    def test_no_side_live_integration_never_uses_yes_book(self):
        calls = []
        def source(leagues, pages):
            calls.append(("discovery",tuple(leagues),pages))
            return self.market_rows
        def market(ticker):
            calls.append(("market",ticker))
            return {"ticker":ticker,"status":"active",
                    "updated_time":(self.now - timedelta(minutes=3)).isoformat()}
        def book(ticker):
            calls.append(("book",ticker))
            return {"yes_bids":[[99,500]],"no_bids":[[57,3]]}
        def fee(series):
            calls.append(("series",series))
            return {"ticker":series, "fee_type":"quadratic", "fee_multiplier":1.0}
        result = run_no_probe(discovery=source,metadata_fetch=market,
                              book_fetch=book,series_fetch=fee,now=self.now)
        self.assertEqual(result["status"],"NO BOOK PARSED — NO SIGNAL")
        self.assertEqual(result["side"],"NO")
        self.assertEqual(result["held_side_book_best_bid_cents"],57)
        self.assertEqual(result["covered_shares"],1)
        self.assertEqual(result["market_updated_age_minutes"],3)
        self.assertFalse(result["fee_schedule_verified"])
        self.assertFalse(result["orderbook_level_age_verified"])
        self.assertEqual(result["series_fee_multiplier"],1)
        self.assertEqual([x[0] for x in calls], ["discovery","market","book","series"])

    def test_fee_metadata_missing_does_not_block_book_parsing(self):
        result = run_no_probe(
            discovery=lambda a,b:self.market_rows,
            metadata_fetch=lambda t:{"ticker":t,"status":"open"},
            book_fetch=lambda t:{"yes_bids":[[99,5]],"no_bids":[[50,1]]},
            series_fetch=lambda t: (_ for _ in ()).throw(OSError("no series")),
            now=self.now)
        self.assertEqual(result["status"],"NO BOOK PARSED — NO SIGNAL")
        self.assertIsNone(result["series_fee_multiplier"])
        self.assertFalse(result["fee_schedule_verified"])
        self.assertFalse(result["orderbook_level_age_verified"])

    def test_closed_market_never_calls_orderbook(self):
        calls = []
        result = run_no_probe(
            discovery=lambda a,b:self.market_rows.head(1),
            metadata_fetch=lambda t:{"ticker":t,"status":"closed"},
            book_fetch=lambda t:calls.append(t),
            series_fetch=lambda t:calls.append(t),now=self.now)
        self.assertEqual(calls,[])
        self.assertEqual(result["status"],"NO QUALIFYING PUBLIC BID VERIFIED")

    def test_wrong_side_bid_does_not_value_no(self):
        result = run_no_probe(
            discovery=lambda a,b:self.market_rows.head(1),
            metadata_fetch=lambda t:{"ticker":t,"status":"open"},
            book_fetch=lambda t:{"yes_bids":[[99,500]],"no_bids":[]},
            series_fetch=lambda t:{"ticker":t.split("-")[0],"fee_type":"quadratic",
                                   "fee_multiplier":1},now=self.now)
        self.assertEqual(result["status"],"NO BOOK EMPTY — NO SIGNAL")
        self.assertIsNone(result["held_side_book_best_bid_cents"])
        self.assertEqual(result["covered_shares"],0)

    def test_no_book_bad_shape_is_not_reported_as_empty_verified(self):
        result = run_no_probe(
            discovery=lambda a,b:self.market_rows.head(1),
            metadata_fetch=lambda t:{"ticker":t,"status":"open"},
            book_fetch=lambda t:{"yes_bids":[],"no_bids":[[55,-1]]},
            series_fetch=lambda t:{"ticker":"KXNCAAFGAME","fee_type":"quadratic",
                                   "fee_multiplier":1},now=self.now)
        self.assertEqual(result["status"],"NO ORDERBOOK INVALID — NO SIGNAL")
        self.assertEqual(result["covered_shares"],0)

if __name__=="__main__":
    unittest.main()
