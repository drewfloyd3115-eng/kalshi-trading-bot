"""Paper-only, event-sourced position ledger with explicit simulated fills.

This module makes NO API calls, never places orders, never infers a fill from a
scan or queue entry, and never claims that a recorded price is executable.
CSV import is strictly validated and replaces (not silently merges with) a
session ledger. All money arithmetic uses Decimal to avoid floating point
share/fee drift. Position IDs and transaction IDs are stable across exports.
"""
import csv
import io
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_UP

import pandas as pd

from config import MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT

LEDGER_VERSION = "1"
COLUMNS = [
    "schema_version", "transaction_id", "position_id", "recorded_at_utc",
    "action", "league", "event", "outcome_team", "ticker", "side",
    "shares", "price_cents", "fee_usd", "notes",
]
MAX_TRANSACTIONS = 5000
MAX_UPLOAD_BYTES = 2_000_000
CENT = Decimal("0.01")
HUNDRED = Decimal("100")
_ALLOWED_LEAGUES = {"CFB", "NFL"}
_ALLOWED_SIDES = {"YES", "NO"}
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TICKER_RE = re.compile(r"^[A-Z0-9_-]{3,128}$")


def empty_ledger():
    return pd.DataFrame(columns=COLUMNS)


def _decimal(value, label, *, minimum=Decimal("0"), maximum=Decimal("1000000"), places=2):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"{label} must be numeric") from None
    if not result.is_finite() or not minimum <= result <= maximum:
        raise ValueError(f"{label} outside permitted range")
    if result != result.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"{label} permits at most {places} decimal places")
    return result


def _shares(value):
    result = _decimal(value, "Shares", minimum=Decimal(1), maximum=Decimal(1000000), places=0)
    return int(result)


def _text(value, label, limit=200, *, allow_empty=False):
    result = str(value if value is not None else "").strip()
    if (not result and not allow_empty) or len(result) > limit:
        raise ValueError(f"{label} is missing or too long")
    if any(ord(char) < 32 and char not in "\t" for char in result):
        raise ValueError(f"{label} contains control characters")
    # Avoid CSV spreadsheet formula injection from manually entered fields.
    if result.lstrip().startswith(("=", "+", "-", "@")):
        raise ValueError(f"{label} cannot begin with a spreadsheet formula character")
    return result


def _timestamp(value):
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise ValueError("Invalid UTC timestamp") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("UTC timestamp must specify a time zone")
    return dt.astimezone(timezone.utc)


def _validate_row(row):
    if str(row.get("schema_version")) != LEDGER_VERSION:
        raise ValueError("Unsupported ledger schema version")
    tid = str(row.get("transaction_id", ""))
    pid = str(row.get("position_id", ""))
    if not _ID_RE.fullmatch(tid) or not _ID_RE.fullmatch(pid):
        raise ValueError("Invalid transaction or position ID")
    action = str(row.get("action", "")).strip()
    if action not in ("ENTRY", "EXIT"):
        raise ValueError("Invalid transaction action")
    league = str(row.get("league", "")).strip()
    if league not in _ALLOWED_LEAGUES:
        raise ValueError("Only CFB and NFL paper positions are supported")
    ticker = str(row.get("ticker", "")).strip()
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError("Ticker must be an exact market ticker (3–128 alphanumerics, _ or -)")
    side = str(row.get("side", "")).strip()
    if side not in _ALLOWED_SIDES:
        raise ValueError("Contract side must be YES or NO")
    price = _decimal(row.get("price_cents"), "Price in cents",
                     minimum=Decimal(1), maximum=Decimal(99), places=0)
    fee = _decimal(row.get("fee_usd"), "Fee in USD", minimum=Decimal(0),
                   maximum=Decimal("100000"), places=2)
    timestamp = _timestamp(row.get("recorded_at_utc"))
    return {
        "schema_version": LEDGER_VERSION,
        "transaction_id": tid,
        "position_id": pid,
        "recorded_at_utc": timestamp.isoformat(timespec="microseconds"),
        "action": action,
        "league": league,
        "event": _text(row.get("event"), "Event"),
        "outcome_team": _text(row.get("outcome_team"), "Outcome team", 120),
        "ticker": ticker,
        "side": side,
        "shares": _shares(row.get("shares")),
        "price_cents": int(price),
        "fee_usd": f"{fee:.2f}",
        "notes": _text(row.get("notes"), "Notes", 500, allow_empty=True),
    }


def _replay(ledger):
    """Canonicalize and replay. Reject forged order, over-selling, or mismatched sides."""
    if ledger is None:
        ledger = empty_ledger()
    if not isinstance(ledger, pd.DataFrame):
        raise ValueError("Ledger must be a table")
    if set(ledger.columns) != set(COLUMNS):
        raise ValueError("Invalid paper position ledger columns")
    if len(ledger) > MAX_TRANSACTIONS:
        raise ValueError("Position journal exceeds maximum entries")

    canonical = []
    positions = {}
    seen_transactions = set()
    for raw in ledger.to_dict(orient="records"):
        tx = _validate_row(raw)
        tid, pid = tx["transaction_id"], tx["position_id"]
        if tid in seen_transactions:
            raise ValueError("Duplicate transaction ID (import rejected)")
        seen_transactions.add(tid)
        when = _timestamp(tx["recorded_at_utc"])
        entry_fee = Decimal(tx["fee_usd"])
        if tx["action"] == "ENTRY":
            if pid in positions:
                raise ValueError("Position ID already has an entry")
            entry_total = Decimal(tx["shares"]) * Decimal(tx["price_cents"]) / HUNDRED + entry_fee
            positions[pid] = {
                **{field: tx[field] for field in ("position_id", "league", "event",
                                                   "outcome_team", "ticker", "side")},
                "entry_time_utc": tx["recorded_at_utc"],
                "last_time": when, "entry_shares": tx["shares"],
                "remaining_shares": tx["shares"], "entry_cents": tx["price_cents"],
                "entry_fee": entry_fee, "entry_cost": entry_total,
                "realized_net": Decimal(0), "exit_count": 0,
            }
        else:
            state = positions.get(pid)
            if state is None:
                raise ValueError("Exit without an entry")
            for field in ("league", "event", "outcome_team", "ticker", "side"):
                if tx[field] != state[field]:
                    raise ValueError("Exit contract does not exactly match the entry")
            if when < state["last_time"]:
                raise ValueError("Exit timestamp before previous transaction")
            if tx["shares"] > state["remaining_shares"]:
                raise ValueError("Exit shares exceed remaining shares")
            allocated_entry = (state["entry_cost"] * Decimal(tx["shares"])
                               / Decimal(state["entry_shares"]))
            net_exit = (Decimal(tx["shares"]) * Decimal(tx["price_cents"]) / HUNDRED
                        - entry_fee - allocated_entry)
            state["realized_net"] += net_exit
            state["remaining_shares"] -= tx["shares"]
            state["exit_count"] += 1
            state["last_time"] = when
        canonical.append(tx)
    return pd.DataFrame(canonical, columns=COLUMNS), positions


def validate_ledger(ledger):
    """Return a validated copy or raise. Never trust imported P&L fields."""
    return _replay(ledger)[0]


def open_positions(ledger):
    _, states = _replay(ledger)
    rows = []
    for p in states.values():
        remaining = p["remaining_shares"]
        if remaining <= 0:
            continue
        at_risk = p["entry_cost"] * Decimal(remaining) / Decimal(p["entry_shares"])
        rows.append({
            "position_id": p["position_id"], "league": p["league"],
            "event": p["event"], "outcome_team": p["outcome_team"],
            "ticker": p["ticker"], "side": p["side"],
            "recorded_at_utc": p["entry_time_utc"],
            "entry_shares": p["entry_shares"], "remaining_shares": remaining,
            "entry_cents": p["entry_cents"],
            "entry_fee_usd": float(p["entry_fee"]),
            "remaining_cost_usd": float(at_risk.quantize(CENT, rounding=ROUND_HALF_UP)),
            "exit_count": p["exit_count"],
        })
    return pd.DataFrame(rows, columns=[
        "position_id", "league", "event", "outcome_team", "ticker", "side",
        "recorded_at_utc", "entry_shares", "remaining_shares", "entry_cents",
        "entry_fee_usd", "remaining_cost_usd", "exit_count"
    ])


def ledger_summary(ledger):
    canonical, positions = _replay(ledger)
    open_states = [p for p in positions.values() if p["remaining_shares"] > 0]
    exposure = sum((
        p["entry_cost"] * Decimal(p["remaining_shares"]) / Decimal(p["entry_shares"])
        for p in open_states
    ), Decimal(0))
    profit = sum((p["realized_net"] for p in positions.values()), Decimal(0))
    return {
        "transactions": len(canonical),
        "positions_total": len(positions),
        "open_positions": len(open_states),
        "closed_positions": len(positions) - len(open_states),
        "partial_exits": sum(p["exit_count"] for p in positions.values()),
        "remaining_shares": sum(p["remaining_shares"] for p in open_states),
        "open_cost_usd": float(exposure.quantize(CENT, rounding=ROUND_UP)),
        "realized_net_usd": float(profit.quantize(CENT, rounding=ROUND_HALF_UP)),
        "has_exits": any(p["exit_count"] > 0 for p in positions.values()),
    }


def _frame_with(ledger, tx):
    frame = validate_ledger(ledger)
    if len(frame) >= MAX_TRANSACTIONS:
        raise ValueError("Position journal is full; export first")
    return validate_ledger(pd.concat([frame, pd.DataFrame([tx], columns=COLUMNS)],
                                     ignore_index=True))


def record_entry(ledger, *, league, event, ticker, outcome_team, side, shares,
                 price_cents, fee_usd, bankroll, other_exposure=0,
                 queued_exposure=0, recorded_at=None, notes=""):
    """Record an explicitly-confirmed hypothetical fill, applying 1%/3% caps."""
    canonical = validate_ledger(ledger)
    count = _shares(shares)
    price = _decimal(price_cents, "Entry price", minimum=Decimal(1),
                     maximum=Decimal(99), places=0)
    fee = _decimal(fee_usd, "Entry fee", maximum=Decimal("100000"), places=2)
    bank = _decimal(bankroll, "Paper bankroll", minimum=Decimal("0.01"),
                    maximum=Decimal("10000000"), places=2)
    other = _decimal(other_exposure, "Other open exposure",
                     maximum=Decimal("10000000"), places=2)
    queued = _decimal(queued_exposure, "Existing paper queue exposure",
                      maximum=Decimal("10000000"), places=2)
    # Use exact unrounded cost allocations for risk enforcement.
    # Reporting rounds cents, but rounded exposure could otherwise bypass caps.
    _, states = _replay(canonical)
    existing = sum((
        p["entry_cost"] * Decimal(p["remaining_shares"]) / Decimal(p["entry_shares"])
        for p in states.values() if p["remaining_shares"] > 0
    ), Decimal(0))
    entry_cost = Decimal(count) * price / HUNDRED + fee
    one_cap = bank * Decimal(str(MAX_TRADE_BANKROLL_PCT))
    total_cap = bank * Decimal(str(MAX_TOTAL_EXPOSURE_PCT))
    if entry_cost > one_cap:
        raise ValueError("Hypothetical entry exceeds 1% paper-bankroll limit (including fee)")
    same_market_exposure = sum((
        p["entry_cost"] * Decimal(p["remaining_shares"]) / Decimal(p["entry_shares"])
        for p in states.values()
        if p["remaining_shares"] > 0 and p["ticker"] == str(ticker).strip()
    ), Decimal(0))
    if same_market_exposure + entry_cost > one_cap:
        raise ValueError("Existing paper holdings plus new entry exceed 1% per-market limit")
    if existing + other + queued + entry_cost > total_cap:
        raise ValueError("Open positions plus queue/other exposure exceed 3% paper-bankroll limit")
    position_id, transaction_id = uuid.uuid4().hex, uuid.uuid4().hex
    entry = {
        "schema_version": LEDGER_VERSION,
        "transaction_id": transaction_id, "position_id": position_id,
        "recorded_at_utc": _timestamp(recorded_at or datetime.now(timezone.utc)).isoformat(),
        "action": "ENTRY", "league": league, "event": event, "ticker": ticker,
        "outcome_team": outcome_team, "side": side, "shares": count,
        "price_cents": int(price), "fee_usd": f"{fee:.2f}", "notes": notes,
    }
    return _frame_with(canonical, entry)


def record_exit(ledger, position_id, *, shares, price_cents, fee_usd,
                recorded_at=None, notes=""):
    """Manually record simulated sale; never use sportsbook ask as a sell bid."""
    canonical, positions = _replay(ledger)
    state = positions.get(str(position_id))
    if not state or state["remaining_shares"] <= 0:
        raise ValueError("No open paper position with that ID")
    count = _shares(shares)
    if count > state["remaining_shares"]:
        raise ValueError("Cannot sell more shares than the position holds")
    price = _decimal(price_cents, "Manual exit price", minimum=Decimal(1),
                     maximum=Decimal(99), places=0)
    fee = _decimal(fee_usd, "Exit fee", maximum=Decimal("100000"), places=2)
    when = _timestamp(recorded_at or datetime.now(timezone.utc))
    if when < state["last_time"]:
        raise ValueError("Exit timestamp before position entry/last exit")
    tx = {
        "schema_version": LEDGER_VERSION,
        "transaction_id": uuid.uuid4().hex, "position_id": position_id,
        "recorded_at_utc": when.isoformat(), "action": "EXIT",
        **{field: state[field] for field in
           ("league", "event", "outcome_team", "ticker", "side")},
        "shares": count, "price_cents": int(price),
        "fee_usd": f"{fee:.2f}", "notes": notes,
    }
    return _frame_with(canonical, tx)


def export_ledger(ledger):
    canonical = validate_ledger(ledger)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(canonical.to_dict(orient="records"))
    return output.getvalue().encode("utf-8")


def import_ledger(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload must be a CSV file below 2 MB")
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Ledger must use UTF-8 CSV") from None
    try:
        reader = csv.DictReader(io.StringIO(data))
        if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS) \
                or len(reader.fieldnames) != len(COLUMNS):
            raise ValueError("Not a Kalshi paper position ledger (wrong columns)")
        rows = list(reader)
        if len(rows) > MAX_TRANSACTIONS:
            raise ValueError("Too many position transactions")
        if any(None in row or any(value is None for value in row.values())
               for row in rows):
            raise ValueError("Malformed CSV rows")
        frame = pd.DataFrame(rows, columns=COLUMNS)
        return validate_ledger(frame)
    except csv.Error:
        raise ValueError("Malformed CSV ledger") from None
