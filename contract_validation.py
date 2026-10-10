"""Fail-closed contract validation for paper research. No sportsbook calls or orders."""
from datetime import datetime, timezone
from urllib.parse import quote
from scanner import _get, fetch_orderbook, _cents
from liquidity import _levels
from edge_engine import taker_fee

def validate_contract(ticker, side, shares=1):
    if not ticker or side not in ("YES","NO") or not isinstance(shares,int) or not 1<=shares<=100:
        raise ValueError("Provide exact ticker, YES/NO side and 1–100 shares")
    checked=datetime.now(timezone.utc).isoformat(timespec="seconds")
    result={"ticker":ticker,"side":side,"shares_requested":shares,"checked_utc":checked,
            "market_status":"UNKNOWN","best_ask_cents":None,"shares_available":0,
            "depth_complete":False,"gross_cost_usd":None,"general_fee_estimate_usd":None,
            "fee_schedule_verified":False,"settlement_rules_verified":False,
            "executable_price_verified":False,"status":"NO VERIFIED TRADE",
            "reason":"Market, fees and settlement not independently verified"}
    try:
        market=_get("/markets/"+quote(ticker,safe="")).get("market",{})
        result["market_status"]=str(market.get("status","UNKNOWN"))
        result["rules_primary"]=str(market.get("rules_primary") or "")[:1200]
        result["rules_secondary"]=str(market.get("rules_secondary") or "")[:1200]
        result["fee_type"]=str(market.get("fee_type") or "NOT PROVIDED")
        result["fee_multiplier"]=market.get("fee_multiplier")
        result["close_time"]=str(market.get("close_time") or "")
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
        result["reason"]=("Depth snapshot covers requested shares; quote can change. "
                          "Fee schedule and settlement rules remain unverified."
                          if remaining==0 else "Insufficient depth for requested shares")
    except Exception as exc:
        result["reason"]="Read-only market/depth lookup failed: "+str(exc)[:160]
    return result
