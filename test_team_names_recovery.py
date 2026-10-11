"""Regression checks for the two recovered college matchups; no network access."""
import unittest
from team_names import normalized

class ExactTeamNormalizationTests(unittest.TestCase):
    def test_hawaii_arizona_state(self):
        self.assertEqual(normalized("Hawaii Rainbow Warriors"), normalized("Hawai'i"))
        self.assertEqual(normalized("Arizona State Sun Devils"), normalized("Arizona St."))

    def test_delaware_middle_tennessee(self):
        self.assertEqual(normalized("Delaware Blue Hens"), normalized("Delaware"))
        self.assertEqual(normalized("Middle Tennessee Blue Raiders"), normalized("Middle Tennessee"))

    def test_ambiguous_names_not_fuzzy_matched(self):
        self.assertNotEqual(normalized("Miami (OH)"), normalized("Miami (FL)"))
        self.assertNotEqual(normalized("Arizona State"), normalized("Arizona"))

if __name__ == "__main__":
    unittest.main()
