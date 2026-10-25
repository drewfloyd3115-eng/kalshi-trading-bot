"""Regression tests for concise mobile CFB cards and read-only new home screen."""
import unittest
import pandas as pd

from cfb_model.card_design import (card_view, game_card_html, market_view,
                                   spread_label, summary_html)


def sample(market_status="ODDS_API_FRESH",age=2):
    return {
        "game_id":"espn-88", "kickoff_utc":pd.Timestamp("2026-10-24T23:00:00Z"),
        "away_team":"Colorado","home_team":"Oklahoma State",
        "away_espn_id":"38","home_espn_id":"197",
        "market_home_handicap":-13.5,"market_verification":market_status,
        "market_oldest_quote_minutes":age,"market_provider":"DraftKings",
        "market_book_count":2,
        "projected_home_margin":2.8,"projected_away_score":24.65,
        "projected_home_score":27.45,"projected_total":52.1,
        "sim_home_win_pct":56.2,"sim_away_win_pct":43.8,
        "simulations":20000,"research_confidence":"PRELIMINARY",
        "confidence_color":"amber", "confidence_reason":"Real games, uncertainty remains"
    }


class CardDesignTests(unittest.TestCase):
    def test_market_vs_model_signs_and_disagreement(self):
        c=card_view(sample(),0)
        self.assertEqual(c["market_spread"],"Oklahoma State -13.5")
        self.assertEqual(c["model_spread"],"Oklahoma State -2.8")
        self.assertAlmostEqual(c["spread_gap"],10.7)
        self.assertEqual(c["market"]["status"],"CURRENT")
        self.assertIn("20,000",game_card_html(sample(),0))

    def test_older_source_cannot_claim_current(self):
        self.assertEqual(market_view(sample(age=20),0)["status"],"OLDER")
        self.assertEqual(market_view(sample(),20)["status"],"OLDER")
        self.assertEqual(market_view(sample(),190)["status"],"MISSING")
        self.assertNotIn("CURRENT",game_card_html(sample(),20))

    def test_espn_reference_is_visibly_not_live_vegas(self):
        c=sample("UNVERIFIED ESPN SCOREBOARD SNAPSHOT",None)
        self.assertEqual(market_view(c,0)["status"],"ESPN")
        h=game_card_html(c,0)
        self.assertIn("ESPN reference",h)
        self.assertIn("reference only",h)
        self.assertIn("not betting edge",h)

    def test_missing_market_keeps_our_model_projection(self):
        c=sample("NO MARKET DATA")
        c["market_home_handicap"]=None
        cv=card_view(c,0)
        self.assertEqual(cv["market_spread"],"Not available")
        self.assertEqual(cv["model_spread"],"Oklahoma State -2.8")
        self.assertIsNone(cv["spread_gap"])
        self.assertEqual(cv["market"]["status"],"MISSING")

    def test_html_escaping_and_logo_whitelist(self):
        c=sample()
        c["away_team"]='<script>alert(1)</script>'
        c["away_espn_id"]='" onerror="alert(1)'
        c["market_provider"]='<iframe src=evil>'
        c["confidence_reason"]='<img src=x>'
        h=game_card_html(c,0)
        self.assertNotIn("<script>",h)
        self.assertNotIn("<iframe",h)
        self.assertNotIn("onerror=",h)
        self.assertIn("&lt;script&gt;",h)
        self.assertIn("tl-logo-placeholder",h)
        self.assertIn("&lt;iframe",h)

    def test_nan_probabilities_and_invalid_model_rejected(self):
        c=sample()
        c["sim_home_win_pct"]=None
        c["sim_away_win_pct"]=float("nan")
        self.assertEqual(card_view(c,0)["home_sim"],None)
        c["projected_home_margin"]=None
        with self.assertRaisesRegex(ValueError,"finite"):
            card_view(c,0)

    def test_summary_does_not_claim_edge(self):
        text=summary_html(7,3,2,"Oct 24, 2026 06:00 PM CDT")
        self.assertIn("UPCOMING",text)
        self.assertIn("LINES SHOWN",text)
        self.assertIn("GAPS ≥7 PT",text)
        self.assertNotIn("BUY",text)


class AppHomeUXTests(unittest.TestCase):
    def test_new_home_and_games_render_without_external_api(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file("app.py",default_timeout=25).run()
        self.assertFalse(at.exception,str(at.exception))
        text=" ".join(str(x.value) for x in at.markdown)
        self.assertIn("Make the numbers easy.",text)
        self.assertIn("Open Games",str([b.label for b in at.button]))
        at.button(key="home_go_games").click().run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertEqual(at.session_state["sports_nav"],"Tonight CFB")
        game_markup=" ".join(str(x.value) for x in at.markdown)
        self.assertIn("Tonight",game_markup)
        self.assertIn("Refresh",str([b.label for b in at.button]))


if __name__=="__main__":
    unittest.main()
