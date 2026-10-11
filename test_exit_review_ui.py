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
        with patch("exit_review_ui.review_public_position",
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
