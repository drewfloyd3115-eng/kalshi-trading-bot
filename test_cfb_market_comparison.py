"""Pure, offline guards for market discrepancies, not bet recommendations."""
import unittest
import pandas as pd

from cfb_model.market_comparison import discrepancy_table
from cfb_model.schedule import indicative_espn_odds, parse_schedule_events


NOW = pd.Timestamp("2026-10-24T12:00:00Z")


def forecast(kickoff="2026-10-24T19:00:00Z", completed=False):
    return pd.DataFrame([{
        "game_id":"espn-99", "kickoff_utc":kickoff,
        "home_team":"Illinois", "away_team":"Oregon",
        "completed":completed, "eligible_history":True,
        "projected_home_margin":-6.9, "projected_total":52.6,
    }])


def quote(kickoff="2026-10-24T11:57:00Z", handicap=9.5, total=49.5):
    return pd.DataFrame([{
        "game_id":"espn-99", "market_home_handicap":handicap,
        "market_total":total, "market_provider":"Test Scoreboard",
        "market_observed_utc":kickoff,
    }])


class MarketComparisonTests(unittest.TestCase):
    def test_home_handicap_sign_and_total_disagreement(self):
        t=discrepancy_table(forecast(),quote(),now=NOW)
        self.assertEqual(len(t),1)
        self.assertAlmostEqual(t.iloc[0].model_minus_market_margin,2.6)
        self.assertAlmostEqual(t.iloc[0].model_minus_market_total,3.1)
        self.assertEqual(t.iloc[0].quality_status,"INDICATIVE ONLY — NOT VERIFIED EV")
        self.assertNotIn("BUY",set(t.columns))
        self.assertNotIn("expected_roi",set(t.columns))

    def test_started_games_omitted(self):
        self.assertTrue(discrepancy_table(forecast(kickoff="2026-10-24T11:00:00Z"),quote(),now=NOW).empty)
        self.assertTrue(discrepancy_table(forecast(completed=True),quote(),now=NOW).empty)

    def test_missing_or_stale_odds_are_not_bets(self):
        self.assertTrue(discrepancy_table(forecast(),pd.DataFrame(),now=NOW).empty)
        q=quote(kickoff="2026-10-24T11:00:00Z")
        t=discrepancy_table(forecast(),q,now=NOW)
        self.assertEqual(t.iloc[0].quality_status,"STALE — NO SIGNAL")
        q=quote(handicap=None,total=49.5)
        t=discrepancy_table(forecast(),q,now=NOW)
        self.assertTrue(pd.isna(t.iloc[0].model_minus_market_margin))
        self.assertAlmostEqual(t.iloc[0].model_minus_market_total,3.1)

    def test_future_quotes_and_duplicate_ids_fail(self):
        q=quote(kickoff="2026-10-24T12:10:00Z")
        with self.assertRaisesRegex(ValueError,"future"):
            discrepancy_table(forecast(),q,now=NOW)
        q=quote()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            discrepancy_table(forecast(),pd.concat([q,q],ignore_index=True),now=NOW)

    def test_espn_odds_need_explicit_favorite_flags(self):
        e={"id":"99"}
        h={"odds":[{"spread":9.5,"overUnder":49.5,
                      "provider":{"name":"Test provider"},
                      "homeTeamOdds":{"favorite":False},
                      "awayTeamOdds":{"favorite":True}}]}
        o=indicative_espn_odds(e,h,NOW)
        self.assertEqual(o["market_home_handicap"],9.5)
        self.assertEqual(o["market_total"],49.5)
        h["odds"][0]["homeTeamOdds"]["favorite"]=True
        h["odds"][0]["awayTeamOdds"]["favorite"]=False
        self.assertEqual(indicative_espn_odds(e,h,NOW)["market_home_handicap"],-9.5)
        del h["odds"][0]["homeTeamOdds"]
        self.assertIsNone(indicative_espn_odds(e,h,NOW)["market_home_handicap"])

    def test_no_odds_never_fabricated(self):
        self.assertIsNone(indicative_espn_odds({"id":"99"},{"odds":[]},NOW))
        self.assertIsNone(indicative_espn_odds({"id":"99"},{"odds":[{"spread":9.5}]},NOW))

    def test_parser_keeps_odds_provenance(self):
        event={"id":"99", "date":"2026-10-24T19:00:00Z",
           "status":{"type":{"state":"pre","completed":False}},
           "competitions":[{"competitors":[
               {"homeAway":"home","team":{"id":"30"}},
               {"homeAway":"away","team":{"id":"40"}}],
               "odds":[{"spread":9.5,"overUnder":49.5,
                         "provider":{"name":"Sample feed"},
                         "homeTeamOdds":{"favorite":False},
                         "awayTeamOdds":{"favorite":True}}]
           }]}
        result=parse_schedule_events({"events":[event]}, {"30":"Illinois","40":"Oregon"},now=NOW)
        market=result.attrs["indicative_market"]
        self.assertEqual(len(market),1)
        self.assertEqual(market.iloc[0]["market_provider"],"Sample feed")


if __name__ == "__main__":
    unittest.main()
