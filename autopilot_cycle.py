"""Batch paper-decision orchestration for all venues. Zero network/order effects.

One cycle can propose several independently validated opportunities; it
reserves hypothetical risk for each PAPER_READY proposal so cross-venue
positions cannot bypass portfolio or correlated-event exposure limits.
No fills, trades, or cash movements are performed.
"""
from dataclasses import replace
from autopilot_core import Candidate, Policy, State, evaluate


def evaluate_cycle(candidates, state=None, policy=None, now=None):
    """Score input signals, enforce aggregate risk, and return auditable decisions.

    Input order is caller supplied priority order. Do NOT sort on unverified
    values or call this a backtest: validated external probabilities are required.
    """
    state = state or State()
    policy = policy or Policy()
    pending = set(state.pending_identity_keys)
    events = set(state.existing_event_keys)
    exposure = float(state.open_exposure_usd)
    open_count = state.open_position_count
    trades_today = state.trades_today
    decisions = []
    for signal in candidates:
        if not isinstance(signal, Candidate):
            raise TypeError("Only normalized Candidate records may be assessed")
        current = replace(
            state, open_exposure_usd=exposure,
            pending_identity_keys=tuple(pending), existing_event_keys=tuple(events),
            open_position_count=open_count, trades_today=trades_today,
        )
        verdict = evaluate(signal, current, policy, now=now)
        decisions.append(verdict)
        if verdict["status"] == "PAPER_READY":
            pending.add(signal.identity)
            events.add(signal.event_key)
            exposure += verdict["all_in_usd"]
            open_count += 1
            trades_today += 1
    return {
        "mode": "PAPER_ONLY",
        "decisions": decisions,
        "paper_proposals": sum(x["status"] == "PAPER_READY" for x in decisions),
        "blocked": sum(x["status"] != "PAPER_READY" for x in decisions),
        "hypothetical_reserved_exposure_usd": round(exposure, 4),
        "cash_moved_usd": 0,
        "orders_placed": 0,
        "paper_fills_recorded": 0,
    }
