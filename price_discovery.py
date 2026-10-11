"""Cached, indicative price discovery. No API calls and no trade approval."""
import pandas as pd
from config import MIN_EDGE_PP
from edge_engine import taker_fee

def price_discovery(matches):
    columns = ["event", "outcome_team", "ticker", "side", "fair_pct",
               "ask_cents", "net_edge_pp_1share", "gap_to_threshold_pp",
               "max_entry_cents_1share", "price_drop_needed_cents",
               "book_spread_pp", "books", "oldest_quote_minutes", "research_status"]
    if matches is None or matches.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in matches.iterrows():
        try:
            fair, ask = float(row["fair_pct"]), float(row["ask_cents"])
            if not (0 < fair < 100 and 0 < ask < 100):
                continue
            edge = fair - ask - 100 * taker_fee(ask, 1)
            max_entry = next((p for p in range(99, 0, -1)
                              if fair - p - 100 * taker_fee(p, 1) >= MIN_EDGE_PP), None)
            gap = max(0.0, MIN_EDGE_PP - edge)
            rows.append({
                "event": row.get("event", ""), "outcome_team": row.get("outcome_team", ""),
                "ticker": row.get("ticker", ""), "side": row.get("side", ""),
                "fair_pct": round(fair, 2), "ask_cents": ask,
                "net_edge_pp_1share": round(edge, 2),
                "gap_to_threshold_pp": round(gap, 2),
                "max_entry_cents_1share": max_entry,
                "price_drop_needed_cents": max(0, ask - max_entry) if max_entry is not None else None,
                "book_spread_pp": row.get("book_spread_pp"),
                "books": row.get("books"),
                "oldest_quote_minutes": row.get("oldest_quote_minutes"),
                "research_status": "PRELIMINARY ONLY — NOT VERIFIED"
            })
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            continue
    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return result
    return result.sort_values(["gap_to_threshold_pp", "book_spread_pp"],
                              ascending=[True, False], na_position="last").reset_index(drop=True)
