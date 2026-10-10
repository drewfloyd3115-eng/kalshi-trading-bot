"""Offline pregame eligibility summary. Never an execution approval."""
from datetime import datetime, timezone
import pandas as pd
from matcher import parse_time

COLUMNS = ["event", "ticker", "side", "outcome_team", "kickoff_utc",
           "kickoff_status", "quote_status", "books", "book_spread_pp",
           "net_edge_pp_1share", "edge_status", "research_status", "reason"]

def eligibility_dashboard(matches, odds, scan_time=None, now=None):
    """Summarize exact matched sides only; unknown evidence always blocks."""
    now = now or datetime.now(timezone.utc)
    scanned = parse_time(scan_time)
    fresh_scan = bool(scanned and -120 <= (now-scanned).total_seconds() <= 300)
    if not isinstance(matches, pd.DataFrame) or matches.empty:
        return pd.DataFrame(columns=COLUMNS)
    rows = []
    for _, match in matches.iterrows():
        ticker = str(match.get("ticker", ""))
        event = str(match.get("event", ""))
        side = str(match.get("side", ""))
        books = int(match.get("books", 0) or 0)
        spread = pd.to_numeric(match.get("book_spread_pp"), errors="coerce")
        edge = pd.to_numeric(match.get("net_edge_pp_1share"), errors="coerce")
        kickoff = None
        if isinstance(odds, pd.DataFrame) and not odds.empty and "start" in odds.columns:
            # Match by event identity using the same exact opponent names as matcher.
            from team_names import normalized
            import re
            parts = re.split(r"\\s+(?:vs\\.?|versus|at|@)\\s+", event, flags=re.I)
            if len(parts) == 2 and {"home", "away"}.issubset(odds.columns):
                pair = {normalized(x) for x in parts}
                same = odds[odds.apply(lambda r:
                    {normalized(r.get("home")), normalized(r.get("away"))} == pair, axis=1)]
                times = {t.isoformat() for v in same["start"] if (t := parse_time(v))}
                if len(times) == 1 and len(same) >= 2:
                    kickoff = parse_time(next(iter(times)))
        kickoff_ok = bool(kickoff and kickoff > now)
        quote_ok = fresh_scan and books >= 2
        edge_ok = pd.notna(edge) and edge >= 5
        reasons = []
        if not kickoff_ok: reasons.append("Independent future kickoff unavailable")
        if not quote_ok: reasons.append("Fresh two-book scan unavailable")
        if pd.isna(spread) or spread > 5: reasons.append("Book disagreement/quality unverified")
        if not edge_ok: reasons.append("Below +5pp or no edge")
        rows.append({
            "event": event, "ticker": ticker, "side": side,
            "outcome_team": match.get("outcome_team", ""),
            "kickoff_utc": kickoff.isoformat() if kickoff else "",
            "kickoff_status": "FUTURE (cached)" if kickoff_ok else "UNKNOWN/PAST",
            "quote_status": "CACHED RECENT" if quote_ok else "UNVERIFIED/STALE",
            "books": books, "book_spread_pp": spread,
            "net_edge_pp_1share": edge,
            "edge_status": "PASSES PRELIMINARY FILTER" if edge_ok else "BELOW THRESHOLD",
            "research_status": "REVIEW ONLY — NOT APPROVED" if not reasons else "BLOCKED",
            "reason": "; ".join(reasons) if reasons else "Fees, rules, execution and live status still unverified"
        })
    return pd.DataFrame(rows, columns=COLUMNS)
