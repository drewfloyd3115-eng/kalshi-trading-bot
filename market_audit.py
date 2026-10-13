"""Pure audit helpers for Kalshi public market and series metadata.

Market.updated_time is NOT an individual order-book level timestamp.
Series fee_type/fee_multiplier describe an advertised fee configuration,
NOT a certified per-order quote or fee exemption. No orders are placed.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def _parse_utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def market_freshness_audit(market, checked_at=None, max_market_age_minutes=15):
    """Only grades MARKET metadata timestamp, never bid/order-book age."""
    at = checked_at or datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("An offset-aware audit time is required")
    if not isinstance(market, dict):
        market = {}
    updated = _parse_utc(market.get("updated_time"))
    outcome = {
        "market_updated_utc": updated.isoformat() if updated else None,
        "market_updated_age_minutes": None,
        "market_metadata_status": "UNKNOWN — NO MARKET UPDATE TIMESTAMP",
        "orderbook_level_age_verified": False,
    }
    if not updated:
        return outcome
    age = (at.astimezone(timezone.utc) - updated).total_seconds() / 60
    outcome["market_updated_age_minutes"] = round(age, 2)
    if age < -2:
        outcome["market_metadata_status"] = "INCONSISTENT — FUTURE MARKET UPDATE"
    elif age > max_market_age_minutes:
        outcome["market_metadata_status"] = "STALE MARKET METADATA"
    else:
        outcome["market_metadata_status"] = "RECENT MARKET METADATA — BID AGE UNKNOWN"
    return outcome


def series_fee_audit(series, *, series_ticker=None):
    """Read fee fields without assuming an executable or certified fee formula."""
    if not isinstance(series, dict):
        series = {}
    actual = str(series.get("ticker") or "").strip()
    expected = str(series_ticker or "").strip()
    if expected and actual != expected:
        return {
            "series_fee_metadata_status": "SERIES TICKER MISMATCH",
            "series_fee_type": None,
            "series_fee_multiplier": None,
            "fee_schedule_verified": False,
        }
    fee_type = str(series.get("fee_type") or "").strip().lower()
    multiplier = series.get("fee_multiplier")
    try:
        factor = Decimal(str(multiplier))
        valid = factor.is_finite() and 0 <= factor <= Decimal("1000")
    except (InvalidOperation, TypeError, ValueError):
        valid = False
        factor = None
    if not valid or fee_type not in ("quadratic", "quadratic_with_maker_fees", "flat"):
        status = "FEE TYPE OR MULTIPLIER MISSING / UNSUPPORTED"
    elif fee_type == "flat":
        status = "FLAT FEE — FORMULA NOT SUPPORTED; EXECUTION FEE UNVERIFIED"
    elif fee_type == "quadratic_with_maker_fees":
        status = "QUADRATIC + MAKER FEES — ORDER-SPECIFIC FEE UNVERIFIED"
    else:
        status = "QUADRATIC SERIES FEE — EXECUTION FEE UNVERIFIED"
    return {
        "series_fee_metadata_status": status,
        "series_fee_type": fee_type or None,
        "series_fee_multiplier": float(factor) if valid else None,
        "fee_schedule_verified": False,
    }
