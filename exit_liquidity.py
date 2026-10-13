"""Read-only Kalshi exit-side depth research for manually recorded PAPER positions.

Requires a user button press. Reads Kalshi public market metadata + resting bids
on the HELD side (YES bids to sell YES, NO bids to sell NO). Does not contact
sportsbook APIs, infer a fill, validate exchange fees/rules, place orders or
estimate live-game win probabilities. Every result remains unverified research.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite
from urllib.parse import quote

from edge_engine import taker_fee
from market_audit import market_freshness_audit, series_fee_audit
from scanner import _get, fetch_orderbook

MAX_REVIEW_SHARES = 10000
SNAPSHOT_MAX_SECONDS = 120
CENT = Decimal("0.01")


def _utc(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Snapshot time must have a time zone")
    return dt.astimezone(timezone.utc)


def _money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _positive_int(value, label, maximum=1000000):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {label}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid {label}") from None
    if not number.is_finite() or number != number.to_integral_value() \
            or number < 1 or number > maximum:
        raise ValueError(f"Invalid {label}")
    return int(number)


def _contract(position):
    position_id = str(position.get("position_id", ""))
    ticker = str(position.get("ticker", "")).strip()
    side = str(position.get("side", "")).strip()
    remaining = _positive_int(position.get("remaining_shares"), "remaining shares")
    if not position_id or not ticker or side not in ("YES", "NO"):
        raise ValueError("Need a valid recorded position ID, exact ticker and held side")
    basis = Decimal(str(position.get("remaining_cost_usd", "")))
    if not basis.is_finite() or basis < 0:
        raise ValueError("Remaining position cost basis unavailable")
    return position_id, ticker, side, remaining, basis


def _bid_levels(book, side):
    """Canonicalize exact-side public resting bids; reject malformed depth."""
    if not isinstance(book, dict):
        raise ValueError("Missing order book")
    key = "yes_bids" if side == "YES" else "no_bids"
    raw = book.get(key)
    if not isinstance(raw, list):
        raise ValueError("Held-side bid levels unavailable")
    levels = {}
    for pair in raw:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            raise ValueError("Malformed bid level")
        try:
            price = Decimal(str(pair[0]))
            count = Decimal(str(pair[1]))
        except (InvalidOperation, ValueError):
            raise ValueError("Malformed bid price or quantity") from None
        if not price.is_finite() or not count.is_finite() \
                or price <= 0 or price >= 100 or count <= 0:
            raise ValueError("Invalid held-side bid price or quantity")
        # Kalshi fixed-point order books may contain fractional contract counts.
        # Our paper ledger uses WHOLE shares only: floor each resting level
        # separately. Never round up or pool sub-shares into a fake whole order.
        # This is conservative and does not certify live execution.
        if price.as_tuple().exponent < -4:
            raise ValueError("Unsupported bid precision")
        whole_shares = int(count)
        if whole_shares == 0:
            continue
        levels[price] = levels.get(price, 0) + whole_shares
    return [(price, count) for price, count in sorted(levels.items(), reverse=True)]


def estimate_exit(position, market, orderbook, requested_shares=None, observed_at=None):
    """Calculate *indicative* available depth and net paper sale proceeds.

    Market status/ticker must match exactly. Insufficient depth NEVER assumes
    that requested shares are sellable. No validated fee schedule or fill claim.
    """
    pid, ticker, side, held, basis = _contract(position)
    requested = _positive_int(
        requested_shares if requested_shares is not None else held,
        "requested shares", maximum=MAX_REVIEW_SHARES)
    if requested > held:
        raise ValueError("Cannot inspect selling more shares than currently held")
    at = _utc(observed_at).isoformat(timespec="seconds")
    result = {
        "position_id": pid, "ticker": ticker, "side": side,
        "held_shares_at_scan": held, "requested_shares": requested,
        "checked_utc": at, "status": "UNVERIFIED — NO EXIT SIGNAL",
        "reason": "Read-only observation; market fills, fees and settlement not verified",
        "best_bid_cents": None, "covered_shares": 0,
        "total_bid_shares": 0, "depth_complete": False,
        "levels_used": [], "gross_proceeds_usd": None,
        "estimated_exit_fee_usd": None, "net_proceeds_usd": None,
        "allocated_entry_cost_usd": None, "hypothetical_net_pnl_usd": None,
        "estimated_roi_pct": None, "remaining_after_review": held,
        "market_status": "UNKNOWN", "fee_schedule_verified": False,
        "source_quote_age_verified": False,
        "execution_verified": False, "hold_value_verified": False,
        # A calculated snapshot is NOT evidence of an actual public request.
        "lookup_status": "SOURCE UNVERIFIED",
    }
    if not isinstance(market, dict) or market.get("ticker") != ticker:
        result["reason"] = "Kalshi market metadata does not match exact held ticker"
        return result
    result["market_status"] = str(market.get("status") or "UNKNOWN")
    if result["market_status"] not in ("open", "active"):
        result["reason"] = "Market not open for observation (closed, settled or unknown)"
        return result
    try:
        levels = _bid_levels(orderbook, side)
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    result["total_bid_shares"] = sum(qty for _, qty in levels)
    if not levels:
        result["reason"] = "No resting bids on the HELD side; no observed sale liquidity"
        return result
    result["best_bid_cents"] = float(levels[0][0])
    remaining = requested
    filled = []
    for cents, available in levels:
        count = min(remaining, available)
        if count:
            filled.append((cents, count))
            remaining -= count
        if remaining == 0:
            break
    covered = requested - remaining
    result["covered_shares"] = covered
    result["depth_complete"] = remaining == 0
    result["levels_used"] = [
        {"bid_cents": float(price), "shares": count}
        for price, count in filled
    ]
    if covered == 0:
        result["reason"] = "No sale-side depth available"
        return result
    gross = sum((price * count / Decimal(100) for price, count in filled), Decimal(0))
    # Generic *estimated* taker fees, not certified Kalshi fee metadata.
    fees = sum((Decimal(str(taker_fee(float(price), count))) for price, count in filled),
               Decimal(0))
    entry_cost = basis * Decimal(covered) / Decimal(held)
    proceeds = gross - fees
    pnl = proceeds - entry_cost
    result.update({
        "gross_proceeds_usd": _money(gross),
        "estimated_exit_fee_usd": _money(fees),
        "net_proceeds_usd": _money(proceeds),
        "allocated_entry_cost_usd": _money(entry_cost),
        "hypothetical_net_pnl_usd": _money(pnl),
        "estimated_roi_pct": float((pnl / entry_cost * 100).quantize(CENT))
                             if entry_cost > 0 else None,
        "remaining_after_review": held - covered,
    })
    # All shown prices are observations. Market fees may vary, source quote age
    # cannot be established from the book, and actual execution isn't proven.
    if remaining > 0:
        result["reason"] = (f"ONLY {covered}/{requested} shares of held-side bid depth "
                            "observed; do not value the unsellable remainder at best bid")
    else:
        result["reason"] = (
            "Held-side bid depth observed for requested shares; a snapshot, "
            "NOT a guaranteed fill. Quote age, fees, rules and actual execution unverified."
        )
    return result


def review_public_position(position, requested_shares=None, *,
                           market_fetch=None, book_fetch=None, observed_at=None,
                           series_fetch=None):
    """Two public market/book GETs, optional third series fee metadata GET."""
    lookup_started = False
    try:
        pid, ticker, side, held, basis = _contract(position)
        requested = _positive_int(
            requested_shares if requested_shares is not None else held,
            "requested shares", maximum=MAX_REVIEW_SHARES)
        if requested > held:
            raise ValueError("Requested quantity exceeds manually held shares")
        # Reject synthetic and unsupported tickers without a public request.
        from scanner import SPORT_PREFIXES
        league = str(position.get("league", "")).strip()
        prefixes = SPORT_PREFIXES.get(league, ())
        if not prefixes or not any(ticker.startswith(prefix + "-") for prefix in prefixes):
            raise ValueError("Ticker is not in the supported CFB/NFL game-winner series")
        if market_fetch is None:
            market_fetch = lambda t: _get("/markets/" + quote(t, safe="")).get("market", {})
        if book_fetch is None:
            book_fetch = fetch_orderbook
        lookup_started = True
        market = market_fetch(ticker)
        market_age = market_freshness_audit(market, checked_at=_utc(observed_at))
        if not isinstance(market, dict) or market.get("ticker") != ticker \
                or market.get("status") not in ("open", "active"):
            result = estimate_exit(position, market, None, requested, observed_at)
            result.update(market_age)
            result["lookup_status"] = "MARKET METADATA ONLY — NO ORDERBOOK"
            return result
        book = book_fetch(ticker)
        result = estimate_exit(position, market, book, requested, observed_at)
        result.update(market_age)
        series_ticker = ticker.split("-", 1)[0]
        fee_meta = series_fee_audit({}, series_ticker=series_ticker)
        if series_fetch is not None:
            try:
                fee_meta = series_fee_audit(series_fetch(series_ticker),
                                            series_ticker=series_ticker)
            except Exception:
                fee_meta["series_fee_metadata_status"] = "PUBLIC SERIES FEE LOOKUP FAILED"
        result.update(fee_meta)
        result["lookup_status"] = "PUBLIC ORDERBOOK RETURNED"
        return result
    except Exception as exc:
        try:
            pid, ticker, side, held, _ = _contract(position)
        except Exception:
            pid, ticker, side, held = "", "", "", 0
        return {
            "position_id": pid, "ticker": ticker, "side": side,
            "held_shares_at_scan": held, "requested_shares": requested_shares,
            "checked_utc": _utc(observed_at).isoformat(timespec="seconds"),
            "status": "UNVERIFIED — NO EXIT SIGNAL",
            "reason": (("Public exit-depth lookup failed: " if lookup_started
                        else "Rejected before public lookup: ") + str(exc)[:140]),
            "lookup_status": ("PUBLIC LOOKUP FAILED" if lookup_started
                              else "REJECTED BEFORE LOOKUP"),
            "best_bid_cents": None, "covered_shares": 0, "depth_complete": False,
            "execution_verified": False, "source_quote_age_verified": False,
            "fee_schedule_verified": False, "hold_value_verified": False,
        }


def snapshot_integrity(snapshot, position, *, now=None, requested_shares=None):
    """Check cached snapshot is recent and still matches remaining holdings."""
    if not isinstance(snapshot, dict):
        return False, "No manual exit review completed"
    try:
        pid, ticker, side, held, _ = _contract(position)
        if (snapshot.get("position_id") != pid or snapshot.get("ticker") != ticker
                or snapshot.get("side") != side
                or snapshot.get("held_shares_at_scan") != held):
            return False, "Position or remaining shares changed; refresh exit review"
        if requested_shares is not None and snapshot.get("requested_shares") != requested_shares:
            return False, "Requested sale quantity changed; refresh exit review"
        lookup = snapshot.get("lookup_status", "SOURCE UNVERIFIED")
        if lookup == "REJECTED BEFORE LOOKUP":
            return False, "No Kalshi public lookup performed — request rejected locally"
        if lookup == "PUBLIC LOOKUP FAILED":
            return False, "Kalshi public lookup failed — no current order-book evidence"
        if lookup == "MARKET METADATA ONLY — NO ORDERBOOK":
            return False, "Market metadata checked, but no sell-side order book retrieved"
        if snapshot.get("market_metadata_status") in (
                "STALE MARKET METADATA",
                "INCONSISTENT — FUTURE MARKET UPDATE"):
            return False, "Market metadata is stale or inconsistent — no current quote claim"
        checked = _utc(snapshot.get("checked_utc"))
        at = _utc(now)
        elapsed = (at - checked).total_seconds()
        if elapsed < -60:
            return False, "Snapshot timestamp inconsistent"
        if elapsed > SNAPSHOT_MAX_SECONDS:
            return False, "Exit quote snapshot is stale; refresh manually"
        # A fresh GET timestamp does not prove how old the resting bids were.
        return True, "Recent public lookup; source quote age and fills NOT verified"
    except (ValueError, TypeError, OverflowError):
        return False, "Invalid exit quote snapshot; no verified signal"
