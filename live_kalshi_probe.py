"""One-time, read-only PUBLIC Kalshi live-data integration diagnostic.

No paper ledger edits, no sportsbook API, no authentication, and no orders.
The live workflow is deliberately triggered only on changes to this probe or
its dedicated workflow, not by ordinary app deployment.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from exit_liquidity import estimate_exit, snapshot_integrity
from scanner import SPORT_PREFIXES, _get, fetch_orderbook, fetch_sports_markets

# A bounded public request budget: at most 2 event-page calls, then
# at most 3 market and 3 book GETs, stopping at a usable response.
MAX_CANDIDATES = 3


def prioritize_markets(markets):
    """Choose exact active game-winner tickers, highest indicative bid first."""
    if markets is None or markets.empty:
        return []
    candidates = []
    seen = set()
    for _, row in markets.iterrows():
        league = str(row.get("league") or "")
        ticker = str(row.get("ticker") or "")
        if league not in SPORT_PREFIXES:
            continue
        if not any(ticker.startswith(prefix + "-") for prefix in SPORT_PREFIXES[league]):
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        try:
            yes = float(row.get("yes_bid_cents") or 0)
            no = float(row.get("no_bid_cents") or 0)
        except (TypeError, ValueError):
            continue
        if not 0 <= yes <= 100 or not 0 <= no <= 100:
            continue
        side, bid = ("YES", yes) if yes >= no else ("NO", no)
        if bid <= 0:
            continue
        candidates.append({
            "league": league,
            "ticker": ticker,
            "event": str(row.get("event") or ""),
            "side": side,
            "indicative_bid_cents": bid,
            "volume": row.get("volume"),
        })
    # Priority simply selects a well-quoted venue response for shape testing.
    # This is NOT trading advice or a recommendation.
    candidates.sort(key=lambda x: x["indicative_bid_cents"], reverse=True)
    return candidates


def run_probe(*, market_source=fetch_sports_markets,
              metadata_source=None, orderbook_source=fetch_orderbook):
    if metadata_source is None:
        metadata_source = lambda ticker: _get(
            "/markets/" + quote(ticker, safe="")
        ).get("market", {})
    checked = datetime.now(timezone.utc)
    markets = market_source(("NFL", "CFB"), 1)
    candidates = prioritize_markets(markets)
    report = {
        "type": "KALSHI_PUBLIC_READ_ONLY_INTEGRATION",
        "checked_utc": checked.isoformat(timespec="seconds"),
        "matches_discovered": len(candidates),
        "markets_probed": 0,
        "status": "NOT VERIFIED",
        "trading_disabled": True,
        "sportsbook_requests": 0,
        "ledger_changes": 0,
    }
    errors = []
    for candidate in candidates[:MAX_CANDIDATES]:
        ticker = candidate["ticker"]
        report["markets_probed"] += 1
        try:
            metadata = metadata_source(ticker)
            if not isinstance(metadata, dict) or metadata.get("ticker") != ticker:
                errors.append("Exact market metadata mismatch")
                continue
            if metadata.get("status") not in ("open", "active"):
                errors.append("Market no longer open")
                continue
            book = orderbook_source(ticker)
            position = {
                "league": candidate["league"],
                "position_id": "0" * 32,  # never persisted
                "ticker": ticker,
                "side": candidate["side"],
                "remaining_shares": 1,
                "remaining_cost_usd": 0.50,  # synthetic for pure arithmetic only
            }
            result = estimate_exit(position, metadata, book,
                                   requested_shares=1, observed_at=checked)
            # The public schema and end-to-end depth calculations reached live
            # Kalshi data. This DOES NOT verify quote freshness or execution.
            report.update({
                "status": ("READ_ONLY_BOOK_PARSED — NO EXIT SIGNAL"
                           if result["covered_shares"] == 1
                           else "READ_ONLY_BOOK_EMPTY — NO EXIT SIGNAL"),
                "ticker": ticker, "league": candidate["league"],
                "side": candidate["side"],
                "market_status": result["market_status"],
                "covered_shares": result["covered_shares"],
                "best_bid_cents": result["best_bid_cents"],
                "depth_complete": result["depth_complete"],
                "fee_schedule_verified": False,
                "source_quote_age_verified": False,
                "execution_verified": False,
                "reason": result["reason"],
            })
            return report
        except Exception as exc:
            # Do not disclose API secrets or network environment details.
            errors.append(type(exc).__name__ + ": " + str(exc)[:130])
    report["errors"] = errors[:MAX_CANDIDATES]
    report["status"] = ("NO OPEN WELL-QUOTED MARKETS FOUND" if not candidates
                        else "PUBLIC LOOKUP FAILED OR MARKETS CHANGED")
    return report


def main():
    try:
        result = run_probe()
    except Exception as exc:
        print(json.dumps({
            "type": "KALSHI_PUBLIC_READ_ONLY_INTEGRATION",
            "status": "PUBLIC API UNAVAILABLE",
            "error_type": type(exc).__name__,
            "trading_disabled": True,
            "sportsbook_requests": 0,
            "ledger_changes": 0,
        }, indent=2))
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"].startswith("READ_ONLY_BOOK_") else 2


if __name__ == "__main__":
    sys.exit(main())
