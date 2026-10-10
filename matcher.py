"""Conservative pregame moneyline matching. Research only, not an execution signal."""
import re
from datetime import datetime, timezone, timedelta
import pandas as pd
from statistics import median
from edge_engine import no_vig, taker_fee
from team_names import normalized

# Conservative school-name normalization. Never fuzzy-match ambiguous names.
ALIASES = {"miami (oh)": "miami ohio", "miami (fl)": "miami florida",
           "ole miss": "mississippi", "uconn": "connecticut",
           "unc": "north carolina", "pitt": "pittsburgh",
           "smu": "southern methodist", "byu": "brigham young",
           "ucf": "central florida", "usc": "southern california",
           "lsu": "louisiana state", "tcu": "texas christian",
           "utsa": "texas san antonio", "uab": "alabama birmingham"}
MASCOTS = set("crimson tide tigers bulldogs wildcats eagles hawks redhawks fighting irish longhorns sooners buckeyes wolverines spartans lions bears cougars knights huskies broncos trojans seminoles hurricanes rebels commodores volunteers gators ducks beavers panthers owls yellow jackets tar heels wolfpack blue devils mountaineers cyclones aggies mustangs cardinals rams raiders rockets falcons pirates golden green wave orange".split())

def clean(name):
    name = str(name or "").lower().replace("&", " and ")
    name = re.sub(r"[^a-z0-9 ]+", " ", name).strip()
    words = [w for w in name.split() if w not in MASCOTS]
    return " ".join(words)

def team_key(name):
    raw = str(name or "").lower().strip()
    for alias, canonical in ALIASES.items():
        if raw == alias or raw.startswith(alias + " "):
            return canonical
    return clean(raw)

def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else None
    except (TypeError, ValueError):
        return None

def compare(markets, odds, now=None):
    """Only matches when both school names appear uniquely in the Kalshi event title.
    Rejects started games, stale odds, incomplete pricing, ambiguous outcomes.
    """
    now = now or datetime.now(timezone.utc)
    if markets is None or odds is None or len(markets) == 0 or len(odds) == 0:
        return pd.DataFrame()
    rows = []
    for _, m in markets.iterrows():
        event = clean(m.get("event", ""))
        title = clean(m.get("title", ""))
        for (home, away), group in odds[odds["league"] == m["league"]].groupby(["home", "away"]):
            home_key, away_key = team_key(home), team_key(away)
            if not home_key or not away_key or home_key == away_key:
                continue
            # Require exact two-team event identity, explicit YES team, and game date.
            import re as _re
            from datetime import date
            event_raw = str(m.get("event", ""))
            parts = _re.split(r"\s+(?:vs\.?|versus|at|@)\s+", event_raw, flags=_re.I)
            if len(parts) != 2 or {normalized(x) for x in parts} != {normalized(home), normalized(away)}:
                continue
            label = normalized(m.get("yes_sub_title", ""))
            if label not in (normalized(home), normalized(away)) or normalized(home) == normalized(away):
                continue
            date_match = _re.search(r"-(\d{2})([A-Z]{3})(\d{2})(?=[A-Z])", str(m.get("ticker", "")).upper())
            months = {x:i for i,x in enumerate(("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"),1)}
            if not date_match or date_match.group(2) not in months:
                continue
            try:
                event_day = date(2000+int(date_match.group(1)), months[date_match.group(2)], int(date_match.group(3)))
            except ValueError:
                continue
            kickoff = parse_time(group.iloc[0].get("start"))
            if not kickoff or event_day not in (kickoff.date(), (kickoff-timedelta(days=1)).date()):
                continue
            yes_team = [home if label == normalized(home) else away]
            valid = []
            quote_ages = []
            seen_books = set()
            for _, book in group.iterrows():
                start = parse_time(book.get("start"))
                updated = parse_time(book.get("updated"))
                if not start or abs((start-kickoff).total_seconds()) > 60 or start <= now or not updated or updated > now + timedelta(minutes=2) or now - updated > timedelta(minutes=15):
                    continue
                try:
                    a, b = normalized(book["team_a"]), normalized(book["team_b"])
                    if {a, b} != {normalized(home), normalized(away)}:
                        continue
                    fy, fn = no_vig(float(book["odds_a"]), float(book["odds_b"]))
                    fair = fy if a == normalized(yes_team[0]) else fn
                    book_id = str(book.get("book_key") or book.get("book") or "").strip().lower()
                    if not book_id or book_id in seen_books:
                        continue
                    seen_books.add(book_id)
                    valid.append((book_id, fair))
                    quote_ages.append((now-updated).total_seconds()/60)
                except (ValueError, TypeError, ZeroDivisionError):
                    continue
            # Two independent books minimum, otherwise avoid fragile comparisons.
            if len({x[0] for x in valid}) < 2:
                continue
            fair = median(v for _, v in valid)
            low_fair = min(v for _, v in valid)
            high_fair = max(v for _, v in valid)
            book_details = "; ".join(f"{book_id}: {prob*100:.2f}%" for book_id,prob in sorted(valid))
            for side, p, col in (("YES", fair, "yes_ask_cents"),
                                 ("NO", 1-fair, "no_ask_cents")):
                try:
                    ask = float(m[col])
                    if not 0 < ask < 100:
                        continue
                    fee = taker_fee(ask, 1)
                    edge = 100*(p-ask/100-fee)
                    rows.append({"league": m["league"], "event": m["event"],
                        "ticker": m["ticker"], "side": side, "outcome_team": normalized(yes_team[0] if side == "YES" else (away if yes_team[0] == home else home)), "ask_cents": ask,
                        "fair_pct": round(p*100, 2), "net_edge_pp_1share": round(edge, 2),
                        "books": len({x[0] for x in valid}),
                        "book_low_pct": round((low_fair if side == "YES" else 1-high_fair)*100,2),
                        "book_high_pct": round((high_fair if side == "YES" else 1-low_fair)*100,2),
                        "book_spread_pp": round((high_fair-low_fair)*100,2),
                        "oldest_quote_minutes": round(max(quote_ages),1),
                        "book_estimates": book_details if side == "YES" else "; ".join(f"{bid}: {(1-prob)*100:.2f}%" for bid,prob in sorted(valid)),
                        "status": "UNVERIFIED — DEPTH/RECHECK REQUIRED"})
                except (TypeError, ValueError, KeyError):
                    continue
    return pd.DataFrame(rows).sort_values("net_edge_pp_1share", ascending=False) if rows else pd.DataFrame()
