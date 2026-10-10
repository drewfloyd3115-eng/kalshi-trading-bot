"""Paper-only comparison of alternative routes using public orderbook depth."""
import pandas as pd
from liquidity import inspect
from edge_engine import taker_fee
from config import MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT

def review_routes(matches, bankroll, exposure, max_outcomes=3):
    fields=["event","outcome_team","ticker","side","preliminary_edge_pp","depth_ask_cents","shares","estimated_total","depth_edge_pp","reason","status"]
    if matches is None or matches.empty or bankroll<=0:
        return pd.DataFrame(columns=fields)
    budget=max(0,min(bankroll*MAX_TRADE_BANKROLL_PCT,bankroll*MAX_TOTAL_EXPOSURE_PCT-exposure))
    outcomes=matches.groupby(["event","outcome_team"])["net_edge_pp_1share"].max().nlargest(max_outcomes)
    records=[]
    for (event,team),_ in outcomes.items():
        subset=matches[(matches["event"]==event)&(matches["outcome_team"]==team)]
        for _,route in subset.iterrows():
            record={"event":event,"outcome_team":team,"ticker":route["ticker"],"side":route["side"],"preliminary_edge_pp":route["net_edge_pp_1share"],"status":"NO VERIFIED TRADE"}
            try:
                snapshot=inspect(route["ticker"],route["side"],10)
                if snapshot.get("status")!="DEPTH SNAPSHOT — NOT VERIFIED TRADE":
                    record["reason"]=snapshot.get("reason","No depth")
                else:
                    gross=0.0
                    fees=0.0
                    count=0
                    for ask,available in snapshot["levels"]:
                        for _ in range(min(int(available),10-count)):
                            newgross=gross+ask/100
                            newfees=fees+taker_fee(ask,1)
                            if newgross+newfees>budget:
                                break
                            gross,fees,count=newgross,newfees,count+1
                    if count:
                        edge=float(route["fair_pct"])-100*(gross+fees)/count
                        record.update(depth_ask_cents=snapshot["best_ask_cents"],shares=count,estimated_total=round(gross+fees,2),depth_edge_pp=round(edge,2))
                        record["reason"]="Below 5pp threshold" if edge<MIN_EDGE_PP else "Above threshold, but fees and market rules not verified"
                    else:
                        record["reason"]="Insufficient depth or bankroll allowance"
            except Exception as exc:
                record["reason"]="Orderbook unavailable: "+str(exc)[:90]
            records.append(record)
    return pd.DataFrame(records,columns=fields)
