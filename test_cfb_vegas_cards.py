"""Offline tests for fresh Vegas spreads, sourced logos and bounded simulations."""
import unittest
from unittest.mock import Mock
import pandas as pd

from cfb_model.vegas import fetch_vegas_spreads, match_fresh_spreads
from cfb_model.sim_preview import simulate_preview, research_confidence
from cfb_model.tonight_ui import logo_url, display_spread, model_spread
from cfb_model.schedule import parse_schedule_events


NOW=pd.Timestamp("2026-10-24T20:00:00Z")


def fixture():
    event={
        "id":"8888888","date":"2026-10-25T00:00:00Z",
        "status":{"type":{"state":"pre","completed":False}},
        "competitions":[{"neutralSite":False,"competitors":[
            {"homeAway":"home","team":{"id":"999","displayName":"Illinois Fighting Illini"}},
            {"homeAway":"away","team":{"id":"2483","displayName":"Oregon Ducks"}}
        ]}]}
    return parse_schedule_events({"events":[event]},{"999":"Illinois","2483":"Oregon"},now=NOW)


def odds(fresh=True,homepoint=9.5):
    updated="2026-10-24T19:58:00Z" if fresh else "2026-10-24T19:10:00Z"
    return [{
        "id":"odds-event-1","home_team":"Illinois Fighting Illini",
        "away_team":"Oregon Ducks","commence_time":"2026-10-25T00:00:00Z",
        "bookmakers":[{"key":"draftkings","title":"DraftKings","last_update":updated,
                       "markets":[{"key":"spreads","last_update":updated,
                                   "outcomes":[{"name":"Illinois Fighting Illini","point":homepoint,"price":-110},
                                               {"name":"Oregon Ducks","point":-homepoint,"price":-110}]}]},
                      {"key":"fanduel","title":"FanDuel","last_update":updated,
                       "markets":[{"key":"spreads","last_update":updated,
                                   "outcomes":[{"name":"Illinois Fighting Illini","point":homepoint+1,"price":-110},
                                               {"name":"Oregon Ducks","point":-(homepoint+1),"price":-110}]}]}]
    }]


class VegasSimulationCardTests(unittest.TestCase):
    def test_exact_source_aliases_and_espn_verified_team_logos(self):
        slate=fixture()
        self.assertEqual(slate.attrs["espn_event_team_ids"]["espn-8888888"],
                         {"home":"999","away":"2483"})
        fresh=match_fresh_spreads(slate,odds(),now=NOW)
        self.assertEqual(len(fresh),1)
        self.assertEqual(fresh.iloc[0].market_book_count,2)
        self.assertAlmostEqual(fresh.iloc[0].market_home_handicap,10.0)
        self.assertEqual(fresh.iloc[0].market_verification,"ODDS_API_FRESH")
        self.assertEqual(fresh.iloc[0].market_provider,"Median of 2 US books")
        self.assertIn("2483.png",logo_url("2483"))
        self.assertIsNone(logo_url("<img src=x>"))

    def test_spread_signs_correct_for_home_and_away_favorites(self):
        self.assertEqual(display_spread("Illinois","Oregon",9.5),"Oregon -9.5")
        self.assertEqual(display_spread("Illinois","Oregon",-3.5),"Illinois -3.5")
        self.assertEqual(model_spread("Illinois","Oregon",-6.9),"Oregon -6.9")
        self.assertEqual(model_spread("Illinois","Oregon",6.9),"Illinois -6.9")
        self.assertEqual(display_spread("Illinois","Oregon",None),"Unavailable")

    def test_stale_quotes_missing_and_no_fuzzy_team_guessing(self):
        self.assertTrue(match_fresh_spreads(fixture(),odds(fresh=False),now=NOW).empty)
        event=odds()[0]
        event["home_team"]="Illinois" # exact ESPN alias, still source verified
        self.assertEqual(len(match_fresh_spreads(fixture(),[event],now=NOW)),1)
        event["home_team"]="Illini"  # no short-name/fuzzy guess
        self.assertTrue(match_fresh_spreads(fixture(),[event],now=NOW).empty)

    def test_wrong_kickoff_or_ambiguous_duplicate_event_excluded(self):
        example=odds()[0]
        example["commence_time"]="2026-10-25T06:00:00Z"
        self.assertTrue(match_fresh_spreads(fixture(),[example],now=NOW).empty)
        self.assertTrue(match_fresh_spreads(fixture(),odds()+odds(),now=NOW).empty)

    def test_book_quotes_require_two_opposing_outcomes(self):
        malformed=odds()
        malformed[0]["bookmakers"][0]["markets"][0]["outcomes"][1]["point"]=-6
        result=match_fresh_spreads(fixture(),malformed,now=NOW)
        self.assertEqual(result.iloc[0].market_book_count,1)
        self.assertEqual(result.iloc[0].market_provider,"FanDuel")

    def test_odds_api_single_explicit_spreads_request(self):
        ss=Mock()
        ss.get.return_value.ok=True
        ss.get.return_value.json.return_value=odds()
        ss.get.return_value.headers={"x-requests-remaining":"8"}
        result,remaining=fetch_vegas_spreads("fake-key",session=ss)
        self.assertEqual(remaining,"8")
        self.assertEqual(len(result),1)
        self.assertEqual(ss.get.call_count,1)
        self.assertEqual(ss.get.call_args.kwargs["params"]["markets"],"spreads")
        self.assertEqual(ss.get.call_args.kwargs["params"]["regions"],"us")

    def test_simulation_seed_and_mathematical_boundaries(self):
        a=simulate_preview("event123",-6.9,52.6,17,16,9.5,49.5)
        b=simulate_preview("event123",-6.9,52.6,17,16,9.5,49.5)
        self.assertEqual(a,b)
        self.assertEqual(a["simulations"],20000)
        self.assertAlmostEqual(a["home_win_pct"]+a["away_win_pct"],100,places=1)
        self.assertGreaterEqual(a["margin_p90"],a["margin_p10"])
        self.assertGreaterEqual(a["total_p90"],a["total_p10"])
        self.assertTrue(0<=a["home_cover_pct"]<=100)
        with self.assertRaisesRegex(ValueError,"positive"):
            simulate_preview("bad",0,50,0,16)

    def test_confidence_never_certifies_positive_ev(self):
        a=research_confidence(7,7,-3.5,1.5,"ODDS_API_FRESH",3)
        self.assertEqual(a[0],"CAUTIOUS")
        self.assertEqual(a[1],"amber")
        b=research_confidence(7,7,-23.5,8.5,"ODDS_API_FRESH",3)
        self.assertEqual(b[1],"red")
        c=research_confidence(7,7,market_source="UNVERIFIED ESPN")
        self.assertEqual(c[0],"UNVERIFIED")
        self.assertNotIn("HIGH",[a[0],b[0],c[0]])
        self.assertNotIn("green",[a[1],b[1],c[1]])


if __name__=="__main__":
    unittest.main()
