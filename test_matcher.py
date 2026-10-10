"""Offline regression checks: no API calls, no orders."""
import unittest
from datetime import datetime,timezone,timedelta
import pandas as pd
from edge_engine import no_vig,taker_fee
from matcher import compare

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
