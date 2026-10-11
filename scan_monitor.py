"""Manual scan-to-scan comparisons. No scheduling, API calls or order placement."""
import pandas as pd
from datetime import datetime, timezone
from matcher import parse_time
from config import MIN_EDGE_PP

COLUMNS = ["event", "outcome_team", "ticker", "side", "previous_edge_pp",
           "current_edge_pp", "edge_change_pp", "previous_ask_cents",
           "current_ask_cents", "ask_change_cents", "threshold_crossing",
           "kickoff_status", "research_status"]

def scan_changes(previous, current, eligibility, previous_time=None, current_time=None, now=None):
    now = now or datetime.now(timezone.utc)
    prev_at, curr_at = parse_time(previous_time), parse_time(current_time)
    independent = bool(prev_at and curr_at and curr_at > prev_at and prev_at <= now and curr_at <= now + pd.Timedelta(minutes=2))
    fresh = bool(curr_at and -120 <= (now - curr_at).total_seconds() <= 300)
    if not isinstance(current, pd.DataFrame) or current.empty:
        return pd.DataFrame(columns=COLUMNS)
    before = {}
    if isinstance(previous, pd.DataFrame) and not previous.empty:
        for _, r in previous.iterrows():
            before[(str(r.get("ticker")), str(r.get("side")))] = r
    statuses = {}
    if isinstance(eligibility, pd.DataFrame) and not eligibility.empty:
        for _, r in eligibility.iterrows():
            statuses[(str(r.get("ticker")), str(r.get("side")))] = r
    rows = []
    for _, r in current.iterrows():
        key = (str(r.get("ticker")), str(r.get("side")))
        prior = before.get(key) if independent else None
        evidence = statuses.get(key)
        edge = pd.to_numeric(r.get("net_edge_pp_1share"), errors="coerce")
        ask = pd.to_numeric(r.get("ask_cents"), errors="coerce")
        old_edge = pd.to_numeric(prior.get("net_edge_pp_1share"), errors="coerce") if prior is not None else float("nan")
        old_ask = pd.to_numeric(prior.get("ask_cents"), errors="coerce") if prior is not None else float("nan")
        kickoff = str(evidence.get("kickoff_status", "UNKNOWN")) if evidence is not None else "UNKNOWN"
        quote = str(evidence.get("quote_status", "UNVERIFIED")) if evidence is not None else "UNVERIFIED"
        kickoff_at = parse_time(evidence.get("kickoff_utc")) if evidence is not None else None
        eligible = bool(independent and fresh and kickoff_at and kickoff_at > now and quote == "CACHED RECENT")
        crossed = bool(eligible and pd.notna(old_edge) and pd.notna(edge) and old_edge < MIN_EDGE_PP <= edge)
        rows.append({
            "event": r.get("event"), "outcome_team": r.get("outcome_team"),
            "ticker": key[0], "side": key[1],
            "previous_edge_pp": old_edge, "current_edge_pp": edge,
            "edge_change_pp": round(float(edge-old_edge), 2) if pd.notna(edge) and pd.notna(old_edge) else None,
            "previous_ask_cents": old_ask, "current_ask_cents": ask,
            "ask_change_cents": round(float(ask-old_ask), 2) if pd.notna(ask) and pd.notna(old_ask) else None,
            "threshold_crossing": "NEW +5pp — REVIEW ONLY" if crossed and eligible else ("CROSSED BUT INELIGIBLE" if crossed else "NO"),
            "kickoff_status": ("FUTURE — independently checked" if kickoff_at and kickoff_at > now else "PAST/UNKNOWN — blocked"),
            "research_status": "PREGAME RESEARCH ONLY — NOT VERIFIED" if eligible and independent else "BLOCKED — scan integrity, kickoff or quotes unverified"
        })
    result = pd.DataFrame(rows, columns=COLUMNS)
    result["previous_scan_utc"] = prev_at.isoformat() if prev_at else ""
    result["current_scan_utc"] = curr_at.isoformat() if curr_at else ""
    result["independent_scans"] = independent
    result["scan_fresh_now"] = fresh
    return result.sort_values(
        ["threshold_crossing", "current_edge_pp"], ascending=[True, False], na_position="last")
