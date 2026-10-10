"""Offline regression checks: no API calls, no orders."""
import unittest
from datetime import datetime,timezone,timedelta
import pandas as pd
from edge_engine import no_vig,taker_fee,assess
from config import MAX_TRADE_BANKROLL_PCT,MAX_TOTAL_EXPOSURE_PCT
from matcher import compare
from diagnostics import diagnostics
from coverage_funnel import coverage_funnel
from paper_journal import journal_rows
from paper_history import import_history, summary as paper_summary
from unittest.mock import patch
from integrated_scan import scan_candidates

NOW=datetime(2026,10,10,16,0,tzinfo=timezone.utc)
def fixtures():
    market=pd.DataFrame([dict(league="CFB",event="Georgia vs Alabama",
        ticker="KXNCAAFGAME-26OCT10UGAALA-ALA",yes_sub_title="Alabama",
        yes_ask_cents=50,no_ask_cents=51)])
    start=(NOW+timedelta(hours=4)).isoformat()
    fresh=(NOW-timedelta(minutes=1)).isoformat()
    odds=pd.DataFrame([dict(league="CFB",home="Georgia",away="Alabama",start=start,
        updated=fresh,book=k,book_key=k,team_a="Alabama",odds_a=-110,
        team_b="Georgia",odds_b=-110) for k in ("book1","book2")])
    return market,odds

class MatcherRegression(unittest.TestCase):
    def test_uab_memphis_coverage(self):
        m,o=fixtures()
        m["event"]="UAB vs Memphis"
        m["yes_sub_title"]="UAB"
        m["ticker"]="KXNCAAFGAME-26OCT10UABMEM-UAB"
        o["home"]="Memphis"
        o["away"]="UAB"
        o["team_a"]="UAB"
        o["team_b"]="Memphis"
        matches=compare(m,o,NOW)
        self.assertEqual(len(matches),2)
        diag=diagnostics(m,o,now=NOW)
        funnel=coverage_funnel(o,diag,matches,m)
        self.assertEqual(funnel.iloc[0]["status"],"MATCHED")
        self.assertEqual(int(funnel.iloc[0]["matched_contract_sides"]),2)
    def test_risk_caps_are_fractions(self):
        self.assertAlmostEqual(MAX_TRADE_BANKROLL_PCT,0.01)
        self.assertAlmostEqual(MAX_TOTAL_EXPOSURE_PCT,0.03)
    def test_position_cost_below_one_percent(self):
        result=assess(-110,-110,40,60,500,0,available_yes=1000,available_no=1000)
        for row in result:
            if row.get("cost") is not None:
                self.assertLessEqual(row["cost"],5.00001)
    def test_paper_journal_deduplicates_equivalent_routes(self):
        m,o=fixtures()
        rows=journal_rows(compare(m,o,NOW),"CFB")
        self.assertEqual(len(rows),2)
        self.assertFalse(rows["fee_verified"].any())
    def test_depth_fee_and_budget(self):
        m,o=fixtures()
        matches=compare(m,o,NOW)
        matches.loc[:,"net_edge_pp_1share"]=10.0
        snapshot={"status":"DEPTH SNAPSHOT — NOT VERIFIED TRADE","levels":[(40,5),(45,20)],"best_ask_cents":40,"checked_utc":"test"}
        with patch("integrated_scan.inspect",return_value=snapshot):
            result=scan_candidates(matches,500,0,max_checks=1)
        self.assertEqual(len(result),1)
        self.assertLessEqual(float(result.iloc[0]["estimated_cost"]),5.0)
    def test_history_observations_are_not_fills(self):
        m,o=fixtures()
        journal=journal_rows(compare(m,o,NOW),"CFB")
        history=import_history(journal.to_csv(index=False).encode("utf-8"))
        stats=paper_summary(history)
        self.assertEqual(stats["observations"],2)
        self.assertEqual(stats["paper_fills"],0)
        self.assertEqual(stats["closed"],0)
        self.assertEqual(stats["gross_pnl"],0.0)
    def test_history_rejects_observed_settlement(self):
        m,o=fixtures()
        journal=journal_rows(compare(m,o,NOW),"CFB")
        journal["settlement_result"]="WIN"
        with self.assertRaises(ValueError):
            import_history(journal.to_csv(index=False).encode("utf-8"))
    def test_history_closed_gross_pnl(self):
        m,o=fixtures()
        journal=journal_rows(compare(m,o,NOW),"CFB").head(1)
        journal["paper_status"]="PAPER_CLOSED"
        journal["paper_shares"]=2
        journal["paper_fill_price_cents"]=40
        journal["settlement_result"]="WIN"
        stats=paper_summary(import_history(journal.to_csv(index=False).encode("utf-8")))
        self.assertAlmostEqual(stats["gross_pnl"],1.2)
    def test_no_vig_even(self):
        a,b=no_vig(-110,-110)
        self.assertAlmostEqual(a,0.5)
        self.assertAlmostEqual(b,0.5)
    def test_fee_grouping(self):
        self.assertLessEqual(taker_fee(15,10),10*taker_fee(15,1))
    def test_valid_fixture(self):
        m,o=fixtures()
        result=compare(m,o,NOW)
        self.assertEqual(len(result),2)
        self.assertEqual(set(result.side),{"YES","NO"})
    def test_stale_quote_excluded(self):
        m,o=fixtures()
        o["updated"]=(NOW-timedelta(minutes=30)).isoformat()
        self.assertTrue(compare(m,o,NOW).empty)
    def test_duplicate_book_excluded(self):
        m,o=fixtures()
        o["book_key"]="same"
        self.assertTrue(compare(m,o,NOW).empty)
    def test_wrong_kickoff_excluded(self):
        m,o=fixtures()
        o.loc[1,"start"]=(NOW+timedelta(hours=5)).isoformat()
        self.assertTrue(compare(m,o,NOW).empty)
    def test_wrong_opponent_excluded(self):
        m,o=fixtures()
        o["away"]="Auburn"
        self.assertTrue(compare(m,o,NOW).empty)
    def test_true_even_median(self):
        m,o=fixtures()
        o.loc[0,"odds_a"]=-200
        o.loc[0,"odds_b"]=150
        r=compare(m,o,NOW)
        self.assertEqual(len(r),2)
        self.assertAlmostEqual(float(r[r.side=="YES"].iloc[0].fair_pct),56.25,places=1)

if __name__=="__main__":
    unittest.main()
