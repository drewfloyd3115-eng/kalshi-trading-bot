"""Read-only quote/depth checks for Kalshi binary contracts.

Kalshi orderbooks contain resting bids. A YES buy lifts NO bids
at complementary prices; a NO buy lifts YES bids.
"""
from datetime import datetime, timezone
from scanner import fetch_orderbook, _get, _cents
from edge_engine import taker_fee

def _levels(raw):
    levels = []
    for row in raw:
        try:
            price, size = float(row[0]), float(row[1])
            if price <= 1:
                price *= 100
            if 0 < price < 100 and size > 0:
                levels.append((round(price, 2), int(size)))
        except (TypeError, ValueError, IndexError):
            continue
    return levels

def inspect(ticker, side, max_shares=10):
    if side not in ("YES", "NO") or not ticker:
        raise ValueError("Need exact ticker and YES/NO side")
    market = _get("/markets/" + ticker).get("market", {})
    if market.get("status") not in ("open", "active"):
        return {"status": "NO TRADE", "reason": "Market is not open"}
    book = fetch_orderbook(ticker)
    opposing = _levels(book["no_bids"] if side == "YES" else book["yes_bids"])
    # Highest opposing bid corresponds to cheapest executable ask.
    levels = sorted([(round(100-p, 2), qty) for p, qty in opposing], key=lambda x:x[0])
    if not levels:
        return {"status": "NO TRADE", "reason": "No executable opposing bids"}
    remaining = max_shares
    fills = []
    for ask, qty in levels:
        take = min(remaining, qty)
        if take:
            fills.append((ask, take))
            remaining -= take
        if not remaining:
            break
    shares = sum(q for _, q in fills)
    gross = sum(p*q/100 for p,q in fills)
    fee_est = sum(taker_fee(p, q) for p,q in fills)
    return {"status": "DEPTH SNAPSHOT — NOT VERIFIED TRADE",
            "ticker": ticker, "side": side, "best_ask_cents": levels[0][0],
            "best_ask_shares": levels[0][1], "shares_covered": shares,
            "requested_shares": max_shares, "levels": fills,
            "gross_cost": round(gross, 2), "estimated_fees": round(fee_est, 2),
            "estimated_total": round(gross+fee_est, 2),
            "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": "Snapshot can change; fees and market rules require confirmation"}
