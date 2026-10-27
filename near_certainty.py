"""Paper-only scanner for high-priced binary markets. No orders, API keys, or fills.

Indicative asks from market metadata are screening hints. Opposite-side bids
on a public order-book snapshot are observable depth, NOT confirmed fills.
Never infer true probabilities from market prices.
"""
from datetime import datetime, timezone
import math
import re
import pandas as pd
from config import MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT
from edge_engine import taker_fee

WATCH_COLUMNS = ["league", "event", "ticker", "side", "indicative_ask_cents",
                 "volume", "close_time", "status"]
TICKER_PATTERN = re.compile(r"^[A-Z0-9_-]{3,128}$")


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def watchlist(markets, lower=90.0, upper=99.0, limit=75, now=None):
    """Screen CFB/NFL game-winner market rows; never identify a tradable edge."""
    if not 0 < lower <= upper < 100 or not 1 <= limit <= 500:
        raise ValueError("Invalid watchlist range or limit")
    if markets is None or markets.empty:
        return pd.DataFrame(columns=WATCH_COLUMNS)
    clock = now or datetime.now(timezone.utc)
    records = []
    for _, item in markets.iterrows():
        ticker = str(item.get("ticker") or "").strip()
        if not TICKER_PATTERN.fullmatch(ticker):
            continue
        close = str(item.get("close_time") or "")
        if close:
            try:
                close_dt = datetime.fromisoformat(close.replace("Z", "+00:00"))
                if close_dt.tzinfo is not None and close_dt <= clock:
                    continue
            except (TypeError, ValueError):
                pass
        for side in ("YES", "NO"):
            ask = finite(item.get(side.lower() + "_ask_cents"))
            if ask is None or not lower <= ask <= upper:
                continue
            records.append({
                "league": str(item.get("league") or ""),
                "event": str(item.get("event") or ""),
                "ticker": ticker, "side": side,
                "indicative_ask_cents": round(ask, 3),
                "volume": item.get("volume"), "close_time": close,
                "status": "WATCH ONLY — depth, fees and true probability unverified",
            })
    records.sort(key=lambda item: (-item["indicative_ask_cents"], item["ticker"], item["side"]))
    return pd.DataFrame(records[:limit], columns=WATCH_COLUMNS)


def inspect_one_share(book, side, bankroll=100.0, open_exposure=0.0,
                      fair_probability=None, fee_multiplier=1.0):
    """Simulate one WHOLE-share buy by lifting one opposing resting bid.

    Standard quadratic fee is only a fee ASSUMPTION, not series verification.
    The function cannot authorize any trade or create any paper fill.
    """
    if side not in ("YES", "NO"):
        raise ValueError("Invalid YES/NO side")
    bank, exposure, multiplier = (finite(bankroll), finite(open_exposure),
                                  finite(fee_multiplier))
    if bank is None or bank <= 0 or exposure is None or exposure < 0 or multiplier is None or multiplier < 0:
        raise ValueError("Invalid bankroll, exposure or fee multiplier")
    fair = None if fair_probability is None else finite(fair_probability)
    if fair_probability is not None and (fair is None or not 0 <= fair <= 1):
        raise ValueError("Probability must be between zero and one")
    if not isinstance(book, dict):
        raise ValueError("Malformed order book")
    levels = book.get("no_bids" if side == "YES" else "yes_bids")
    if not isinstance(levels, list):
        raise ValueError("Opposite-side order book missing")
    choices = []
    for level in levels:
        if not isinstance(level, (tuple, list)) or len(level) < 2:
            continue
        price, count = finite(level[0]), finite(level[1])
        if price is not None and count is not None and 0 < price < 100 and count >= 1:
            choices.append((round(100 - price, 4), math.floor(count)))
    base = {
        "side": side, "sample_checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quote_age_verified": False, "fee_verified": False,
        "settlement_verified": False, "real_order_placed": False,
        "paper_fill_recorded": False,
    }
    if not choices:
        return {**base, "status": "NO DEPTH — WATCH ONLY",
                "blockers": ["No whole-share opposing resting bid available"]}
    ask, depth = min(choices)
    fee = taker_fee(ask, 1, multiplier)
    cost = ask/100 + fee
    edge_pp = None if fair is None else 100 * (fair - cost)
    blockers = []
    if cost > bank * MAX_TRADE_BANKROLL_PCT + 1e-9:
        blockers.append("Per-position 1% bankroll limit exceeded")
    if exposure + cost > bank * MAX_TOTAL_EXPOSURE_PCT + 1e-9:
        blockers.append("Aggregate 3% bankroll exposure limit exceeded")
    if edge_pp is None:
        blockers.append("Independent calibrated probability missing")
    elif edge_pp < MIN_EDGE_PP - 1e-9:
        blockers.append("Fails +5 percentage-point net edge threshold")
    blockers.append("Exact fee override, contract settlement and source depth age unverified")
    return {
        **base, "status": "WATCH ONLY — UNVERIFIED",
        "indicative_ask_cents": ask, "whole_share_depth_at_best": depth,
        "paper_shares_proposed": 1, "assumed_fee_usd": round(fee, 4),
        "cost_usd": round(cost, 4),
        "profit_if_wins_usd": round(1-cost, 4),
        "loss_if_loses_usd": round(cost, 4),
        "break_even_probability_pct": round(100*cost, 2),
        "required_probability_for_5pp_pct": round(100*(cost+MIN_EDGE_PP/100), 2),
        "maximum_possible_edge_pp": round(100*(1-cost), 2),
        "manual_probability_pct": None if fair is None else round(100*fair, 2),
        "net_edge_pp": None if edge_pp is None else round(edge_pp, 2),
        "expected_value_usd": None if fair is None else round(fair-cost, 4),
        "per_position_limit_usd": round(bank*MAX_TRADE_BANKROLL_PCT, 2),
        "aggregate_limit_usd": round(bank*MAX_TOTAL_EXPOSURE_PCT, 2),
        "exposure_before_usd": round(exposure, 2),
        "blockers": blockers,
    }
