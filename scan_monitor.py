"""Manual scan-to-scan comparisons. No scheduling, API calls or order placement."""
import pandas as pd
from config import MIN_EDGE_PP

COLUMNS = ["event", "outcome_team", "ticker", "side", "previous_edge_pp",
           "current_edge_pp", "edge_change_pp", "previous_ask_cents",
           "current_ask_cents", "ask_change_cents", "threshold_crossing",
           "kickoff_status", "research_status"]

def scan_changes(previous, current, eligibility):
    if current is None or current.empty:
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
        prior = before.get(key)
        evidence = statuses.get(key)
        edge = pd.to_numeric(r.get("net_edge_pp_1share"), errors="coerce")
        ask = pd.to_numeric(r.get("ask_cents"), errors="coerce")
        old_edge = pd.to_numeric(prior.get("net_edge_pp_1share"), errors="coerce") if prior is not None else float("nan")
        old_ask = pd.to_numeric(prior.get("ask_cents"), errors="coerce") if prior is not None else float("nan")
        kickoff = str(evidence.get("kickoff_status", "UNKNOWN")) if evidence is not None else "UNKNOWN"
        quote = str(evidence.get("quote_status", "UNVERIFIED")) if evidence is not None else "UNVERIFIED"
        eligible = kickoff.startswith("FUTURE") and quote == "CACHED RECENT"
        crossed = bool(pd.notna(old_edge) and pd.notna(edge) and old_edge < MIN_EDGE_PP <= edge)
        rows.append({
            "event": r.get("event"), "outcome_team": r.get("outcome_team"),
            "ticker": key[0], "side": key[1],
            "previous_edge_pp": old_edge, "current_edge_pp": edge,
            "edge_change_pp": round(float(edge-old_edge), 2) if pd.notna(edge) and pd.notna(old_edge) else None,
            "previous_ask_cents": old_ask, "current_ask_cents": ask,
            "ask_change_cents": round(float(ask-old_ask), 2) if pd.notna(ask) and pd.notna(old_ask) else None,
            "threshold_crossing": "NEW +5pp — REVIEW ONLY" if crossed and eligible else ("CROSSED BUT INELIGIBLE" if crossed else "NO"),
            "kickoff_status": kickoff,
            "research_status": "PREGAME RESEARCH ONLY — NOT VERIFIED" if eligible else "BLOCKED — stale or unknown kickoff/quotes"
        })
    return pd.DataFrame(rows, columns=COLUMNS).sort_values(
        ["threshold_crossing", "current_edge_pp"], ascending=[True, False], na_position="last")
