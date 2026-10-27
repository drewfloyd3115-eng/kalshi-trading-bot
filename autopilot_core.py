"""Multi-venue autonomous *decision* core; PAPER_ONLY, no live order endpoint.

Only externally validated and independently modeled signals can become paper
candidates. Public snapshot timestamps never prove individual order freshness.
All prices are per $1-settling binary share. Unsupported derivatives fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import math
from typing import Optional

from config import DEFAULT_BANKROLL, MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT

VENUES = frozenset({"KALSHI", "POLYMARKET_US", "NOVIG"})
PRICE_AGE_SECONDS = 15
MODEL_AGE_SECONDS = 300


def money(value, field_name="money"):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field_name} must be finite") from None
    if not d.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return d


def when(value):
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return ts.astimezone(timezone.utc) if ts.tzinfo is not None else None


@dataclass(frozen=True)
class Candidate:
    venue: str
    market_id: str
    event_key: str
    side: str
    category: str
    ask_cents: object
    depth_whole_shares: int
    fee_per_share_usd: object
    fair_probability: Optional[object] = None
    quote_at_utc: Optional[str] = None
    estimate_at_utc: Optional[str] = None
    market_open: bool = False
    binary_settlement_verified: bool = False
    fee_schedule_verified: bool = False
    quote_age_verified: bool = False
    model_independent: bool = False
    model_calibrated: bool = False
    payout_usd: object = 1

    @property
    def identity(self):
        return f"{self.venue}:{self.market_id}:{self.side}"


@dataclass(frozen=True)
class State:
    bankroll_usd: object = DEFAULT_BANKROLL
    current_equity_usd: object = DEFAULT_BANKROLL
    open_exposure_usd: object = 0
    realized_daily_pnl_usd: object = 0
    existing_event_keys: tuple = field(default_factory=tuple)
    pending_identity_keys: tuple = field(default_factory=tuple)
    open_position_count: int = 0
    trades_today: int = 0
    kill_switch: bool = False


@dataclass(frozen=True)
class Policy:
    initial_bankroll_usd: object = DEFAULT_BANKROLL
    trade_fraction: object = MAX_TRADE_BANKROLL_PCT
    portfolio_fraction: object = MAX_TOTAL_EXPOSURE_PCT
    min_edge_pp: object = MIN_EDGE_PP
    daily_stop_usd: object = 2
    max_drawdown_usd: object = 5
    max_positions: int = 3
    max_daily_trades: int = 20
    max_price_age_seconds: int = PRICE_AGE_SECONDS
    max_model_age_seconds: int = MODEL_AGE_SECONDS


def evaluate(candidate: Candidate, state: State = State(),
             policy: Policy = Policy(), now=None):
    """Return auditable constraints and a PAPER_READY or BLOCK decision.

    PAPER_READY is strictly a hypothetical decision. It does not claim an
    executable fill, verified market-model quality, or authorize a live order.
    """
    clock = when(now or datetime.now(timezone.utc))
    if clock is None:
        raise ValueError("Audit clock must be timezone-aware")
    reasons = []
    if candidate.venue not in VENUES:
        reasons.append("Unsupported venue")
    if not candidate.market_id or not candidate.event_key or candidate.side not in ("YES", "NO"):
        reasons.append("Incomplete market identity or contract side")
    if not candidate.market_open:
        reasons.append("Market is not confirmed open")
    if not candidate.binary_settlement_verified or money(candidate.payout_usd) != 1:
        reasons.append("Binary $1 settlement and outcome rules not verified")
    if not candidate.fee_schedule_verified:
        reasons.append("Applicable trading fee not verified")
    if not candidate.quote_age_verified:
        reasons.append("Order-book level freshness not independently verified")
    if not candidate.model_independent or not candidate.model_calibrated:
        reasons.append("Independent calibrated probability model missing")
    if candidate.fair_probability is None:
        reasons.append("No validated fair probability")
    price, fee = money(candidate.ask_cents,"ask price"), money(candidate.fee_per_share_usd,"fee")
    if not 0 < price < 100 or fee < 0:
        reasons.append("Invalid share price or fee")
    fair = None if candidate.fair_probability is None else money(candidate.fair_probability,"fair probability")
    if fair is not None and not 0 <= fair <= 1:
        reasons.append("Fair probability outside [0,1]")
    if isinstance(candidate.depth_whole_shares, bool) or not isinstance(candidate.depth_whole_shares, int) or candidate.depth_whole_shares < 1:
        reasons.append("Insufficient verified whole-share ask depth")
    quote = when(candidate.quote_at_utc)
    estimate = when(candidate.estimate_at_utc)
    if quote is None or (clock - quote).total_seconds() not in range(0, policy.max_price_age_seconds + 1):
        reasons.append("Missing, stale or future order-book quote")
    if estimate is None or not 0 <= (clock - estimate).total_seconds() <= policy.max_model_age_seconds:
        reasons.append("Missing, stale or future model estimate")
    if state.kill_switch:
        reasons.append("Manual kill switch engaged")
    if candidate.event_key in state.existing_event_keys:
        reasons.append("Correlated event is already exposed on another venue")
    if candidate.identity in state.pending_identity_keys:
        reasons.append("Identical order is already pending")
    if state.open_position_count >= policy.max_positions:
        reasons.append("Maximum concurrent positions reached")
    if state.trades_today >= policy.max_daily_trades:
        reasons.append("Maximum daily trade count reached")
    equity = money(state.current_equity_usd, "equity")
    bank = money(state.bankroll_usd, "bankroll")
    exposure = money(state.open_exposure_usd, "exposure")
    daily = money(state.realized_daily_pnl_usd, "daily pnl")
    initial = money(policy.initial_bankroll_usd)
    if equity <= 0 or bank <= 0 or exposure < 0:
        reasons.append("Invalid bankroll/equity/exposure")
    if daily <= -money(policy.daily_stop_usd):
        reasons.append("Daily loss stop triggered")
    if equity <= initial - money(policy.max_drawdown_usd):
        reasons.append("Maximum equity drawdown triggered")

    one_cost = price / Decimal(100) + fee
    if one_cost <= 0:
        reasons.append("Invalid all-in share cost")
        shares = 0
    else:
        trade_limit = min(bank, equity) * money(policy.trade_fraction)
        total_remaining = min(bank, equity) * money(policy.portfolio_fraction) - exposure
        budget = max(Decimal(0), min(trade_limit, total_remaining))
        shares = max(0, min(candidate.depth_whole_shares if type(candidate.depth_whole_shares) is int else 0,
                int((budget / one_cost).to_integral_value(rounding=ROUND_DOWN))))
        if shares == 0:
            reasons.append("One whole contract would exceed position/portfolio limits or depth")
    edge_pp = None if fair is None else (fair - one_cost) * Decimal(100)
    if edge_pp is not None and edge_pp < money(policy.min_edge_pp):
        reasons.append("Insufficient net probability edge")
    cost = one_cost * shares
    expected = None if fair is None else shares * (fair - one_cost)
    return {
        "status": "PAPER_READY" if not reasons else "BLOCK",
        "mode": "PAPER_ONLY",
        "venue": candidate.venue,
        "identity": candidate.identity,
        "event_key": candidate.event_key,
        "shares": shares,
        "all_in_usd": float(cost),
        "cost_per_share_usd": float(one_cost),
        "net_edge_pp": None if edge_pp is None else float(edge_pp),
        "expected_net_usd": None if expected is None else float(expected),
        "max_loss_usd": float(cost),
        "reasons": reasons,
        "audit_utc": clock.isoformat(timespec="seconds"),
        "real_order_allowed": False,
        "order_created": False,
        "paper_fill_created": False,
    }


def public_market_to_candidate(row, side="YES"):
    """Normalize observation across venue namespaces WITHOUT inventing verification.

    This intentionally fails closed even if the market quote looks extremely good.
    Independent feeds/models must later populate confirmed timestamps, fees and rules.
    """
    return Candidate(
        venue="KALSHI", market_id=str(row.get("ticker") or ""),
        event_key=str(row.get("event") or ""),
        side=side, category=str(row.get("league") or "UNVERIFIED"),
        ask_cents=row.get("yes_ask_cents" if side == "YES" else "no_ask_cents") or 0,
        depth_whole_shares=0, fee_per_share_usd=0,
        market_open=True,
    )
