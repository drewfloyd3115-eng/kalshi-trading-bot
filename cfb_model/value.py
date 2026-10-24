"""Fee-aware research pricing; never assumes a fill or checks order placement."""
from __future__ import annotations
import math
from dataclasses import dataclass


def taker_fee(price_cents: float, shares: int = 1, multiplier: float = 1.0) -> float:
    if not 0 < price_cents < 100 or shares < 1 or int(shares) != shares or multiplier < 0:
        raise ValueError("Invalid price, number of shares, or fee multiplier")
    p = price_cents / 100
    return math.ceil((.07*multiplier*shares*p*(1-p))*100-1e-10)/100


def evaluate(fair_probability: float, price_cents: float, shares: int = 10,
             multiplier: float = 1.0, min_edge_pp: float = 5.0):
    if not 0 <= fair_probability <= 1 or not 0 < price_cents < 100 or shares < 1:
        raise ValueError("Invalid probability, price, or share count")
    fee = taker_fee(price_cents, shares, multiplier)
    total_cost = shares*price_cents/100 + fee
    expected_payout = shares*fair_probability
    ev = expected_payout - total_cost
    edge_pp = 100*(fair_probability - total_cost/shares)
    return {"fair_pct":round(fair_probability*100,2),
            "ask_cents":price_cents, "shares":shares, "fee_usd":fee,
            "cost_usd":round(total_cost,2), "expected_profit_usd":round(ev,4),
            "expected_roi_pct":round(100*ev/total_cost,2),
            "net_edge_pp":round(edge_pp,2),
            "status":"PAPER CANDIDATE — VALIDATION REQUIRED" if edge_pp>=min_edge_pp else "PASS"}


def max_buy_price(fair: float, shares: int = 10, multiplier:float=1.0, min_edge_pp:float=5.0):
    for cents in range(99,0,-1):
        if evaluate(fair,cents,shares,multiplier,min_edge_pp)["net_edge_pp"] >= min_edge_pp-1e-9:
            return cents
    return None


def from_orderbook(book: dict, side: str, shares: int):
    """Public bid-side book -> hypothetical BUY asks. Cannot certify executability.

    Buy YES takes the best NO bid complement; buy NO takes best YES bid complement.
    Reject insufficient depth rather than pretending the top-of-book size is enough.
    """
    if side not in ("YES","NO") or shares < 1:
        raise ValueError("Invalid side or shares")
    levels = book.get("no_bids" if side == "YES" else "yes_bids", [])
    levels = sorted(((float(p),math.floor(float(q))) for p,q in levels
                     if 0<float(p)<100 and float(q)>=1), reverse=True)
    remaining = shares
    total_cents = 0.0
    fills=[]
    for bid,quantity in levels:
        take = min(quantity,remaining)
        if take<=0:
            continue
        buy_price = round(100-bid, 4)
        total_cents += take*buy_price
        fills.append((buy_price,take))
        remaining-=take
        if remaining==0:
            break
    if remaining:
        return {"status":"INSUFFICIENT OBSERVED DEPTH", "available_shares":shares-remaining,
                "requested_shares":shares,"levels":fills}
    return {"status":"OBSERVED BID DEPTH ONLY", "requested_shares":shares,
            "available_shares":shares,"average_ask_cents":round(total_cents/shares,4),"levels":fills}


def historical_outcome(home_points,away_points,outcome,line=None):
    hp, ap = float(home_points),float(away_points)
    if outcome == "HOME_WIN": return hp>ap
    if outcome == "AWAY_WIN": return ap>hp
    if outcome in ("HOME_COVER","AWAY_COVER","OVER","UNDER"):
        if line is None or abs(float(line)*2-round(float(line)*2))>1e-8 or int(float(line)*2)%2==0:
            raise ValueError("Use half-point lines only; integer/push settlement must be explicitly verified")
        if outcome == "HOME_COVER": return hp-ap+float(line)>0
        if outcome == "AWAY_COVER": return hp-ap+float(line)<0
        if outcome == "OVER": return hp+ap>float(line)
        if outcome == "UNDER": return hp+ap<float(line)
    raise ValueError("Unknown outcome")
