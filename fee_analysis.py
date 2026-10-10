"""Read-only fee and entry threshold analysis. General taker schedule assumed."""
from edge_engine import taker_fee
from config import MIN_EDGE_PP
import pandas as pd

def fee_analysis(matches, shares=10):
    columns=["event","ticker","side","fair_pct","ask_cents","shares",
             "fee_one_order","fee_split_orders","net_edge_one_order_pp",
             "max_ask_for_5pp_cents","status"]
    if matches is None or matches.empty:
        return pd.DataFrame(columns=columns)
    rows=[]
    for _,r in matches.iterrows():
        ask=float(r["ask_cents"])
        fair=float(r["fair_pct"])
        fee=taker_fee(ask,shares)
        split=shares*taker_fee(ask,1)
        edge=fair-ask-100*fee/shares
        maximum=None
        for cents in range(99,0,-1):
            if fair-cents-100*taker_fee(cents,shares)/shares>=MIN_EDGE_PP:
                maximum=cents
                break
        rows.append({"event":r["event"],"ticker":r["ticker"],"side":r["side"],
                     "fair_pct":fair,"ask_cents":ask,"shares":shares,
                     "fee_one_order":round(fee,2),"fee_split_orders":round(split,2),
                     "net_edge_one_order_pp":round(edge,2),
                     "max_ask_for_5pp_cents":maximum,
                     "status":"ESTIMATE ONLY — confirm series fee multiplier, execution and rules"})
    return pd.DataFrame(rows,columns=columns).sort_values("net_edge_one_order_pp",ascending=False)
