"""Offline smoke tests for new mobile presentation; no market or sportsbook calls."""
import unittest
from datetime import datetime, timedelta, timezone
import pandas as pd

from sports_ui import opportunity_view, research_label


class SportsUITests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 18, tzinfo=timezone.utc)
        self.matches = pd.DataFrame([
            {"league": "CFB", "event": "Alpha vs Beta", "ticker": "ALPHA",
             "side": "YES", "outcome_team": "alpha", "fair_pct": 62,
             "ask_cents": 54, "net_edge_pp_1share": 7.0,
             "books": 3, "book_spread_pp": 1.5, "oldest_quote_minutes": 2},
            {"league": "CFB", "event": "Alpha vs Beta", "ticker": "BETA",
             "side": "NO", "outcome_team": "alpha", "fair_pct": 62,
             "ask_cents": 53, "net_edge_pp_1share": 8.0,
             "books": 3, "book_spread_pp": 1.5, "oldest_quote_minutes": 2},
        ])
        kickoff = (self.now + timedelta(hours=2)).isoformat()
        self.odds = pd.DataFrame([{"home": "Alpha", "away": "Beta", "start": kickoff}
                                  for _ in range(3)])

    def test_empty_opportunities(self):
        self.assertTrue(opportunity_view(pd.DataFrame()).empty)

    def test_equivalent_outcomes_deduplicated(self):
        cards = opportunity_view(self.matches, self.odds, self.now.isoformat(),
                                 now=self.now)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards.iloc[0]["ticker"], "BETA")
        self.assertEqual(cards.iloc[0]["research_status"], "REVIEW ONLY — NOT APPROVED")
        self.assertIn("PRELIMINARY", research_label(cards.iloc[0]))

    def test_started_game_always_blocks(self):
        past = self.odds.copy()
        past["start"] = (self.now - timedelta(minutes=1)).isoformat()
        cards = opportunity_view(self.matches, past, self.now.isoformat(), now=self.now)
        self.assertTrue((cards["research_status"] == "BLOCKED").all())
        self.assertEqual(research_label(cards.iloc[0]), "BLOCKED — no trade")

    def test_stale_scan_always_blocks(self):
        old = (self.now - timedelta(minutes=12)).isoformat()
        cards = opportunity_view(self.matches, self.odds, old, now=self.now)
        self.assertTrue((cards["research_status"] == "BLOCKED").all())


class SportsUIAppSmokeTests(unittest.TestCase):
    def test_main_pages_load_without_fetching_odds(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        nav = at.button_group(key="sports_nav")
        self.assertEqual(nav.value, "Home")
        self.assertEqual(len(nav.options), 5)
        for page in ("Opportunities", "Market Detail", "Portfolio",
                     "Research", "Home"):
            at.button_group(key="sports_nav").set_value(page).run()
            self.assertFalse(at.exception, str(at.exception))
            self.assertEqual(at.session_state["sports_nav"], page)


if __name__ == "__main__":
    unittest.main()
