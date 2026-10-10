"""Read-only diagnostics for why sportsbook games do not reach comparison."""
import pandas as pd
from datetime import datetime, timezone, timedelta
from matcher import parse_time
import re
from team_names import normalized

def diagnostics(markets, odds):
    if markets is None or odds is None or markets.empty or odds.empty:
        return pd.DataFrame()
    now = datetime.now(timezone.utc)
    rows = []
    for (league, home, away), group in odds.groupby(["league", "home", "away"]):
        start = parse_time(group.iloc[0].get("start"))
        fresh = 0
        for _, book in group.iterrows():
            updated = parse_time(book.get("updated"))
            if updated and now-timedelta(minutes=15) <= updated <= now+timedelta(minutes=2):
                fresh += 1
        candidates = markets[markets["league"] == league]
        a, b = normalized(home), normalized(away)
        found = []
        for _, m in candidates.iterrows():
            parts = re.split(r"\s+(?:vs\.?|versus|at|@)\s+", str(m.get("event", "")), flags=re.I)
            if len(parts) == 2 and a and b and a != b and {normalized(x) for x in parts} == {a, b}:
                found.append(m)
        if not start or start <= now:
            reason = "Game already started or missing kickoff"
        elif fresh < 2:
            reason = "Fewer than 2 recently updated sportsbook rows"
        elif not found:
            reason = "Team names not recognized in Kalshi event"
        else:
            reason = "Event candidate found; outcome/pricing or other validation may reject"
        rows.append({"league": league, "game": str(away)+" @ "+str(home),
                     "sportsbook_rows": len(group), "fresh_rows": fresh,
                     "kalshi_event_candidates": len(found), "reason": reason})
    return pd.DataFrame(rows).sort_values(["kalshi_event_candidates","sportsbook_rows"],ascending=[True,False])
