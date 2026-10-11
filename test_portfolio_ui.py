"""Portfolio UI regression checks: cached paper activity only; no market/API usage."""
import unittest
import pandas as pd

from paper_history import HISTORY_COLUMNS
from portfolio_ui import portfolio_view_model, portfolio_overview_html, _open_paper_card


class PortfolioUIModelTests(unittest.TestCase):
    @staticmethod
    def row(status, settlement="UNRESOLVED", shares=0, pnl=float("nan")):
        row = {key: None for key in HISTORY_COLUMNS}
        row.update({
            "event": "Test Team A vs Team B",
            "ticker": "FAKE-TICKER", "side": "YES",
            "paper_status": status, "settlement_result": settlement,
            "paper_shares": shares, "paper_fill_price_cents": 55,
            "paper_pnl_usd": pnl,
        })
        return row

    def test_no_history_and_no_queue_have_no_position_or_performance(self):
        m = portfolio_view_model(None, [], 500.0, 0.0, 0.0)
        self.assertEqual(m["open_paper_fills"], 0)
        self.assertEqual(m["closed"], 0)
        self.assertEqual(m["queue_count"], 0)
        self.assertEqual(m["gross_pnl"], 0.0)
        self.assertIn("NO REAL POSITIONS", portfolio_overview_html(m))

    def test_queue_and_observations_are_not_assumed_filled(self):
        history = pd.DataFrame([self.row("OBSERVED")], columns=HISTORY_COLUMNS)
        queue = [{"ticker": "TEST", "cost": 3.0}]
        m = portfolio_view_model(history, queue, 500, 1, 3)
        self.assertEqual(m["queue_count"], 1)
        self.assertEqual(m["queue_exposure"], 3)
        self.assertEqual(m["open_paper_fills"], 0)
        self.assertEqual(m["closed"], 0)
        self.assertEqual(m["observations"], 1)

    def test_explicit_paper_filled_and_closed_records_are_separate(self):
        history = pd.DataFrame([
            self.row("OBSERVED"),
            self.row("PAPER_FILLED", shares=4),
            self.row("PAPER_FILLED", shares=0),
            self.row("PAPER_CLOSED", settlement="WIN", shares=2, pnl=0.90),
            self.row("PAPER_CLOSED", settlement="LOSS", shares=2, pnl=-1.10),
        ], columns=HISTORY_COLUMNS)
        m = portfolio_view_model(history, [], 500, 0, 0)
        self.assertEqual(m["open_paper_fills"], 1)
        self.assertEqual(m["paper_fills"], 4)
        self.assertEqual(m["closed"], 2)
        self.assertEqual(m["wins"], 1)
        self.assertAlmostEqual(m["gross_pnl"], -0.20, places=2)

    def test_open_position_text_is_escaped_and_does_not_invent_exit_bid(self):
        row = self.row("PAPER_FILLED", shares=3)
        row["event"] = "<script>alert(1)</script>"
        row["ticker"] = "<img src=x>"
        html = _open_paper_card(row)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("No current executable sell bid", html)


class PortfolioAppTests(unittest.TestCase):
    def test_portfolio_navigation_and_sections_render_without_live_data(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        at.button_group(key="sports_nav").set_value("Portfolio").run()
        self.assertFalse(at.exception, str(at.exception))
        markup = "\n".join(str(x.value) for x in at.markdown)
        self.assertIn("Paper Portfolio", markup)
        self.assertIn("NO REAL POSITIONS", markup)
        self.assertGreaterEqual(len(at.info), 1)  # no settled-paper-performance claim

        nav = at.button_group(key="sports_portfolio_area")
        self.assertEqual(len(nav.options), 4)
        at.button_group(key="sports_portfolio_area").set_value("Open paper fills").run()
        self.assertFalse(at.exception, str(at.exception))
        # Manual ledger is the primary view; legacy records remain separately labeled.
        expanders = [str(x.label) for x in at.expander]
        self.assertIn("Older imported paper-journal fills (separate records)", expanders)
        for page in ("Open paper fills", "History", "Exit review", "Overview"):
            at.button_group(key="sports_portfolio_area").set_value(page).run()
            self.assertFalse(at.exception, str(at.exception))
            self.assertEqual(at.session_state["sports_portfolio_area"], page)
        at.button_group(key="sports_portfolio_area").set_value("Exit review").run()
        text = "\n".join(str(x.value) for x in at.markdown)
        self.assertIn("SELL-SIDE DEPTH RESEARCH", text)
        self.assertIn("Review Open Positions", text)


if __name__ == "__main__":
    unittest.main()
