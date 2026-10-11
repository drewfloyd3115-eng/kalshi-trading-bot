"""Offline tests for portable research snapshots."""
import unittest
import pandas as pd
from snapshot_backup import export_snapshot, import_snapshot

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.matches = pd.DataFrame([{"ticker":"ABC","side":"YES","ask_cents":41,
                                      "net_edge_pp_1share":-2.5,"event":"A vs B"}])
        self.time = "2026-10-11T01:14:02+00:00"

    def test_round_trip(self):
        blob = export_snapshot(self.matches, "CFB", self.time)
        restored = import_snapshot(blob, "CFB", "2026-10-11T01:19:12+00:00")
        self.assertEqual(restored["time"], self.time)
        self.assertEqual(restored["matches"].iloc[0]["ask_cents"], 41)

    def test_reject_wrong_league(self):
        blob = export_snapshot(self.matches, "CFB", self.time)
        with self.assertRaises(ValueError):
            import_snapshot(blob, "NFL")

    def test_reject_future_snapshot(self):
        blob = export_snapshot(self.matches, "CFB", self.time)
        with self.assertRaises(ValueError):
            import_snapshot(blob, "CFB", self.time)

if __name__ == "__main__":
    unittest.main()
