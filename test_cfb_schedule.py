"""Offline regression coverage for FBS upcoming schedule data and exact ESPN IDs."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
import pandas as pd

from cfb_model.data import parse_public_games_csv, fetch_public_years
from cfb_model.schedule import parse_schedule_events, fetch_upcoming_schedule


NOW = pd.Timestamp("2026-10-24T12:00:00Z")


def event(eid="4018", status="pre", when="2026-10-25T19:30:00Z",
          home="30", away="40", neutral=False):
    return {
        "id": eid, "date": when,
        "status": {"type": {"state": status, "completed": status == "post"}},
        "week": {"number": 9},
        "competitions": [{
            "neutralSite": neutral,
            "competitors": [
                {"homeAway": "home", "team": {"id": home, "displayName": "ABC"}},
                {"homeAway": "away", "team": {"id": away, "displayName": "DEF"}}
            ]
        }]
    }


SCOREBOARD_HEADER = (
    "id,season,week,start_date,neutral_site,home_team,away_team,"
    "home_points,away_points,home_level,away_level,home_id,away_id\n"
)


class CFBUpcomingScheduleTests(unittest.TestCase):
    def test_exact_id_matching_and_future_only(self):
        payload = {"events": [
            event("1"), event("2", status="in"),
            event("3", when="2026-10-22T19:30:00Z"),
            event("4", home="999"),
            event("5", status="post"),
        ]}
        result = parse_schedule_events(payload, {"30": "Michigan", "40": "Indiana"}, now=NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0].game_id, "espn-1")
        self.assertEqual(result.iloc[0].home_team, "Michigan")
        self.assertEqual(result.iloc[0].away_team, "Indiana")
        self.assertFalse(result.iloc[0].completed)
        self.assertTrue(pd.isna(result.iloc[0].home_points))
        self.assertEqual(result.attrs["stats"]["received"], 5)

    def test_missing_mapping_or_only_invalid_games_fail(self):
        payload = {"events": [event()]}
        with self.assertRaisesRegex(ValueError, "mapping"):
            parse_schedule_events(payload, {}, now=NOW)
        with self.assertRaisesRegex(ValueError, "No future"):
            parse_schedule_events(payload, {"30":"Michigan"}, now=NOW)
        with self.assertRaisesRegex(ValueError, "no schedule events"):
            parse_schedule_events({"events":[]}, {"30":"Michigan"}, now=NOW)

    def test_espn_response_requires_correct_shape(self):
        with self.assertRaisesRegex(ValueError, "events"):
            parse_schedule_events({}, {"30": "Michigan"}, now=NOW)

    def test_fetch_uses_bounded_dates_and_no_auth(self):
        ss=Mock()
        ss.get.return_value.json.return_value={"events":[event()]}
        df=fetch_upcoming_schedule({"30":"Michigan","40":"Indiana"},now=NOW,days=8,session=ss)
        self.assertEqual(len(df),1)
        request=ss.get.call_args
        self.assertEqual(request.kwargs["params"]["groups"],"80")
        self.assertEqual(request.kwargs["params"]["limit"],500)
        self.assertEqual(request.kwargs["params"]["dates"],"20261024-20261101")
        self.assertNotIn("headers",request.kwargs)
        with self.assertRaisesRegex(ValueError,"1–14"):
            fetch_upcoming_schedule({"30":"Michigan","40":"Indiana"},days=30,session=ss)

    def test_public_source_builds_team_id_mapping(self):
        sample=(SCOREBOARD_HEADER+
                "101,2025,1,2025-09-01T16:00:00Z,False,Michigan,Indiana,24,21,fbs,fbs,30,40\n"+
                "102,2025,2,2025-09-08T16:00:00Z,False,Michigan,Indiana,14,7,fbs,fbs,30,40\n")
        games=parse_public_games_csv(sample)
        self.assertEqual(games.attrs["espn_team_ids"],{"30":"Michigan","40":"Indiana"})
        self.assertEqual(len(games),2)

    def test_cross_year_team_id_conflicts_are_excluded(self):
        ss=Mock()
        def fetch(url, timeout):
            year=int(url.split("games")[-1].split(".csv")[0])
            away="Indiana" if year == 2025 else "Other University"
            m=Mock()
            m.text=(SCOREBOARD_HEADER+
                    f"foo-{year},{year},1,{year}-09-01T16:00:00Z,False,Michigan,{away},24,21,fbs,fbs,30,40\n")
            return m
        ss.get.side_effect=fetch
        data=fetch_public_years(2025,2026,session=ss)
        self.assertEqual(data.attrs["espn_team_ids"],{"30":"Michigan"})
        self.assertIn("40",data.attrs["ambiguous_espn_ids"])


if __name__ == "__main__":
    unittest.main()
