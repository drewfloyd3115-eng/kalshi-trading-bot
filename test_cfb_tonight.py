"""Offline tests: same-day Central time, quote provenance and safety."""
import unittest
import pandas as pd
from cfb_model.tonight import tonight_slate, _as_of


def source_games():
    return pd.DataFrame([
        {"game_id":"g0","season":2024,"week":8,"kickoff_utc":"2024-10-20T19:00:00Z",
         "home_team":"Alpha","away_team":"Beta","home_points":42,"away_points":24,
         "completed":True,"neutral_site":False},
    ])


def schedule(when="2026-10-25T00:00:00Z", home="Alpha",away="Beta", eid="900",
             fetched="2026-10-24T21:20:00Z"):
    d=pd.DataFrame([{
        "game_id":f"espn-{eid}","season":2026,"week":9,
        "kickoff_utc":when,"home_team":home,"away_team":away,
        "home_points":None,"away_points":None,
        "completed":False,"neutral_site":False
    }])
    d.attrs["fetched_utc"]=fetched
    d.attrs["indicative_market"]=pd.DataFrame([{
        "game_id":f"espn-{eid}","market_home_handicap":9.5,"market_total":54.5,
        "market_provider":"Test sports book"
    }])
    return d


NOW="2026-10-24T21:24:00Z"  # 4:24 PM CDT, same Saturday as user's request


class TonightCFBTests(unittest.TestCase):
    def test_valid_after_five_central_appears_research_only(self):
        # Build 305 real synthetic previous fixtures to exercise the history
        # eligibility gate, never represent these fixtures as real games.
        rows=[]
        for i in range(305):
            rows.append({
                "game_id":f"history-{i}","season":2020+i//100,"week":1+i%15,
                "kickoff_utc":(pd.Timestamp("2020-08-01T13:00:00Z")+
                               pd.Timedelta(days=i)).isoformat(),
                "home_team":"Alpha" if i%2 else "Beta",
                "away_team":"Beta" if i%2 else "Alpha",
                "home_points":24+i%21,"away_points":13+i%17,
                "completed":True,"neutral_site":False
            })
        games=pd.DataFrame(rows)
        board=tonight_slate(games,schedule(),now=NOW)
        self.assertEqual(len(board),1)
        self.assertEqual(board.iloc[0]["game_id"],"espn-900")
        self.assertEqual(board.iloc[0]["decision"],"PASS — NO VERIFIED POSITIVE EV")
        self.assertAlmostEqual(board.iloc[0]["spread_disagreement_points"],
                               board.iloc[0]["projected_home_margin"]+9.5,places=1)
        self.assertTrue(board.iloc[0]["matchup"].startswith("Beta @ Alpha"))
        self.assertNotIn("roi",board.columns)

    def test_started_or_pre_five_pm_central_excluded(self):
        base=source_games()
        # Source contains just one history game and will fail history eligibility,
        # but kickoff eligibility must still result in an empty table.
        self.assertTrue(tonight_slate(base,schedule(when="2026-10-24T21:00:00Z"),now=NOW).empty)
        self.assertTrue(tonight_slate(base,schedule(when="2026-10-24T22:30:00Z"),now=NOW).empty)

    def test_next_day_central_excluded_despite_utc_matching(self):
        self.assertTrue(tonight_slate(source_games(),
                                      schedule(when="2026-10-25T06:00:00Z"),
                                      now=NOW).empty)

    def test_stale_or_future_schedule_blocks(self):
        with self.assertRaisesRegex(ValueError,"over 30 minutes"):
            tonight_slate(source_games(),schedule(fetched="2026-10-24T20:00:00Z"),now=NOW)
        with self.assertRaisesRegex(ValueError,"future-dated"):
            tonight_slate(source_games(),schedule(fetched="2026-10-24T23:00:00Z"),now=NOW)

    def test_no_fake_or_postgame_fixtures(self):
        df=schedule()
        df.loc[0,"completed"]=True
        df.loc[0,"home_points"]=35
        df.loc[0,"away_points"]=7
        with self.assertRaisesRegex(ValueError,"scored fixtures"):
            tonight_slate(source_games(),df,now=NOW)
        df=schedule(eid="900")
        df.loc[0,"game_id"]="made-up"
        with self.assertRaisesRegex(ValueError,"exact ESPN event IDs"):
            tonight_slate(source_games(),df,now=NOW)

    def test_missing_market_comparisons_stay_missing(self):
        df=schedule()
        df.attrs["indicative_market"]=pd.DataFrame()
        board=tonight_slate(source_games(),df,now=NOW)
        self.assertTrue(board.empty)  # one real historical game fails minimum history
        self.assertEqual(list(board.columns)[-1],"decision")

    def test_timestamp_must_be_aware(self):
        with self.assertRaisesRegex(ValueError,"timezone-aware"):
            _as_of("2026-10-24T17:30:00")


if __name__=="__main__":
    unittest.main()
