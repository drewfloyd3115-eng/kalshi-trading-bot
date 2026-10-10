"""CSV-backed paper history; observational scans are never assumed filled."""
import io
import pandas as pd
from paper_journal import COLUMNS

HISTORY_COLUMNS=COLUMNS+["paper_status","paper_fill_price_cents","paper_shares","settlement_result","paper_pnl_usd"]
VALID_STATUS={"OBSERVED","PAPER_FILLED","PAPER_CLOSED"}
VALID_RESULT={"UNRESOLVED","WIN","LOSS"}

def import_history(raw):
    df=pd.read_csv(io.BytesIO(raw))
    missing=[c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Not a paper journal CSV. Missing: "+", ".join(missing))
    df=df.copy()
    for c in ("scan_utc","league","event","outcome_team","ticker","side"):
        df[c]=df[c].fillna("").astype(str)
    for c in ("ask_cents","fair_pct","edge_pp","books"):
        df[c]=pd.to_numeric(df[c],errors="raise")
    for c in ("fee_verified","settlement_verified","execution_verified"):
        df[c]=df[c].astype(str).str.lower().eq("true")
    if not df["side"].isin(["YES","NO"]).all():
        raise ValueError("Invalid contract side")
    if not df["ask_cents"].between(0,100).all():
        raise ValueError("Invalid ask price")
    if not df["fair_pct"].between(0,100).all():
        raise ValueError("Invalid probability")
    for c,default in [("paper_status","OBSERVED"),("paper_fill_price_cents",float("nan")),
                      ("paper_shares",0),("settlement_result","UNRESOLVED"),("paper_pnl_usd",float("nan"))]:
        if c not in df.columns:
            df[c]=default
    if not df["paper_status"].isin(VALID_STATUS).all() or not df["settlement_result"].isin(VALID_RESULT).all():
        raise ValueError("Invalid paper status or settlement result")
    df["paper_shares"]=pd.to_numeric(df["paper_shares"],errors="raise")
    df["paper_fill_price_cents"]=pd.to_numeric(df["paper_fill_price_cents"],errors="coerce")
    df["paper_pnl_usd"]=pd.to_numeric(df["paper_pnl_usd"],errors="coerce")
    if (df["paper_shares"]<0).any() or (df["paper_shares"]%1!=0).any():
        raise ValueError("Invalid share quantity")
    if ((df["paper_status"]=="PAPER_CLOSED") & (df["settlement_result"]=="UNRESOLVED")).any():
        raise ValueError("Closed paper positions require a settlement result")
    if ((df["paper_status"]=="PAPER_CLOSED") & (df["paper_shares"]<=0)).any():
        raise ValueError("Closed paper positions require positive shares")
    if ((df["paper_status"]=="PAPER_CLOSED") & ~df["paper_fill_price_cents"].between(0,100)).any():
        raise ValueError("Closed paper positions require a valid fill price")
    if ((df["paper_status"]=="OBSERVED") & (df["settlement_result"]!="UNRESOLVED")).any():
        raise ValueError("Observed quotes cannot be settled as positions")
    # Never trust uploaded P&L. Recompute using price and quantity, excluding unverified fees.
    df["paper_pnl_usd"]=float("nan")
    closed=df["paper_status"]=="PAPER_CLOSED"
    wins=df["settlement_result"]=="WIN"
    df.loc[closed,"paper_pnl_usd"]=(
        df.loc[closed,"paper_shares"]*
        ((wins.loc[closed].astype(int)*100-df.loc[closed,"paper_fill_price_cents"])/100))
    return df[HISTORY_COLUMNS].drop_duplicates(subset=["scan_utc","league","ticker","side","outcome_team"],keep="last")

def summary(df):
    closed=df[df["paper_status"]=="PAPER_CLOSED"] if not df.empty else df
    return {"observations":len(df),"paper_fills":int(df["paper_status"].isin(["PAPER_FILLED","PAPER_CLOSED"]).sum()) if not df.empty else 0,
            "closed":len(closed),"wins":int((closed["settlement_result"]=="WIN").sum()) if not closed.empty else 0,
            "gross_pnl":round(float(closed["paper_pnl_usd"].sum()),2) if not closed.empty else 0.0}
