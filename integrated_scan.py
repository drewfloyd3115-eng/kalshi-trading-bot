"""Bounded, read-only paper scanner with risk caps. No trade instructions."""
from datetime import datetime, timezone, timedelta
import pandas as pd
from config import MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT
from liquidity import inspect
from edge_engine import taker_fee

def scan_candidates(matches, bankroll, exposure, max_checks=5):
    if matches is None or matches.empty:
        return pd.DataFrame()
    if bankroll <= 0 or exposure < 0:
        raise ValueError("Invalid bankroll/exposure")
    budget = max(0.0, min(bankroll*MAX_TRADE_BANKROLL_PCT,
                          bankroll*MAX_TOTAL_EXPOSURE_PCT-exposure))
    results = []
    # Only top preliminary edges; bounded API calls and never touch negative edges.
    eligible = matches[matches["net_edge_pp_1share"] >= MIN_EDGE_PP].head(max_checks)
    for _, row in eligible.iterrows():
        record = {"event": row["event"], "ticker": row["ticker"],
                  "side": row["side"], "fair_pct": row["fair_pct"],
                  "books": row["books"], "status": "NO TRADE"}
        try:
            if budget < 0.02:
                record["reason"] = "Insufficient risk budget"
            else:
                snapshot = inspect(row["ticker"], row["side"], 100)
                if snapshot["status"] != "DEPTH SNAPSHOT — NOT VERIFIED TRADE":
                    record["reason"] = snapshot.get("reason", "No usable depth")
                else:
                    levels = snapshot["levels"]
                    count, gross, fee = 0, 0.0, 0.0
                    # Charge estimated fees per executed depth level, not on the last level alone.
                    fills = []
                    for ask, qty in levels:
                        level_count = 0
                        for _ in range(int(qty)):
                            next_level_count = level_count + 1
                            proposed_fee = (fee - (taker_fee(ask, level_count) if level_count else 0)
                                            + taker_fee(ask, next_level_count))
                            proposed_gross = gross + ask/100
                            if proposed_gross + proposed_fee > budget + 1e-9:
                                break
                            gross, fee = proposed_gross, proposed_fee
                            level_count, count = next_level_count, count + 1
                        if level_count:
                            fills.append((ask, level_count))
                    fee = sum(taker_fee(price, qty) for price, qty in fills)
                    if count == 0:
                        record["reason"] = "No affordable shares at depth"
                    else:
                        edge = float(row["fair_pct"]) - 100*(gross+fee)/count
                        record.update(shares=count, estimated_cost=round(gross+fee,2),
                                      net_edge_pp=round(edge,2),
                                      best_ask_cents=snapshot["best_ask_cents"],
                                      checked_utc=snapshot["checked_utc"])
                        if edge >= MIN_EDGE_PP:
                            record["status"] = "PAPER REVIEW ONLY"
                            record["reason"] = "Fresh sportsbook prices, exact fees, injury and market rules not independently revalidated"
                        else:
                            record["reason"] = "Net edge below minimum after depth and fees"
        except Exception as exc:
            record["reason"] = "Liquidity check failed: " + str(exc)[:120]
        results.append(record)
    return pd.DataFrame(results)
