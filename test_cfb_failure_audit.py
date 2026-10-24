"""Regression checks for descriptive historical model weakness diagnostics."""
import unittest
import pandas as pd
from cfb_model.failure_audit import market_failure_audit


def paired_fixture():
    return pd.DataFrame([
        {"game_id":"100","week":1,"away_team":"Away A","home_team":"Home A",
         "provider":"ESPN Bet","actual_margin":40.0,"projected_home_margin":10.0,
         "market_home_margin":31.5,"actual_total":55.0,
         "projected_total":58.0,"total":54.5},
        {"game_id":"101","week":7,"away_team":"Away B","home_team":"Home B",
         "provider":"ESPN Bet","actual_margin":3.0,"projected_home_margin":4.0,
         "market_home_margin":2.5,"actual_total":42.0,
         "projected_total":54.0,"total":44.5},
        {"game_id":"102","week":12,"away_team":"Away C","home_team":"Home C",
         "provider":"ESPN Bet","actual_margin":-17.0,"projected_home_margin":-5.0,
         "market_home_margin":-16.5,"actual_total":71.0,
         "projected_total":53.0,"total":62.5},
    ])


class CFBAuditTests(unittest.TestCase):
    def test_exact_scoring_and_book_direction(self):
        result=market_failure_audit(paired_fixture())
        self.assertEqual(result["summary"]["paired_games"],3)
        s=result["summary"]["spread"]
        self.assertAlmostEqual(s["model_mae"], (30+1+12)/3,places=2)
        self.assertAlmostEqual(s["book_mae"], (8.5+.5+.5)/3,places=2)
        self.assertAlmostEqual(s["book_advantage_points"], round((30+1+12-8.5-.5-.5)/3,2))
        self.assertEqual(result["summary"]["provider_names"],["ESPN Bet"])
        self.assertIn("not a fresh",result["summary"]["important_limit"])

    def test_predeclared_week_bins(self):
        result=market_failure_audit(paired_fixture())
        w=result["by_week_spread"]
        self.assertEqual(w.season_phase.tolist(),["Weeks 1–4","Weeks 5–8","Weeks 9–14"])
        self.assertEqual(w.games.tolist(),[1,1,1])

    def test_favorite_size_bins_and_abs_market_handicap(self):
        result=market_failure_audit(paired_fixture())
        f=result["by_favorite_spread"].set_index("book_favorite_points")
        self.assertEqual(f.loc["21+","games"],1)
        self.assertEqual(f.loc["Under 3","games"],1)
        self.assertEqual(f.loc["14–20.5","games"],1)

    def test_disagreement_bins_preserve_model_errors(self):
        result=market_failure_audit(paired_fixture())
        t=result["by_disagreement_spread"].set_index("margin_disagreement")
        self.assertEqual(t.loc["14+","games"],1)
        self.assertEqual(t.loc["Under 3","games"],1)
        self.assertEqual(t.loc["7–13.5","games"],1)
        worse=result["largest_spread_failures"]
        self.assertEqual(worse.iloc[0].home_team,"Home A")
        self.assertGreater(worse.iloc[0].book_advantage_points,0)

    def test_missing_total_is_not_fabricated(self):
        f=paired_fixture()
        f.loc[0,"total"]=None
        a=market_failure_audit(f)
        self.assertEqual(a["summary"]["spread"]["games"],3)
        self.assertEqual(a["summary"]["total"]["games"],2)
        self.assertEqual(a["by_total_band"].games.sum(),2)

    def test_duplicates_missing_columns_and_invalid_weeks_block(self):
        f=paired_fixture()
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            market_failure_audit(pd.concat([f,f.iloc[[0]]],ignore_index=True))
        with self.assertRaisesRegex(ValueError,"Missing historical"):
            market_failure_audit(f.drop(columns=["actual_total"]))
        f.loc[1,"week"]=999
        with self.assertRaisesRegex(ValueError,"Invalid schedule"):
            market_failure_audit(f)

    def test_no_leakage_into_core_or_betting_orders(self):
        a=market_failure_audit(paired_fixture())
        self.assertNotIn("profit",a)
        self.assertNotIn("expected_ev",a)
        self.assertNotIn("trade",a)
        self.assertEqual(a["summary"]["paired_games"],3)

    def test_original_dataframe_remains_unchanged(self):
        raw=paired_fixture()
        original=raw.copy(deep=True)
        market_failure_audit(raw)
        pd.testing.assert_frame_equal(raw,original)


if __name__=="__main__":
    unittest.main()
