"""Fail-closed contract validation for paper research. No sportsbook calls or orders."""
from datetime import datetime, timezone, timedelta
import re
from urllib.parse import quote
from scanner import _get, fetch_orderbook
from liquidity import _levels
from edge_engine import taker_fee

def timing_gate(kickoff_utc, now=None):
    """Only an independently supplied kickoff can establish pregame timing."""
    now=now or datetime.now(timezone.utc)
    if not kickoff_utc:
        return "UNKNOWN — NO INDEPENDENT KICKOFF"
    try:
        kickoff=datetime.fromisoformat(str(kickoff_utc).replace("Z","+00:00"))
        if kickoff.tzinfo is None:
            return "UNKNOWN — KICKOFF LACKS TIMEZONE"
        return "PREGAME" if now < kickoff else "STARTED OR PAST KICKOFF — BLOCKED"
    except (ValueError,TypeError):
        return "UNKNOWN — INVALID KICKOFF"

def validate_contract(ticker, side, shares=1, kickoff_utc=None):
    if not ticker or side not in ("YES","NO") or not isinstance(shares,int) or not 1<=shares<=100:
        raise ValueError("Provide exact ticker, YES/NO side and 1–100 shares")
    now=datetime.now(timezone.utc)
    checked=now.isoformat(timespec="seconds")
    result={"ticker":ticker,"side":side,"shares_requested":shares,"checked_utc":checked,
            "market_status":"UNKNOWN","best_ask_cents":None,"shares_available":0,
            "depth_complete":False,"gross_cost_usd":None,"general_fee_estimate_usd":None,
            "fee_schedule_verified":False,"settlement_rules_verified":False,
            "executable_price_verified":False,"status":"NO VERIFIED TRADE",
            "reason":"Market, fees and settlement not independently verified",
            "kickoff_utc":str(kickoff_utc or ""),
            "pregame_timing":timing_gate(kickoff_utc,now)}
    try:
        market=_get("/markets/"+quote(ticker,safe="")).get("market",{})
        result["market_status"]=str(market.get("status","UNKNOWN"))
        result["rules_primary"]=str(market.get("rules_primary") or "")[:1200]
        result["rules_secondary"]=str(market.get("rules_secondary") or "")[:1200]
        result["fee_type"]=str(market.get("fee_type") or "NOT PROVIDED")
        result["fee_status"]="UNVERIFIED — contract-specific fee schedule not established"
        result["fee_multiplier"]=market.get("fee_multiplier")
        result["close_time"]=str(market.get("close_time") or "")
        if result["pregame_timing"] != "PREGAME":
            result["reason"]="Pregame kickoff not independently confirmed; depth shown for research only"
        if market.get("status") not in ("open","active"):
            result["reason"]="Market is not open"
            return result
        book=fetch_orderbook(ticker)
        opposing=_levels(book["no_bids"] if side=="YES" else book["yes_bids"])
        asks=sorted(((round(100-p,4),int(qty)) for p,qty in opposing),key=lambda x:x[0])
        if not asks:
            result["reason"]="No opposing bids to lift"
            return result
        result["best_ask_cents"]=asks[0][0]
        remaining=shares
        fills=[]
        for price,qty in asks:
            take=min(remaining,qty)
            if take>0:
                fills.append((price,take))
                remaining-=take
            if remaining==0:
                break
        result["shares_available"]=shares-remaining
        result["depth_complete"]=remaining==0
        result["gross_cost_usd"]=round(sum(p*q/100 for p,q in fills),4)
        result["general_fee_estimate_usd"]=round(sum(taker_fee(p,q) for p,q in fills),2)
        if remaining != 0:
            result["reason"]="Insufficient depth for requested shares"
        elif result["pregame_timing"] != "PREGAME":
            result["reason"]="Depth snapshot available, but kickoff is unverified or game has started; no pregame approval"
        else:
            result["reason"]="Pregame timing supplied; depth is a snapshot only. Fees, rules and execution unverified."
    except Exception as exc:
        result["reason"]="Read-only market/depth lookup failed: "+str(exc)[:160]
    return result
