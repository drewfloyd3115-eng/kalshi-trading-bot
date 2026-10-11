"""End-to-end offline Streamlit paper ledger workflow (no sportsbook requests)."""
import unittest
from streamlit.testing.v1 import AppTest

from position_ledger import ledger_summary


class ManualPaperLedgerUITests(unittest.TestCase):
    def portfolio(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.assertFalse(app.exception, str(app.exception))
        app.button_group(key="sports_nav").set_value("Portfolio").run()
        self.assertFalse(app.exception, str(app.exception))
        return app

    def test_forms_are_explicit_and_navigation_never_creates_a_fill(self):
        app = self.portfolio()
        self.assertEqual(ledger_summary(app.session_state["position_ledger"])["transactions"], 0)
        app.button_group(key="sports_portfolio_area").set_value("Open paper fills").run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.button(key="ledger_entry_save").label, "Save hypothetical entry")
        self.assertEqual(ledger_summary(app.session_state["position_ledger"])["transactions"], 0)
        app.button_group(key="sports_portfolio_area").set_value("Exit review").run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(ledger_summary(app.session_state["position_ledger"])["open_positions"], 0)

    def test_manual_entry_and_partial_exit_work_without_market_api(self):
        app = self.portfolio()
        app.button_group(key="sports_portfolio_area").set_value("Open paper fills").run()
        self.assertFalse(app.exception, str(app.exception))
        app.text_input(key="ledger_entry_ticker").set_value("KXCFB-ALPHA-BETA")
        app.text_input(key="ledger_entry_event").set_value("Alpha vs Beta")
        app.text_input(key="ledger_entry_winner").set_value("Alpha")
        app.number_input(key="ledger_entry_shares").set_value(2)
        app.number_input(key="ledger_entry_price").set_value(40)
        app.number_input(key="ledger_entry_fee").set_value(0.02)
        app.checkbox(key="ledger_entry_confirm").check()
        app.button(key="ledger_entry_save").click().run()
        self.assertFalse(app.exception, str(app.exception))
        summary = ledger_summary(app.session_state["position_ledger"])
        self.assertEqual(summary["transactions"], 1)
        self.assertEqual(summary["open_positions"], 1)
        self.assertAlmostEqual(summary["open_cost_usd"], 0.82)

        app.button_group(key="sports_portfolio_area").set_value("Exit review").run()
        self.assertFalse(app.exception, str(app.exception))
        app.number_input(key="ledger_exit_shares").set_value(1)
        app.number_input(key="ledger_exit_price").set_value(70)
        app.number_input(key="ledger_exit_fee").set_value(0.01)
        app.checkbox(key="ledger_exit_confirm").check()
        app.button(key="ledger_exit_save").click().run()
        self.assertFalse(app.exception, str(app.exception))
        summary = ledger_summary(app.session_state["position_ledger"])
        self.assertEqual(summary["transactions"], 2)
        self.assertEqual(summary["remaining_shares"], 1)
        self.assertAlmostEqual(summary["open_cost_usd"], 0.41)
        self.assertAlmostEqual(summary["realized_net_usd"], 0.28)

        app.button_group(key="sports_portfolio_area").set_value("History").run()
        self.assertFalse(app.exception, str(app.exception))
        markdown = "\n".join(str(item.value) for item in app.markdown)
        self.assertIn("Manual paper position ledger", markdown)
        self.assertEqual(ledger_summary(app.session_state["position_ledger"])["transactions"], 2)
        # Streamlit's AppTest omits download_button elements; CSV bytes are
        # covered by the pure ledger export/import roundtrip regression test.


if __name__ == "__main__":
    unittest.main()
