"""Offline regression tests for manual pregame scan monitoring."""
import unittest
import pandas as pd
from scan_monitor import scan_changes

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.old = pd.DataFrame([{"event":"A vs B","outcome_team":"A","ticker":"T","side":"YES","ask_cents":50,"net_edge_pp_1share":3}])
        self.new = pd.DataFrame([{"event":"A vs B","outcome_team":"A","ticker":"T","side":"YES","ask_cents":47,"net_edge_pp_1share":6}])

    def test_new_threshold_flag_only_with_future_fresh_evidence(self):
        evidence = pd.DataFrame([{"ticker":"T","side":"YES","kickoff_status":"FUTURE (cached)","quote_status":"CACHED RECENT"}])
        result = scan_changes(self.old, self.new, evidence)
        self.assertEqual(result.iloc[0]["threshold_crossing"], "NEW +5pp — REVIEW ONLY")
        self.assertEqual(result.iloc[0]["ask_change_cents"], -3)
        self.assertEqual(result.iloc[0]["edge_change_pp"], 3)

    def test_started_game_blocked(self):
        evidence = pd.DataFrame([{"ticker":"T","side":"YES","kickoff_status":"UNKNOWN/PAST","quote_status":"CACHED RECENT"}])
        result = scan_changes(self.old, self.new, evidence)
        self.assertEqual(result.iloc[0]["threshold_crossing"], "CROSSED BUT INELIGIBLE")
        self.assertTrue(result.iloc[0]["research_status"].startswith("BLOCKED"))

    def test_first_scan_has_no_false_crossing(self):
        result = scan_changes(None, self.new, None)
        self.assertEqual(result.iloc[0]["threshold_crossing"], "NO")

if __name__ == "__main__":
    unittest.main()
