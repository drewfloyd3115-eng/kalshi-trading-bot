"""Offline tests: no API calls or orders."""
import unittest
from datetime import datetime, timedelta, timezone
import pandas as pd
from pregame_dashboard import eligibility_dashboard

class PregameDashboardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 15, tzinfo=timezone.utc)
        self.matches = pd.DataFrame([{"event":"Alpha vs Beta", "ticker":"T1",
            "side":"YES", "outcome_team":"alpha", "books":3,
            "book_spread_pp":2.0, "net_edge_pp_1share":6.0}])
        self.odds = pd.DataFrame([{"home":"Alpha","away":"Beta","start":
            (self.now+timedelta(hours=2)).isoformat()} for _ in range(3)])

    def test_recent_future_is_review_only(self):
        result=eligibility_dashboard(self.matches,self.odds,self.now.isoformat(),self.now)
        self.assertEqual(result.iloc[0]["research_status"],"REVIEW ONLY — NOT APPROVED")

    def test_stale_scan_blocks(self):
        old=(self.now-timedelta(minutes=6)).isoformat()
        result=eligibility_dashboard(self.matches,self.odds,old,self.now)
        self.assertEqual(result.iloc[0]["research_status"],"BLOCKED")

    def test_past_kickoff_blocks(self):
        self.odds["start"]=(self.now-timedelta(minutes=1)).isoformat()
        result=eligibility_dashboard(self.matches,self.odds,self.now.isoformat(),self.now)
        self.assertEqual(result.iloc[0]["kickoff_status"],"UNKNOWN/PAST")
        self.assertEqual(result.iloc[0]["research_status"],"BLOCKED")

    def test_disagreement_blocks(self):
        self.matches["book_spread_pp"]=8.0
        result=eligibility_dashboard(self.matches,self.odds,self.now.isoformat(),self.now)
        self.assertEqual(result.iloc[0]["research_status"],"BLOCKED")

    def test_below_threshold_blocks(self):
        self.matches["net_edge_pp_1share"]=4.99
        result=eligibility_dashboard(self.matches,self.odds,self.now.isoformat(),self.now)
        self.assertEqual(result.iloc[0]["research_status"],"BLOCKED")

    def test_missing_comparisons(self):
        self.assertTrue(eligibility_dashboard(pd.DataFrame(),self.odds).empty)

if __name__=="__main__":
    unittest.main()
