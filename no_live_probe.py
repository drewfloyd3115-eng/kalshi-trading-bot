"""One-shot, NO-side, read-only Kalshi public integration and metadata audit.

No sportsbook calls, credentials, position journal changes, or orders.
Only a bounded set of public GETs (two discovery pages, up to 3 individual
market + orderbook requests, and one series fee metadata request).
The runner is triggered only by its dedicated GitHub workflow.
"""
import json
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from exit_liquidity import estimate_exit
from market_audit import market_freshness_audit, series_fee_audit
from scanner import _get, fetch_orderbook, fetch_sports_markets, SPORT_PREFIXES

MAX_NO_PROBES = 3


def prioritize_no_contracts(markets):
    """Identify exact CFB/NFL contracts with a displayed NO bid."""
    if markets is None or markets.empty:
        return []
    found = []
    seen = set()
    for _, market in markets.iterrows():
        league, ticker = str(market.get("league") or ""), str(market.get("ticker") or "")
        if league not in SPORT_PREFIXES or ticker in seen:
            continue
        if not any(ticker.startswith(prefix + "-") for prefix in SPORT_PREFIXES[league]):
            continue
        seen.add(ticker)
        try:
            value = float(market.get("no_bid_cents"))
        except (TypeError, ValueError):
            continue
        if not 0 < value < 100:
            continue
        found.append({"ticker": ticker, "league": league, "no_bid_cents": value,
                      "series_ticker": ticker.split("-", 1)[0]})
    found.sort(key=lambda r: r["no_bid_cents"], reverse=True)
    return found


def run_no_probe(*, discovery=fetch_sports_markets, metadata_fetch=None,
                 book_fetch=fetch_orderbook, series_fetch=None, now=None):
    at = now or datetime.now(timezone.utc)
    if metadata_fetch is None:
        metadata_fetch = lambda ticker: _get(
            "/markets/" + quote(ticker, safe="")).get("market", {})
    if series_fetch is None:
        series_fetch = lambda series: _get(
            "/series/" + quote(series, safe="")).get("series", {})
    markets = discovery(("NFL", "CFB"), 1)
    routes = prioritize_no_contracts(markets)
    report = {
        "type": "KALSHI_NO_PUBLIC_ORDERBOOK_AUDIT",
        "checked_utc": at.isoformat(timespec="seconds"),
        "candidate_no_markets": len(routes),
        "markets_checked": 0,
        "status": "NO QUALIFYING PUBLIC BID VERIFIED",
        "trading_disabled": True,
        "paper_ledger_mutations": 0,
        "sportsbook_requests": 0,
        "execution_verified": False,
        "orderbook_level_age_verified": False,
        "fee_schedule_verified": False,
    }
    errors = []
    for candidate in routes[:MAX_NO_PROBES]:
        ticker = candidate["ticker"]
        report["markets_checked"] += 1
        try:
            market = metadata_fetch(ticker)
            if not isinstance(market, dict) or market.get("ticker") != ticker:
                errors.append("Metadata ticker mismatch")
                continue
            if market.get("status") not in ("open", "active"):
                errors.append("Market status not open/active")
                continue
            book = book_fetch(ticker)
            mock_position = {
                "position_id": "0" * 32, "ticker": ticker,
                "league": candidate["league"], "side": "NO",
                "remaining_shares": 1, "remaining_cost_usd": 0.50,
            }
            estimate = estimate_exit(mock_position, market, book, requested_shares=1,
                                     observed_at=at)
            metadata_audit = market_freshness_audit(market, checked_at=at)
            try:
                series = series_fetch(candidate["series_ticker"])
                fee_audit = series_fee_audit(
                    series, series_ticker=candidate["series_ticker"])
            except Exception as exc:
                fee_audit = series_fee_audit({}, series_ticker=candidate["series_ticker"])
                errors.append("Fee metadata retrieval: " + type(exc).__name__)
            report.update({
                "ticker": ticker, "league": candidate["league"],
                "side": "NO", "market_status": str(market.get("status")),
                "indicative_no_bid_cents": candidate["no_bid_cents"],
                "held_side_book_best_bid_cents": estimate["best_bid_cents"],
                "covered_shares": estimate["covered_shares"],
                "depth_complete": estimate["depth_complete"],
                "orderbook_result_reason": estimate["reason"],
                **metadata_audit, **fee_audit,
            })
            # Unparsable books must be reported as FAIL, not as empty depth.
            malformed = estimate["reason"].startswith(("Invalid", "Malformed",
                "Unsupported", "Missing order book", "Held-side bid levels unavailable"))
            report["status"] = (
                "NO ORDERBOOK INVALID — NO SIGNAL" if malformed
                else "NO BOOK PARSED — NO SIGNAL" if estimate["covered_shares"] == 1
                else "NO BOOK EMPTY — NO SIGNAL"
            )
            report["errors"] = errors[:3]
            return report
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc)[:100])
    report["errors"] = errors[:3]
    return report


def main():
    try:
        report = run_no_probe()
    except Exception as exc:
        print(json.dumps({
            "type": "KALSHI_NO_PUBLIC_ORDERBOOK_AUDIT",
            "status": "PUBLIC DATA UNAVAILABLE",
            "error": type(exc).__name__,
            "paper_ledger_mutations": 0,
            "sportsbook_requests": 0,
            "trading_disabled": True,
        }, indent=2))
        return 2
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"].startswith("NO BOOK PARSED") else 2


if __name__ == "__main__":
    sys.exit(main())
