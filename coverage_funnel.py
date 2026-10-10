"""Coverage labels use actual matched contract tickers, not heuristic candidates."""
import re
import pandas as pd
from team_names import normalized

def coverage_funnel(odds, diagnostics, comparisons, markets=None):
    if diagnostics is None or diagnostics.empty:
        return pd.DataFrame()
    result=diagnostics.copy()
    matched=set(comparisons["ticker"].astype(str)) if comparisons is not None and not comparisons.empty else set()
    counts={}
    nearest={}
    market_names={}
    if markets is not None and not markets.empty:
        for league, frame in markets.groupby("league"):
            market_names[league]=sorted(set(str(v) for v in frame["event"].dropna()))
    if odds is not None and not odds.empty and markets is not None and not markets.empty:
        for (league,home,away),group in odds.groupby(["league","home","away"]):
            tickers=set()
            for _,market in markets[markets["league"]==league].iterrows():
                parts=re.split(r"\s+(?:vs\.?|versus|at|@)\s+",str(market.get("event","")),flags=re.I)
                if len(parts)==2 and {normalized(x) for x in parts}=={normalized(home),normalized(away)}:
                    tickers.add(str(market.get("ticker")))
            nearest[(league,str(away)+" @ "+str(home))]="; ".join(sorted(set(str(m.get("event")) for _,m in markets[markets["league"]==league].iterrows() if normalized(home) in [normalized(p) for p in re.split(r"\s+(?:vs\\.?|versus|at|@)\s+",str(m.get("event","")),flags=re.I)] or normalized(away) in [normalized(p) for p in re.split(r"\s+(?:vs\\.?|versus|at|@)\s+",str(m.get("event","")),flags=re.I)]))[:3])
            counts[(league,str(away)+" @ "+str(home))]=sum(
                int((comparisons["ticker"]==ticker).sum()) for ticker in tickers & matched)
    result["matched_contract_sides"]=[
        counts.get((r["league"],r["game"]),0) for _,r in result.iterrows()]
    result["partial_event_candidates"]=[nearest.get((r["league"],r["game"]),"") for _,r in result.iterrows()]
    result["status"]=result.apply(
        lambda r:"MATCHED" if r["matched_contract_sides"]>0 else
        ("CANDIDATE — NOT MATCHED" if r["kalshi_event_candidates"]>0 else "EXCLUDED"),axis=1)
    return result
