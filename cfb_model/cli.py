"""Offline-first CFB modeling CLI. Run: python -m cfb_model.cli --help"""
import argparse
import json
import os
from pathlib import Path
import pandas as pd
from .data import fetch_years, fetch_public_years, read_games_csv
from .core import walk_forward
from .backtest import score_predictions, evaluate_quote_history
from .historical_market import (
    calibration_table, benchmark_predictions, normalize_closing_lines,
    fetch_cfbd_closing_lines
)


def main(argv=None):
    cli=argparse.ArgumentParser(description="Paper-only CFB model")
    subs=cli.add_subparsers(dest="command",required=True)
    sync=subs.add_parser("sync",help="Fetch REAL games from CFBD using your API key")
    sync.add_argument("--start",type=int,default=2018)
    sync.add_argument("--end",type=int,default=2026)
    sync.add_argument("--out",default="data/cfbd_games.csv")
    pub=subs.add_parser("sync-public",help="Fetch free public FBS game scores (2020–2026)")
    pub.add_argument("--start",type=int,default=2020)
    pub.add_argument("--end",type=int,default=2026)
    pub.add_argument("--out",default="data/fbs_public_games.csv")
    run=subs.add_parser("backtest",help="Walk-forward projections and historical accuracy")
    run.add_argument("--games",required=True)
    run.add_argument("--holdout-year",type=int,default=2025)
    run.add_argument("--out",default="data/pregame_predictions.csv")
    run.add_argument("--quotes",help="OPTIONAL actual timestamped historical market quotes")
    bench=subs.add_parser("benchmark",help="Market paired-MAE benchmark; never computes betting ROI")
    bench.add_argument("--predictions",required=True,help="Previously exported timestamped pregame forecasts CSV")
    bench.add_argument("--lines",help="Real closing lines CSV with exact game IDs (optional with --fetch-cfbd)")
    bench.add_argument("--fetch-cfbd",action="store_true",help="One real CFBD request using CFBD_API_KEY")
    bench.add_argument("--provider",default="consensus",choices=["consensus","DraftKings","Caesars","Bovada","teamrankings"])
    bench.add_argument("--holdout-year",type=int,default=2025)
    bench.add_argument("--out",default="data/cfb_paired_closing_line_benchmark.csv")
    a=cli.parse_args(argv)
    if a.command=="sync":
        token=os.getenv("CFBD_API_KEY","")
        data=fetch_years(a.start,a.end,token)
        Path(a.out).parent.mkdir(parents=True,exist_ok=True)
        data.to_csv(a.out,index=False)
        print(f"Saved {len(data)} real fixtures to {a.out}")
    elif a.command=="sync-public":
        data=fetch_public_years(a.start,a.end)
        Path(a.out).parent.mkdir(parents=True,exist_ok=True)
        data.to_csv(a.out,index=False)
        print(f"Saved {len(data)} real public FBS fixtures to {a.out} (source: jackwarfield/cfb_rankings)")
    elif a.command=="benchmark":
        if bool(a.lines) == bool(a.fetch_cfbd):
            cli.error("Provide exactly one of --lines CSV or --fetch-cfbd")
        forecasts=pd.read_csv(a.predictions)
        if a.fetch_cfbd:
            lines=fetch_cfbd_closing_lines(a.holdout_year,os.getenv("CFBD_API_KEY",""),a.provider)
        else:
            lines=normalize_closing_lines(pd.read_csv(a.lines))
        report,matched=benchmark_predictions(forecasts,lines,a.holdout_year)
        destination=Path(a.out)
        destination.parent.mkdir(parents=True,exist_ok=True)
        matched.to_csv(destination,index=False)
        cal=calibration_table(forecasts,a.holdout_year)
        cal.to_csv(destination.with_name("cfb_probability_calibration.csv"),index=False)
        print(json.dumps(report,indent=2))
        print(f"Saved {len(matched)} paired records to {destination}; market lines are NOT historical executable prices.")
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
