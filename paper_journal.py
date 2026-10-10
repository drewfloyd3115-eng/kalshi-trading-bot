"""Paper-only scan journal. CSV stays in session; no real orders."""
from datetime import datetime, timezone
import pandas as pd

COLUMNS=["scan_utc","league","event","outcome_team","ticker","side","ask_cents","fair_pct","edge_pp","books","decision","fee_verified","settlement_verified","execution_verified"]

def journal_rows(comparisons, league, scan_time=None):
    if comparisons is None or comparisons.empty:
        return pd.DataFrame(columns=COLUMNS)
    timestamp=scan_time or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows=[]
    # Save one best indicative route per unique winning outcome.
    for _,r in comparisons.sort_values("net_edge_pp_1share",ascending=False).drop_duplicates(["event","outcome_team"]).iterrows():
        rows.append(dict(scan_utc=timestamp,league=league,event=r["event"],outcome_team=r["outcome_team"],
            ticker=r["ticker"],side=r["side"],ask_cents=r["ask_cents"],fair_pct=r["fair_pct"],
            edge_pp=r["net_edge_pp_1share"],books=r["books"],decision="WATCH ONLY — UNVERIFIED",
            fee_verified=False,settlement_verified=False,execution_verified=False))
    return pd.DataFrame(rows,columns=COLUMNS)
