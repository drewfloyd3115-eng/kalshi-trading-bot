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
    if odds is not None and not odds.empty and markets is not None and not markets.empty:
        for (league,home,away),group in odds.groupby(["league","home","away"]):
            tickers=set()
            for _,market in markets[markets["league"]==league].iterrows():
                parts=re.split(r"\s+(?:vs\.?|versus|at|@)\s+",str(market.get("event","")),flags=re.I)
                if len(parts)==2 and {normalized(x) for x in parts}=={normalized(home),normalized(away)}:
                    tickers.add(str(market.get("ticker")))
            partial=[]
            for _,m in markets[markets["league"]==league].iterrows():
                parts=re.split(r"\\s+(?:vs\\.?|versus|at|@)\\s+",str(m.get("event","")),flags=re.I)
                if len(parts)==2 and ({normalized(home),normalized(away)} & {normalized(p) for p in parts}):
                    partial.append(str(m.get("event")))
            nearest[(league,str(away)+" @ "+str(home))]="; ".join(sorted(set(partial))[:3])
            counts[(league,str(away)+" @ "+str(home))]=sum(
                int((comparisons["ticker"]==ticker).sum()) for ticker in tickers & matched)
    result["matched_contract_sides"]=[
        counts.get((r["league"],r["game"]),0) for _,r in result.iterrows()]
    result["partial_event_candidates"]=[nearest.get((r["league"],r["game"]),"") for _,r in result.iterrows()]
    result["status"]=result.apply(
        lambda r:"MATCHED" if r["matched_contract_sides"]>0 else
        ("CANDIDATE — NOT MATCHED" if r["kalshi_event_candidates"]>0 else "EXCLUDED"),axis=1)
    return result
