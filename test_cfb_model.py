import io
import unittest
from datetime import datetime,timedelta,timezone
import pandas as pd
from cfb_model.data import COLUMNS, normalize_games, parse_games, fetch_year
from cfb_model.core import walk_forward, Forecast, PowerModel
from cfb_model.backtest import score_predictions, evaluate_quote_history
from cfb_model.value import taker_fee, evaluate, max_buy_price, from_orderbook, historical_outcome


def game(i, season=2024, done=True, home='Team A', away='Team B', hp=24, ap=21):
    return dict(game_id=str(i),season=season,week=1,kickoff_utc=(datetime(season,9,1,tzinfo=timezone.utc)+timedelta(days=i%10,hours=i//10)).isoformat(),home_team=home,away_team=away,home_points=hp if done else None,away_points=ap if done else None,completed=done,neutral_site=False)

class ModelTests(unittest.TestCase):
    def test_load_exact(self):
        games=normalize_games(pd.DataFrame([game(2),game(1)]))
        self.assertEqual(games.shape[0],2)
        self.assertEqual(set(games.columns),set(COLUMNS))
    def test_reject_duplicate(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            normalize_games(pd.DataFrame([game(1),game(1)]))
    def test_no_future_scores(self):
        p1,_=walk_forward(pd.DataFrame([game(0,hp=80,ap=20),game(1,done=False)]),min_history=1)
        p2,_=walk_forward(pd.DataFrame([game(0,hp=80,ap=20),game(1,hp=2,ap=9,done=False)]),min_history=1)
        self.assertEqual(float(p1.iloc[1].projected_home_margin),float(p2.iloc[1].projected_home_margin))
        self.assertEqual(int(p1.iloc[1].training_games),1)
    def test_season_regression(self):
        m=PowerModel()
        m.update('Home','Away',60,0)
        before=m.ratings['Home']
        m.new_season(2024)
        m.new_season(2025)
        self.assertAlmostEqual(m.ratings['Home'],before*.7)
    def test_probabilities(self):
        f=Forecast(8,54,.75,16,15,100,6,6)
        self.assertAlmostEqual(f.probability('HOME_WIN'),.75)
        self.assertAlmostEqual(f.probability('AWAY_WIN'),.25)
        self.assertGreater(f.probability('HOME_COVER',-3.5),.5)
        self.assertLess(f.probability('HOME_COVER',-10.5),.5)
        self.assertAlmostEqual(f.probability('HOME_COVER',-3.5)+f.probability('AWAY_COVER',-3.5),1)
        self.assertLess(f.probability('OVER',60.5),.5)
    def test_holdout_empty(self):
        pred,_=walk_forward(pd.DataFrame([game(0),game(1)]))
        self.assertEqual(score_predictions(pred,2025)['games'],0)
    def test_actual_cfbd_parse(self):
        data=[{'id':123,'season':2024,'week':3,'startDate':'2024-09-14T16:00:00.000Z','homeTeam':'Oregon','awayTeam':'Utah','homePoints':28,'awayPoints':14,'completed':True,'homeDivision':'fbs','awayDivision':'fbs'}]
        parsed=parse_games(data)
        self.assertEqual(parsed.home_team.iloc[0],'Oregon')
        self.assertEqual(parsed.home_points.iloc[0],28)
    def test_fetch_requires_key(self):
        with self.assertRaisesRegex(ValueError,'CFBD_API_KEY'):
            fetch_year(2025,'')

class Values(unittest.TestCase):
    def test_fee_rounding(self):
        self.assertEqual(taker_fee(50,100),1.75)
        self.assertEqual(taker_fee(50,1),.02)
        self.assertEqual(taker_fee(50,10),.18)
        self.assertEqual(taker_fee(50,10,0),0)
    def test_edge(self):
        r=evaluate(.60,50,100)
        self.assertEqual(r['status'],'PAPER CANDIDATE — VALIDATION REQUIRED')
        self.assertAlmostEqual(r['net_edge_pp'],8.25)
        self.assertEqual(evaluate(.50,50,100)['status'],'PASS')
        self.assertLessEqual(max_buy_price(.6,100),53)
    def test_book_side_conversion(self):
        book={'yes_bids':[[40,10]],'no_bids':[[44,5],[43,5]]}
        r=from_orderbook(book,'YES',10)
        self.assertEqual(r['average_ask_cents'],56.5)
        self.assertEqual(from_orderbook(book,'NO',10)['average_ask_cents'],60)
        self.assertEqual(from_orderbook(book,'YES',11)['status'],'INSUFFICIENT OBSERVED DEPTH')
    def test_halfpoint_settlement(self):
        self.assertTrue(historical_outcome(24,20,'HOME_COVER',-3.5))
        self.assertFalse(historical_outcome(24,20,'AWAY_COVER',-3.5))
        self.assertTrue(historical_outcome(24,20,'OVER',43.5))
        with self.assertRaises(ValueError):historical_outcome(24,20,'OVER',44.0)
    def test_backtest_anti_lookahead(self):
        d1=game(0)
        d2=game(1)
        pre,_=walk_forward(pd.DataFrame([d1,d2]),min_history=1)
        row=pre.iloc[1]
        q=pd.DataFrame([dict(game_id=str(row.game_id),captured_utc=row.kickoff_utc-pd.Timedelta(hours=1),
                             outcome='HOME_WIN',line=None,ask_cents=48,shares=10,market_ticker='FAKE-HOME',fee_multiplier=1)])
        out=evaluate_quote_history(pre,q)
        self.assertEqual(out.shape[0],1)
        q['captured_utc']=row.kickoff_utc+pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError,'Lookahead'):
            evaluate_quote_history(pre,q)
    def test_backtest_duplicates(self):
        p,_=walk_forward(pd.DataFrame([game(0),game(1)]),min_history=1)
        q=pd.DataFrame([dict(game_id='1',captured_utc='2024-09-01T00:00:00Z',outcome='OVER',line=44.5,ask_cents=50,shares=10,market_ticker='TEST',fee_multiplier=1)]*2)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            evaluate_quote_history(p,q)

if __name__=='__main__': unittest.main()

class IntegrationTests(unittest.TestCase):
    def test_idempotent_patcher(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from apply_integration import apply
        with TemporaryDirectory() as td:
            path=Path(td)
            (path/'cfb_model').mkdir()
            (path/'cfb_model'/'ui.py').write_text('')
            (path/'sports_ui.py').write_text('PAGES = ["Home", "Opportunities", "Market Detail", "Portfolio", "Research"]')
            (path/'app.py').write_text('if page == "Portfolio":\n    pass\nelse:\n    if "quick_results" in st.session_state:\n        pass\n')
            self.assertIn('Integrated',apply(path))
            self.assertEqual(apply(path),'Already integrated')
            self.assertEqual((path/'app.py').read_text().count('elif page == "CFB Model"'),1)

    def test_market_ticker_validation(self):
        from cfb_model.kalshi import fetch_market_and_orderbook
        with self.assertRaisesRegex(ValueError,'Invalid exact'):
            fetch_market_and_orderbook('../admin')
