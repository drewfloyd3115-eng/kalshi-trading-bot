"""Offline tests for the cached opportunity-discovery summary."""
import unittest
import pandas as pd
from discovery_report import discovery_report


class DiscoveryReportTests(unittest.TestCase):
    def test_empty_data(self):
        metrics, table = discovery_report(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        self.assertEqual(metrics["matched_games"], 0)
        self.assertTrue(table.empty)

    def test_stages_and_no_forced_match(self):
        funnel = pd.DataFrame([
            {"league": "CFB", "game": "A @ B", "matched_contract_sides": 2, "kalshi_event_candidates": 2, "fresh_rows": 3},
            {"league": "CFB", "game": "C @ D", "matched_contract_sides": 0, "kalshi_event_candidates": 1, "fresh_rows": 2},
            {"league": "CFB", "game": "E @ F", "matched_contract_sides": 0, "kalshi_event_candidates": 0, "fresh_rows": 1},
        ])
        metrics, table = discovery_report(pd.DataFrame({"ticker": ["a"]}), pd.DataFrame({"book": ["x"]}), funnel, pd.DataFrame({"ticker": ["a", "b"]}))
        self.assertEqual((metrics["matched_games"], metrics["candidate_games"], metrics["excluded_games"]), (1, 1, 1))
        self.assertEqual(metrics["matched_sides"], 2)
        self.assertEqual(table.iloc[0]["coverage_stage"], "CANDIDATE — UNMATCHED")
        self.assertEqual(table.loc[table["game"] == "C @ D", "matched_contract_sides"].iloc[0], 0)


if __name__ == "__main__":
    unittest.main()
