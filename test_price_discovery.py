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

    def test_invalid_prices_excluded(self):
        data = pd.DataFrame([{"fair_pct": 60, "ask_cents": 0}])
        self.assertTrue(price_discovery(data).empty)

if __name__ == "__main__":
    unittest.main()
