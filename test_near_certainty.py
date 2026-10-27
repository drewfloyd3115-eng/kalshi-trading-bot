"""Offline regression and UI smoke tests for the near-certainty paper scanner."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pandas as pd

from near_certainty import watchlist, inspect_one_share


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        now=datetime(2026,10,26,12,tzinfo=timezone.utc)
        self.now=now
        self.markets=pd.DataFrame([
            {"league":"NFL","event":"A vs B","ticker":"KXNFLGAME-ABC","yes_ask_cents":95.0,
             "no_ask_cents":6.0,"volume":100, "close_time":(now+timedelta(hours=1)).isoformat()},
            {"league":"CFB","event":"C vs D","ticker":"KXNCAAFGAME-CD","yes_ask_cents":4.0,
             "no_ask_cents":97.0,"volume":50, "close_time":(now+timedelta(hours=2)).isoformat()},
            {"league":"NFL","event":"Expired","ticker":"KXNFLGAME-OLD","yes_ask_cents":97.0,
             "no_ask_cents":4.0,"volume":50, "close_time":(now-timedelta(hours=2)).isoformat()},
            {"league":"NFL","event":"Invalid price","ticker":"KXNFLGAME-NAN","yes_ask_cents":float("nan"),
             "no_ask_cents":98.0,"volume":50, "close_time":(now+timedelta(hours=2)).isoformat()},
        ])

    def test_expected_yes_and_no_with_expiry_and_nan_filtered(self):
        results=watchlist(self.markets,now=self.now)
        self.assertEqual(set(zip(results["ticker"],results["side"])),{
            ("KXNFLGAME-ABC","YES"),("KXNCAAFGAME-CD","NO"),("KXNFLGAME-NAN","NO")})
        self.assertTrue(results["status"].str.contains("WATCH ONLY").all())

    def test_bounded_and_empty_results(self):
        self.assertTrue(watchlist(pd.DataFrame()).empty)
        self.assertEqual(len(watchlist(self.markets,limit=1,now=self.now)),1)
        with self.assertRaises(ValueError):
            watchlist(self.markets,lower=99,upper=90)

    def test_outside_target_range_rejected(self):
        self.assertTrue(watchlist(self.markets,lower=80,upper=89,now=self.now).empty)


class OneShareRiskTests(unittest.TestCase):
    def test_yes_95cent_opposite_no_bid_and_fee(self):
        result=inspect_one_share({"yes_bids":[],"no_bids":[[5,10]]},"YES")
        self.assertEqual(result["indicative_ask_cents"],95)
        self.assertEqual(result["assumed_fee_usd"],0.01)
        self.assertAlmostEqual(result["cost_usd"],0.96)
        self.assertEqual(result["required_probability_for_5pp_pct"],101)
        self.assertIn("Fails +5 percentage-point net edge threshold",
                      inspect_one_share({"yes_bids":[],"no_bids":[[5,10]]},"YES",
                                        fair_probability=1)["blockers"])
        self.assertFalse(result["real_order_placed"])
        self.assertFalse(result["paper_fill_recorded"])

    def test_no_side_uses_yes_bids_not_no_bids(self):
        result=inspect_one_share({"yes_bids":[[6,8]],"no_bids":[[99,100]]},"NO")
        self.assertEqual(result["indicative_ask_cents"],94)

    def test_one_share_90cent_97_percent_is_preliminary_only(self):
        result=inspect_one_share({"no_bids":[[10,5]],"yes_bids":[]},"YES",
                                 fair_probability=0.97)
        self.assertEqual(result["indicative_ask_cents"],90)
        self.assertAlmostEqual(result["cost_usd"],0.91)
        self.assertEqual(result["net_edge_pp"],6)
        self.assertEqual(result["expected_value_usd"],0.06)
        self.assertEqual(result["status"],"WATCH ONLY — UNVERIFIED")
        self.assertEqual(len(result["blockers"]),1)
        self.assertIn("unverified",result["blockers"][0])

    def test_99cent_contract_fee_wipes_out_profit(self):
        result=inspect_one_share({"no_bids":[[1,20]],"yes_bids":[]},"YES",
                                 fair_probability=1)
        self.assertAlmostEqual(result["cost_usd"],1)
        self.assertAlmostEqual(result["profit_if_wins_usd"],0)
        self.assertEqual(result["maximum_possible_edge_pp"],0)

    def test_exposure_blocks_one_share(self):
        result=inspect_one_share({"no_bids":[[10,20]]},"YES",open_exposure=2.5,
                                 fair_probability=1)
        self.assertTrue(any("Aggregate" in s for s in result["blockers"]))

    def test_fractional_only_book_does_not_create_whole_share(self):
        result=inspect_one_share({"no_bids":[[5,0.7],[6,0.5]]},"YES")
        self.assertEqual(result["status"],"NO DEPTH — WATCH ONLY")
        self.assertFalse(result["paper_fill_recorded"])

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            inspect_one_share({"yes_bids":[]},"NO",fair_probability=float("nan"))
        with self.assertRaises(ValueError):
            inspect_one_share({"yes_bids":[]},"INVALID")
        with self.assertRaises(ValueError):
            inspect_one_share({"yes_bids":[]},"NO",bankroll=0)
        with self.assertRaises(ValueError):
            inspect_one_share({"yes_bids":None},"NO")


class AppIntegrationTests(unittest.TestCase):
    def test_mobile_page_loads_without_network(self):
        from streamlit.testing.v1 import AppTest
        with patch("scanner.fetch_sports_markets",side_effect=AssertionError("Network on page load")):
            app=AppTest.from_file("app.py",default_timeout=30).run()
            self.assertFalse(app.exception,str(app.exception))
            app=app.button_group(key="sports_nav").set_value("Near Certainty").run()
            self.assertFalse(app.exception,str(app.exception))
            self.assertIn("Near-Certainty", " ".join(str(s.value) for s in app.subheader))
            self.assertIn("no proven +EV", " ".join(str(a.value) for a in app.warning))
            self.assertEqual(float(app.session_state.get("quick_bankroll",100)),100)


if __name__=="__main__":
    unittest.main()
