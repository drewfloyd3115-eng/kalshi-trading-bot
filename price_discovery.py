"""Cached, indicative price discovery. No API calls and no trade approval."""
import pandas as pd
from config import MIN_EDGE_PP
from edge_engine import taker_fee

def price_discovery(matches, depth=None):
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
    if not result.empty:
        result["outcome_key"] = result["event"].astype(str).str.lower().str.strip() + " | " + result["outcome_team"].astype(str).str.lower().str.strip()
        result["route_count"] = result.groupby("outcome_key")["ticker"].transform("size")

        result["quote_quality"] = result.apply(lambda r: "REVIEW — disagreement" if pd.notna(pd.to_numeric(r["book_spread_pp"], errors="coerce")) and float(r["book_spread_pp"]) > 3 else ("REVIEW — quote age" if pd.notna(pd.to_numeric(r["oldest_quote_minutes"], errors="coerce")) and float(r["oldest_quote_minutes"]) > 10 else ("UNVERIFIED — check source" if pd.isna(pd.to_numeric(r["books"], errors="coerce")) or float(r["books"]) < 2 else "CONSENSUS — still unverified")), axis=1)
        result["depth_status"] = "NOT INSPECTED — no executable price verified"
        result["depth_best_ask_cents"] = None
        result["depth_edge_pp"] = None
        if depth is not None and not depth.empty:
            for _, d in depth.iterrows():
                mask = (result["ticker"].astype(str) == str(d.get("ticker"))) & (result["side"].astype(str) == str(d.get("side")))
                result.loc[mask, "depth_status"] = str(d.get("reason", "Depth not verified"))
                result.loc[mask, "depth_best_ask_cents"] = d.get("depth_ask_cents")
                result.loc[mask, "depth_edge_pp"] = d.get("depth_edge_pp")
    if result.empty:
        return result
    result = result.sort_values(["gap_to_threshold_pp", "net_edge_pp_1share", "book_spread_pp"], ascending=[True, False, False], na_position="last").reset_index(drop=True)
    result["best_route_for_outcome"] = ~result.duplicated("outcome_key")
    return result
