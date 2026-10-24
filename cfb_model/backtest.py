"""Reproducible retrospective scoring and optional historical-priced PAPER P&L.

Never use today's quotes to backtest historic games. Quotes must have timestamp
before kickoff and be tied to the exact outcome and line in the records.
"""
import pandas as pd
from .core import walk_forward, normal_cdf
from .value import historical_outcome, taker_fee


def score_predictions(predictions: pd.DataFrame, test_season: int = 2025):
    df = predictions[(predictions["completed"]) & (predictions["eligible_history"]) &
                     (predictions["season"] == test_season)].copy()
    if df.empty:
        return {"games":0,"season":test_season,"warning":"No holdout games available; add prior seasons"}
    actual_margin = df.home_points-df.away_points
    actual_total = df.home_points+df.away_points
    target = (actual_margin>0).astype(float)
    preds = df.home_win_prob.clip(.000001,.999999)
    return {"games":len(df), "season":test_season,
            "margin_mae":round((actual_margin-df.projected_home_margin).abs().mean(),3),
            "total_mae":round((actual_total-df.projected_total).abs().mean(),3),
            "win_brier":round(((preds-target)**2).mean(),4),
            "home_win_accuracy":round(((preds>=.5)==(target==1)).mean(),4),
            "warning":"Predictive accuracy is NOT demonstrated profitability"}


def evaluate_quote_history(predictions:pd.DataFrame, quotes:pd.DataFrame):
    """Historical quotes: game_id, captured_utc, outcome, line, ask_cents, shares,
    market_ticker, fee_multiplier. Each contract must be manually verified first.

    Test on holdout forecasts only. Reject timestamps >= kickoff and duplicate
    market snapshots for the same game/outcome; prevent opportunistic best-price bias.
    """
    cols={"game_id","captured_utc","outcome","line","ask_cents","shares","market_ticker","fee_multiplier"}
    if not cols.issubset(quotes.columns):
        raise ValueError("Quote file missing: "+", ".join(sorted(cols-set(quotes.columns))))
    q=quotes.copy()
    q["game_id"]=q["game_id"].astype(str)
    q["captured_utc"]=pd.to_datetime(q.captured_utc,utc=True,errors="coerce")
    if q["captured_utc"].isna().any():raise ValueError("Quote timestamps must be timezone-aware")
    p=predictions.copy()
    p["game_id"]=p["game_id"].astype(str)
    p["kickoff_utc"]=pd.to_datetime(p.kickoff_utc,utc=True)
    if q.duplicated(["game_id","outcome","line"]).any():
        raise ValueError("Duplicate historical snapshots: use one prespecified timestamp per market")
    m=q.merge(p,on="game_id",how="left",validate="many_to_one",indicator=True)
    if (m._merge!="both").any(): raise ValueError("Quote game_id does not match the games dataset")
    if (m.captured_utc>=m.kickoff_utc).any():raise ValueError("Lookahead/post-kickoff quote detected")
    if ((~m.completed) | (~m.eligible_history)).any():
        raise ValueError("Only completed games with sufficient past training history allowed")
    records=[]
    for _,r in m.iterrows():
        line=None if pd.isna(r.line) else float(r.line)
        o=r.outcome
        if o=="HOME_WIN": fair=r.home_win_prob
        elif o=="AWAY_WIN":fair=1-r.home_win_prob
        elif o in ("HOME_COVER","AWAY_COVER"):
            if line is None: raise ValueError("Missing spread line")
            x=normal_cdf((r.projected_home_margin+line)/r.margin_sigma)
            fair=x if o=="HOME_COVER" else 1-x
        elif o in ("OVER","UNDER"):
            if line is None: raise ValueError("Missing total line")
            x=normal_cdf((r.projected_total-line)/r.total_sigma)
            fair=x if o=="OVER" else 1-x
        else:raise ValueError("Invalid outcome "+str(o))
        win=historical_outcome(r.home_points,r.away_points,o,line)
        n=int(r.shares)
        if n!=float(r.shares) or n<1: raise ValueError("Invalid shares")
        fee=taker_fee(float(r.ask_cents),n,float(r.fee_multiplier))
        stake=n*float(r.ask_cents)/100+fee
        edge=100*(fair-stake/n)
        pnl=n*(1 if win else 0)-stake
        records.append({"game_id":r.game_id,"ticker":r.market_ticker,"outcome":o,
                        "fair_pct":round(100*fair,2),"entry_cost":round(stake,2),
                        "model_edge_pp":round(edge,2),"won":bool(win),
                        "paper_pnl":round(pnl,2),"candidate_5pp":edge>=5})
    return pd.DataFrame(records)
