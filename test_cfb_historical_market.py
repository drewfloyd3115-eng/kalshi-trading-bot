"""CFB historical-book benchmark: identity, line direction, leakage and paired metrics."""
import unittest
from unittest.mock import Mock
import pandas as pd

from cfb_model.historical_market import (
    _formatted_home_handicap, normalize_closing_lines,
    parse_cfbd_closing_lines, fetch_cfbd_closing_lines,
    benchmark_predictions, calibration_table
)


def predicted(home="Illinois", away="Oregon", season=2025, margin=-6.9,
              total=52.6, hp=21, ap=30, probability=.34):
    return pd.DataFrame([{
        "game_id":"120", "home_team":home, "away_team":away,
        "season":season, "week":9, "kickoff_utc":pd.Timestamp("2025-10-24T19:00:00Z"),
        "home_points":hp, "away_points":ap, "projected_home_margin":margin,
        "projected_total":total, "home_win_prob":probability,
        "completed":True, "eligible_history":True,
    }])


def closing(home="Illinois", away="Oregon", handicap=9.5, total=49.5):
    return pd.DataFrame([{
        "game_id":"120", "home_team":home, "away_team":away,
        "provider":"consensus", "home_handicap":handicap, "total":total,
    }])


class CFBDHistoricalLineTests(unittest.TestCase):
    def test_exact_signed_home_and_away_direction(self):
        self.assertEqual(_formatted_home_handicap("Oregon -9.5","Illinois","Oregon"),9.5)
        self.assertEqual(_formatted_home_handicap("Illinois +9.5","Illinois","Oregon"),9.5)
        self.assertEqual(_formatted_home_handicap("Illinois -3","Illinois","Oregon"),-3)
        self.assertIsNone(_formatted_home_handicap("ILL +9.5","Illinois","Oregon"))
        self.assertIsNone(_formatted_home_handicap("Oregon 9.5","Illinois","Oregon"))
        self.assertIsNone(_formatted_home_handicap("","Illinois","Oregon"))

    def test_parse_exact_provider_and_safe_sign(self):
        raw=[{"id":120,"homeTeam":"Illinois","awayTeam":"Oregon","lines":[
            {"provider":"DraftKings","formattedSpread":"Oregon -10.5","spread":-10.5,"overUnder":51.5},
            {"provider":"consensus","formattedSpread":"Oregon -9.5","spread":-9.5,"overUnder":49.5},
        ]}]
        df=parse_cfbd_closing_lines(raw)
        self.assertEqual(len(df),1)
        self.assertEqual(df.iloc[0].provider,"consensus")
        self.assertEqual(df.iloc[0].home_handicap,9.5)
        self.assertEqual(df.iloc[0].total,49.5)
        df=parse_cfbd_closing_lines(raw,provider="DraftKings")
        self.assertEqual(df.iloc[0].home_handicap,10.5)

    def test_snake_case_vendor_response_supported(self):
        raw=[{"id":120,"home_team":"Illinois","away_team":"Oregon","lines":[
            {"provider":"consensus","formatted_spread":"Oregon -9.5",
             "spread":-9.5,"over_under":49.5}
        ]}]
        rows=parse_cfbd_closing_lines(raw)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows.iloc[0].home_handicap,9.5)
        self.assertEqual(rows.iloc[0].total,49.5)

    def test_malformed_spread_only_allows_total(self):
        raw=[{"id":120,"homeTeam":"Illinois","awayTeam":"Oregon","lines":[
            {"provider":"consensus","formattedSpread":"ILL -9.5","spread":9.5,"overUnder":50.5}
        ]}]
        df=parse_cfbd_closing_lines(raw)
        self.assertTrue(pd.isna(df.iloc[0].home_handicap))
        self.assertEqual(df.iloc[0].total,50.5)

    def test_mismatched_formatted_and_numeric_spreads_rejected(self):
        raw=[{"id":120,"homeTeam":"Illinois","awayTeam":"Oregon","lines":[
            {"provider":"consensus","formattedSpread":"Oregon -9.5","spread":-6.5,"overUnder":50.5}
        ]}]
        with self.assertRaisesRegex(ValueError,"discrepancy"):
            parse_cfbd_closing_lines(raw)

    def test_duplicate_game_rows_or_provider_rows_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicate game_id"):
            normalize_closing_lines(pd.concat([closing(),closing()],ignore_index=True))
        raw=[{"id":120,"homeTeam":"Illinois","awayTeam":"Oregon","lines":[
            {"provider":"consensus","formattedSpread":"Oregon -9.5","overUnder":50.5},
            {"provider":"consensus","formattedSpread":"Oregon -8.5","overUnder":50.5}
        ]}]
        with self.assertRaisesRegex(ValueError,"Duplicate consensus"):
            parse_cfbd_closing_lines(raw)

    def test_api_needs_key_and_is_manual_single_season(self):
        with self.assertRaisesRegex(ValueError,"CFBD_API_KEY"):
            fetch_cfbd_closing_lines(2025,"")
        http=Mock()
        http.get.return_value.json.return_value=[
            {"id":120,"homeTeam":"Illinois","awayTeam":"Oregon","lines":[
                {"provider":"consensus","formattedSpread":"Oregon -9.5",
                 "spread":-9.5,"overUnder":49.5}
            ]}
        ]
        result=fetch_cfbd_closing_lines(2025,"secret-test",session=http)
        self.assertEqual(len(result),1)
        self.assertEqual(http.get.call_args.kwargs["params"],{"year":2025,"provider":"consensus"})
        self.assertIn("Bearer secret-test",http.get.call_args.kwargs["headers"]["Authorization"])

    def test_spread_and_total_paired_mae(self):
        result,table=benchmark_predictions(predicted(),closing())
        self.assertEqual(result["matched_market_games"],1)
        self.assertEqual(result["matched_coverage_pct"],100.0)
        self.assertEqual(result["spread_comparison"]["model_mae"],2.1)
        self.assertEqual(result["spread_comparison"]["market_mae"],.5)
        self.assertEqual(result["spread_comparison"]["market_advantage_points"],-1.6)
        self.assertEqual(result["total_comparison"]["model_mae"],1.6)
        self.assertEqual(result["total_comparison"]["market_mae"],1.5)
        self.assertEqual(result["total_comparison"]["market_advantage_points"],-.1)
        self.assertNotIn("roi",result)
        self.assertNotIn("paper_pnl",result)
        self.assertIn("No EV, ROI, CLV",result["source_warning"])
        self.assertEqual(table.iloc[0].actual_total,51)

    def test_exact_identity_only_and_zero_matches_rejected(self):
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            benchmark_predictions(predicted(),closing(home="Illinois",away="Michigan"))
        l=closing()
        l["game_id"]="999"
        with self.assertRaisesRegex(ValueError,"Zero matching"):
            benchmark_predictions(predicted(),l)

    def test_missing_spread_total_have_independent_coverage(self):
        a=closing(handicap=None)
        metrics,_=benchmark_predictions(predicted(),a)
        self.assertEqual(metrics["spread_comparison"]["games"],0)
        self.assertEqual(metrics["total_comparison"]["games"],1)
        b=closing(total=None)
        metrics,_=benchmark_predictions(predicted(),b)
        self.assertEqual(metrics["spread_comparison"]["games"],1)
        self.assertEqual(metrics["total_comparison"]["games"],0)

    def test_eligible_holdout_games_only(self):
        p=predicted()
        p["eligible_history"]=False
        with self.assertRaisesRegex(ValueError,"No eligible"):
            benchmark_predictions(p,closing())

    def test_calibration_shows_actual_vs_estimated_not_pnl(self):
        p=predicted()
        p2=predicted(season=2025,margin=7,probability=.8,hp=28,ap=24)
        p2["game_id"]="121"
        both=pd.concat([p,p2],ignore_index=True)
        cal=calibration_table(both,2025)
        self.assertEqual(int(cal.games.sum()),2)
        self.assertIn("calibration_gap_pp",cal.columns)
        self.assertEqual(calibration_table(both,2024).shape[0],0)


if __name__ == "__main__":
    unittest.main()
