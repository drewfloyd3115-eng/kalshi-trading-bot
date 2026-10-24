"""Offline smoke tests for new mobile presentation; no market or sportsbook calls."""
import unittest
from datetime import datetime, timedelta, timezone
import pandas as pd

from sports_ui import opportunity_view, research_label, opportunity_card_html, scan_age_label, detail_panel_html


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

    def test_cards_escape_market_feed_html(self):
        sample = {
            "event": '<img src=x onerror=alert(1)> vs School',
            "outcome_team": '<script>attack</script>',
            "league": "CFB", "side": "YES", "net_edge_pp_1share": 8.0,
            "ask_cents": 54.0, "fair_pct": 63.0, "books": 2,
            "book_spread_pp": 1.5, "oldest_quote_minutes": 2.0,
            "depth_status": "<b>unverified</b>",
            "reason": "<script>unsanitized</script>",
            "research_status": "BLOCKED"
        }
        markup = opportunity_card_html(sample)
        self.assertNotIn("<script>", markup)
        self.assertNotIn("<img", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("BLOCKED", markup)

    def test_scan_age_stale_is_never_current(self):
        current, allowed = scan_age_label(
            (self.now - timedelta(minutes=8)).isoformat(), now=self.now)
        self.assertFalse(allowed)
        self.assertIn("STALE", current)

    def test_missing_scan_timestamp_not_current(self):
        label, allowed = scan_age_label(None, now=self.now)
        self.assertFalse(allowed)
        self.assertIn("unknown", label.lower())

    def test_preview_never_looks_like_an_approved_or_blocked_market(self):
        sample = {
            "event": "Upcoming matchup placeholder",
            "outcome_team": "No outcome loaded", "research_status": "DESIGN PREVIEW",
            "net_edge_pp_1share": None, "ask_cents": None, "fair_pct": None,
            "books": None, "depth_status": "NOT INSPECTED",
            "reason": "DESIGN PREVIEW ONLY — no odds, no verified trade",
        }
        self.assertEqual(research_label(sample), "DESIGN PREVIEW — no market data")
        html = opportunity_card_html(sample)
        self.assertIn("kl-opp-flag preview", html)
        self.assertNotIn("BLOCKED — no trade", html)
        self.assertNotIn("PRELIMINARY +5pp", html)

    def test_market_detail_preview_contains_no_fake_price_or_trade(self):
        preview = {
            "event": "Matchup not loaded", "outcome_team": "No outcome selected",
            "research_status": "DESIGN PREVIEW", "fair_pct": None,
            "ask_cents": None, "net_edge_pp_1share": None,
            "reason": "DESIGN PREVIEW ONLY",
        }
        markup = detail_panel_html(preview)
        self.assertIn("DESIGN PREVIEW", markup)
        self.assertIn("Estimated fair chance", markup)
        self.assertIn("style=\"width:0.00%\">", markup)
        self.assertNotIn("PRELIMINARY — not approved", markup)

    def test_market_detail_stale_scan_stays_blocked(self):
        sample = {
            "event": "Alpha vs Beta", "outcome_team": "Alpha",
            "ticker": "TICKER1", "side": "YES", "fair_pct": 62,
            "ask_cents": 54, "net_edge_pp_1share": 6.0,
            "research_status": "REVIEW ONLY — NOT APPROVED",
            "quote_status": "CACHED RECENT", "kickoff_status": "FUTURE (cached)"
        }
        markup = detail_panel_html(
            sample, (self.now - timedelta(minutes=10)).isoformat(), now=self.now)
        self.assertIn("BLOCKED — stale or missing scan", markup)
        self.assertNotIn("PRELIMINARY — not approved", markup)
        self.assertIn("62.00%", markup)
        self.assertIn("54.0¢", markup)

    def test_market_detail_html_escapes_feed_fields(self):
        sample = {
            "event": '<script>alert(1)</script>',
            "outcome_team": '<img src=x onerror=alert(2)>',
            "ticker": "<b>attack</b>", "side": "YES",
            "reason": '<script>attack</script>', "research_status": "BLOCKED",
            "fair_pct": 55, "ask_cents": 53, "net_edge_pp_1share": -1
        }
        markup = detail_panel_html(sample)
        self.assertNotIn("<script>", markup)
        self.assertNotIn("<img", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("&lt;img", markup)

    def test_market_detail_fee_arithmetic_is_one_share(self):
        from edge_engine import taker_fee
        sample = {
            "event": "Alpha vs Beta", "outcome_team": "Alpha",
            "research_status": "REVIEW ONLY — NOT APPROVED",
            "fair_pct": 62, "ask_cents": 54, "net_edge_pp_1share": 6.0
        }
        markup = detail_panel_html(sample, self.now.isoformat(), now=self.now)
        fee = taker_fee(54, 1)
        self.assertIn(f"{fee:.2f} USD", markup)
        self.assertIn(f"{0.54+fee:.2f} USD", markup)
        self.assertIn("PRELIMINARY — not approved", markup)

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
    def test_market_detail_design_preview_without_fetching_odds(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        at.button_group(key="sports_nav").set_value("Market Detail").run()
        self.assertFalse(at.exception, str(at.exception))
        markup = "\n".join(str(item.value) for item in at.markdown)
        self.assertIn("Market intelligence / CFB + NFL", markup)
        self.assertIn("DESIGN PREVIEW", markup)
        self.assertIn("Estimated probability comparison", markup)
        self.assertIn("Pregame and quote-quality checks", markup)

    def test_new_opportunities_markup_and_placeholder_are_rendered(self):
        """Catch stale presentation modules that render an obsolete UI."""
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        at.button_group(key="sports_nav").set_value("Opportunities").run()
        self.assertFalse(at.exception, str(at.exception))
        markdown = "\n".join(str(item.value) for item in at.markdown)
        self.assertIn("Market research / CFB + NFL", markdown)
        self.assertIn("Upcoming matchup placeholder", markdown)
        self.assertIn("DESIGN PREVIEW ONLY", markdown)
        self.assertNotIn("Ranked by estimated net edge. One best YES/NO route per distinct", markdown)

    def test_main_pages_load_without_fetching_odds(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        nav = at.button_group(key="sports_nav")
        self.assertEqual(nav.value, "Home")
        self.assertEqual(len(nav.options), 6)
        for page in ("Opportunities", "Market Detail", "Portfolio",
                     "CFB Model", "Research", "Home"):
            at.button_group(key="sports_nav").set_value(page).run()
            self.assertFalse(at.exception, str(at.exception))
            self.assertEqual(at.session_state["sports_nav"], page)


if __name__ == "__main__":
    unittest.main()
