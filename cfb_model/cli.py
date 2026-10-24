"""Offline-first CFB modeling CLI. Run: python -m cfb_model.cli --help"""
import argparse
import json
import os
from pathlib import Path
import pandas as pd
from .data import fetch_years, read_games_csv
from .core import walk_forward
from .backtest import score_predictions, evaluate_quote_history


def main(argv=None):
    cli=argparse.ArgumentParser(description="Paper-only CFB model")
    subs=cli.add_subparsers(dest="command",required=True)
    sync=subs.add_parser("sync",help="Fetch REAL games from CFBD using your API key")
    sync.add_argument("--start",type=int,default=2018)
    sync.add_argument("--end",type=int,default=2026)
    sync.add_argument("--out",default="data/cfbd_games.csv")
    run=subs.add_parser("backtest",help="Walk-forward projections and historical accuracy")
    run.add_argument("--games",required=True)
    run.add_argument("--holdout-year",type=int,default=2025)
    run.add_argument("--out",default="data/pregame_predictions.csv")
    run.add_argument("--quotes",help="OPTIONAL actual timestamped historical market quotes")
    a=cli.parse_args(argv)
    if a.command=="sync":
        token=os.getenv("CFBD_API_KEY","")
        data=fetch_years(a.start,a.end,token)
        Path(a.out).parent.mkdir(parents=True,exist_ok=True)
        data.to_csv(a.out,index=False)
        print(f"Saved {len(data)} real fixtures to {a.out}")
    elif a.command=="backtest":
        games=read_games_csv(a.games)
        pre,model=walk_forward(games)
        Path(a.out).parent.mkdir(parents=True,exist_ok=True)
        pre.to_csv(a.out,index=False)
        print(json.dumps(score_predictions(pre,a.holdout_year),indent=2))
        print(f"Saved {len(pre)} timestamp-ordered pregame forecasts to {a.out}")
        if a.quotes:
            paper=evaluate_quote_history(pre,pd.read_csv(a.quotes))
            print(f"Historical verified-quote rows: {len(paper)}; total paper P&L: ${paper.paper_pnl.sum():.2f}")
            paper.to_csv(Path(a.out).with_name("historical_paper_pnl.csv"),index=False)


if __name__=="__main__":main()
