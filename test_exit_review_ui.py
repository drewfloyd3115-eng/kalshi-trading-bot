"""Offline mobile Exit Review UI tests: render and caching cannot place trades."""
import unittest
from unittest.mock import patch

from exit_review_ui import _review_card, _cents, _usd


class ExitReviewCardTests(unittest.TestCase):
    def test_missing_quote_displays_no_pnl(self):
        record = {
            "ticker": "KXCFB-TEST-MARKET", "side": "YES",
            "status": "UNVERIFIED — NO EXIT SIGNAL",
            "reason": "Market unavailable", "covered_shares": 0,
            "requested_shares": 2,
        }
        text = _review_card(record, False, "No current snapshot")
        self.assertIn("UNVERIFIED · NO EXIT SIGNAL", text)
        self.assertIn("NOT actual realized profit", text)
        self.assertIn("Market unavailable", text)
        self.assertIn("NOT CURRENT", text)
        self.assertEqual(_usd(None), "—")
        self.assertEqual(_cents(None), "—")

    def test_rejected_local_ticker_does_not_claim_recent_lookup(self):
        record = {
            "ticker": "KXCFB-TEST-MARKET", "side": "YES",
            "reason": "Rejected before public lookup: unsupported ticker",
            "lookup_status": "REJECTED BEFORE LOOKUP",
            "covered_shares": 0, "requested_shares": 4,
        }
        rendered = _review_card(record, False,
                                "No Kalshi public lookup performed")
        self.assertIn("NO PUBLIC LOOKUP", rendered)
        self.assertIn("REJECTED BEFORE LOOKUP", rendered)
        self.assertNotIn("RECENT LOOKUP", rendered)
        self.assertIn("No Kalshi public lookup performed", rendered)

    def test_real_book_lookup_still_not_certified_execution(self):
        record = {
            "ticker": "KXNCAAFGAME-SAMPLE", "side": "YES",
            "reason": "Orderbook snapshot observed",
            "lookup_status": "PUBLIC ORDERBOOK RETURNED",
            "covered_shares": 4, "requested_shares": 4,
            "best_bid_cents": 75, "net_proceeds_usd": 2.88
        }
        rendered = _review_card(record, True, "Recent retrieval; not a fill")
        self.assertIn("RECENT RETRIEVAL", rendered)
        self.assertIn("NO EXIT SIGNAL", rendered)
        self.assertIn("NOT actual realized profit", rendered)

    def test_market_update_age_and_series_fee_are_separately_labeled(self):
        snapshot = {
            "ticker": "KXNCAAFGAME-26OCT16CHSOCLEM-CHSO",
            "side": "NO", "checked_utc": "2026-10-13T17:17:49Z",
            "reason": "Public bid depth only",
            "lookup_status": "PUBLIC ORDERBOOK RETURNED",
            "requested_shares": 1, "covered_shares": 1,
            "market_metadata_status": "STALE MARKET METADATA",
            "market_updated_age_minutes": 11465.57,
            "series_fee_type": "quadratic_with_maker_fees",
            "series_fee_multiplier": 1.0,
            "series_fee_metadata_status": "QUADRATIC + MAKER FEES — ORDER-SPECIFIC FEE UNVERIFIED",
        }
        html = _review_card(snapshot, False, "Market metadata is stale or inconsistent")
        self.assertIn("STALE MARKET METADATA", html)
        self.assertIn("11465.57 minutes", html)
        self.assertIn("quadratic_with_maker_fees", html)
        self.assertIn("ORDER-SPECIFIC FEE UNVERIFIED", html)
        self.assertIn("NOT CURRENT", html)
        self.assertIn("NO EXIT SIGNAL", html)

    def test_escape_quoted_metadata_and_reason(self):
        record = {
            "ticker": "<img src=x onerror=alert(1)>",
            "side": "<script>YES</script>",
            "reason": "<script>unsafe</script>",
            "checked_utc": "<img>",
            "covered_shares": 0, "requested_shares": 1,
        }
        text = _review_card(record, True, "<script>clock</script>")
        self.assertNotIn("<script>", text)
        self.assertNotIn("<img", text)
        self.assertIn("&lt;script&gt;", text)

    def test_render_portfolio_exit_tab_does_not_fetch_automatically(self):
        # No manual positions in empty session. Merely opening Exit Review
        # must never make network requests to public Kalshi or sportsbook.
        from streamlit.testing.v1 import AppTest
        with patch("requests.get",
                   side_effect=AssertionError("Background public GET not allowed")):
            app = AppTest.from_file("app.py", default_timeout=20).run()
            self.assertFalse(app.exception, str(app.exception))
            app.button_group(key="sports_nav").set_value("Portfolio").run()
            self.assertFalse(app.exception, str(app.exception))
            app.button_group(key="sports_portfolio_area").set_value("Exit review").run()
            self.assertFalse(app.exception, str(app.exception))
            text = "\n".join(str(x.value) for x in app.markdown)
            self.assertIn("SELL-SIDE DEPTH RESEARCH", text)
            self.assertIn("Review Open Positions", text)


if __name__ == "__main__":
    unittest.main()
