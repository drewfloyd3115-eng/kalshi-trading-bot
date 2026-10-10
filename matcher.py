"""Conservative pregame moneyline matching. Research only, not an execution signal."""
import re
from datetime import datetime, timezone, timedelta
import pandas as pd
from edge_engine import no_vig, taker_fee

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
            if not all(re.search(r"(?<!\\w)" + re.escape(k) + r"(?!\\w)", event) for k in (home_key, away_key)):
                continue
            # Title must uniquely identify the YES-winning team.
            yes_team = [t for t, k in ((home, home_key), (away, away_key))
                        if re.search(r"(?<!\\w)" + re.escape(k) + r"(?!\\w)", title)]
            if len(yes_team) != 1:
                continue
            valid = []
            for _, book in group.iterrows():
                start = parse_time(book.get("start"))
                updated = parse_time(book.get("updated"))
                if not start or start <= now or not updated or updated > now + timedelta(minutes=2) or now - updated > timedelta(minutes=15):
                    continue
                try:
                    a, b = team_key(book["team_a"]), team_key(book["team_b"])
                    if {a, b} != {home_key, away_key}:
                        continue
                    fy, fn = no_vig(float(book["odds_a"]), float(book["odds_b"]))
                    fair = fy if a == team_key(yes_team[0]) else fn
                    valid.append((book["book"], fair))
                except (ValueError, TypeError, ZeroDivisionError):
                    continue
            # Two independent books minimum, otherwise avoid fragile comparisons.
            if len({x[0] for x in valid}) < 2:
                continue
            fair = sorted(v for _, v in valid)[len(valid)//2]
            for side, p, col in (("YES", fair, "yes_ask_cents"),
                                 ("NO", 1-fair, "no_ask_cents")):
                try:
                    ask = float(m[col])
                    if not 0 < ask < 100:
                        continue
                    fee = taker_fee(ask, 1)
                    edge = 100*(p-ask/100-fee)
                    rows.append({"league": m["league"], "event": m["event"],
                        "ticker": m["ticker"], "side": side, "ask_cents": ask,
                        "fair_pct": round(p*100, 2), "net_edge_pp_1share": round(edge, 2),
                        "books": len({x[0] for x in valid}), "status": "UNVERIFIED — DEPTH/RECHECK REQUIRED"})
                except (TypeError, ValueError, KeyError):
                    continue
    return pd.DataFrame(rows).sort_values("net_edge_pp_1share", ascending=False) if rows else pd.DataFrame()
