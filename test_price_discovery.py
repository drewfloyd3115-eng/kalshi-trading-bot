"""Offline price discovery regression tests; no network access."""
import unittest
import pandas as pd
from price_discovery import price_discovery

class PriceDiscoveryTests(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(price_discovery(pd.DataFrame()).empty)

    def test_ranking_and_one_share_fee(self):
        data = pd.DataFrame([
            {"event":"A vs B","outcome_team":"A","ticker":"a","side":"YES","fair_pct":60,"ask_cents":58,"book_spread_pp":2,"books":3},
            {"event":"C vs D","outcome_team":"C","ticker":"c","side":"NO","fair_pct":60,"ask_cents":50,"book_spread_pp":1,"books":2},
        ])
        out = price_discovery(data)
        self.assertEqual(len(out), 2)
        self.assertEqual(out.iloc[0]["ticker"], "c")
        self.assertGreater(out.iloc[1]["gap_to_threshold_pp"], 0)
        self.assertEqual(out.iloc[0]["research_status"], "PRELIMINARY ONLY — NOT VERIFIED")

    def test_dedup_and_cached_depth(self):
        data = pd.DataFrame([
            {"event":"A vs B","outcome_team":"A","ticker":"t1","side":"YES","fair_pct":60,"ask_cents":55,"book_spread_pp":1,"books":3},
            {"event":"A vs B","outcome_team":"A","ticker":"t2","side":"NO","fair_pct":60,"ask_cents":54,"book_spread_pp":4,"books":3},
        ])
        depth = pd.DataFrame([{"ticker":"t2","side":"NO","depth_ask_cents":54,"depth_edge_pp":4.1,"reason":"Below 5pp threshold"}])
        result = price_discovery(data, depth)
        self.assertEqual(int(result["best_route_for_outcome"].sum()), 1)
        self.assertEqual(int(result.iloc[0]["route_count"]), 2)
        self.assertEqual(result.iloc[0]["depth_status"], "Below 5pp threshold")
        self.assertEqual(result.iloc[0]["quote_quality"], "REVIEW — disagreement")

    def test_invalid_prices_excluded(self):
        data = pd.DataFrame([{"fair_pct": 60, "ask_cents": 0}])
        self.assertTrue(price_discovery(data).empty)

if __name__ == "__main__":
    unittest.main()
