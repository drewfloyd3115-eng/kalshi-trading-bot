"""Rank alternative Kalshi contracts paying on the same team's victory.

These are indicative one-share comparisons, NOT executable opportunities.
"""
import pandas as pd

def equivalent_routes(matches):
    columns=["event","outcome_team","routes","best_ticker","best_side",
             "best_ask_cents","best_preliminary_net_edge_pp","alternate_routes",
             "status"]
    if matches is None or matches.empty or "outcome_team" not in matches.columns:
        return pd.DataFrame(columns=columns)
    rows=[]
    for (event,team), group in matches.groupby(["event","outcome_team"],dropna=True):
        if not team:
            continue
        ranked=group.sort_values("net_edge_pp_1share",ascending=False)
        best=ranked.iloc[0]
        rows.append({"event":event,"outcome_team":team,
            "routes":len(group),"best_ticker":best["ticker"],"best_side":best["side"],
            "best_ask_cents":best["ask_cents"],
            "best_preliminary_net_edge_pp":best["net_edge_pp_1share"],
            "alternate_routes":"; ".join(str(r["ticker"])+":"+str(r["side"]) for _,r in ranked.iloc[1:].iterrows()),
            "status":"INDICATIVE ONLY — no executable depth verified"})
    return pd.DataFrame(rows,columns=columns).sort_values("best_preliminary_net_edge_pp",ascending=False)
