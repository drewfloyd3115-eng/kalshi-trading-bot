"""Read-only upcoming FBS schedule lookup using ESPN's undocumented public scoreboard.

No auth, odds, quotes, betting or order placement. ESPN does not guarantee this API.
Team identity is matched by exact ESPN numeric team IDs from historical scoreboards,
never fuzzy names. Incomplete or stale responses must fail closed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import requests

from .data import COLUMNS, normalize_games

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/football/"
    "college-football/scoreboard"
)


def parse_schedule_events(payload: dict, id_to_name: dict, now=None) -> pd.DataFrame:
    """Convert scheduled ESPN FBS events to scoreless fixtures.

    Requires both competitors to have exact ESPN team IDs in an FBS-only history
    mapping. Status must be pregame and kickoff strictly in the future.
    """
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("As-of time must have an explicit timezone")
    now = now.tz_convert("UTC")
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Missing ESPN events array; schedule response not usable")
    mapping = {str(k).strip(): str(v).strip() for k, v in id_to_name.items() if str(v).strip()}
    if not mapping:
        raise ValueError("Missing verified ESPN team-ID mapping: reload public FBS game results")
    if not payload["events"]:
        raise ValueError("ESPN returned no schedule events; verify endpoint and date range")
    rows, seen = [], set()
    stats = {"received": len(payload["events"]), "started": 0,
             "unmapped": 0, "invalid": 0}
    for e in payload["events"]:
        if not isinstance(e, dict):
            stats["invalid"] += 1
            continue
        state = (e.get("status") or {}).get("type") or {}
        if state.get("state") != "pre" or state.get("completed") is True:
            stats["started"] += 1
            continue
        timestamp = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        if pd.isna(timestamp) or timestamp <= now:
            stats["started"] += 1
            continue
        competitions = e.get("competitions") or []
        if len(competitions) != 1 or not isinstance(competitions[0], dict):
            stats["invalid"] += 1
            continue
        comp = competitions[0]
        opponents = comp.get("competitors") or []
        if len(opponents) != 2:
            stats["invalid"] += 1
            continue
        matched = {}
        for x in opponents:
            if not isinstance(x, dict) or x.get("homeAway") not in ("home", "away"):
                continue
            tid = str((x.get("team") or {}).get("id", "")).strip()
            if tid in mapping:
                matched[x["homeAway"]] = mapping[tid]
        if len(matched) != 2:
            stats["unmapped"] += 1
            continue
        eid = str(e.get("id", "")).strip()
        if not eid or eid in seen or matched["home"] == matched["away"]:
            stats["invalid"] += 1
            continue
        seen.add(eid)
        rows.append({
            "game_id": f"espn-{eid}", "season": int(timestamp.year),
            "week": int(((e.get("week") or {}).get("number")) or 0),
            "kickoff_utc": timestamp.isoformat(),
            "home_team": matched["home"], "away_team": matched["away"],
            "home_points": None, "away_points": None,
            "completed": False, "neutral_site": bool(comp.get("neutralSite", False))
        })
    if not rows:
        raise ValueError(
            "No future, pregame FBS matchups with verified ESPN team IDs "
            f"(received={stats['received']}, started={stats['started']}, "
            f"unmapped={stats['unmapped']}, invalid={stats['invalid']}). "
            "Refresh historical public scores or try another upcoming week."
        )
    df = normalize_games(pd.DataFrame(rows, columns=COLUMNS))
    df.attrs.update({
        "source": "ESPN public scoreboard (unofficial, read-only)",
        "fetched_utc": now.isoformat(), "stats": stats
    })
    return df


def fetch_upcoming_schedule(id_to_name: dict, now=None, days: int = 7,
                            session=None) -> pd.DataFrame:
    """Fetch an 8-day horizon through separate, single-date ESPN scoreboards.

    ESPN discontinued DATE-RANGE requests for team-sport scoreboards in 2026:
    dates=YYYYMMDD-YYYYMMDD yields 400; YYYYMMDD still works.
    We combine bounded daily results, deduplicate exact ESPN event IDs, and
    reject the entire fetch when any day fails. No fabricated partial schedule.
    """
    if not isinstance(days, int) or isinstance(days, bool) or days < 1 or days > 14:
        raise ValueError("Days must be 1–14")
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("As-of time must be timezone-aware")
    now = now.tz_convert("UTC")
    end = now + pd.Timedelta(days=days)
    client = session or requests
    events_by_id = {}
    dates_checked = []
    # A rolling N*24 hour horizon can touch N+1 distinct UTC calendar dates.
    for day in pd.date_range(now.normalize(), end.normalize(), freq="D"):
        date_string = day.strftime("%Y%m%d")
        response = client.get(ESPN_SCOREBOARD, params={
            "dates": date_string, "groups": "80", "limit": 500
        }, timeout=25)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError(f"Invalid ESPN scoreboard for {date_string}; no partial schedule")
        for event in payload["events"]:
            if not isinstance(event, dict):
                continue
            eid = str(event.get("id") or "").strip()
            if eid:
                # Multiple daily scoreboards can contain the same fixture.
                events_by_id.setdefault(eid, event)
        dates_checked.append(date_string)
    if not events_by_id:
        raise ValueError(f"ESPN returned no games for the next {days} days")
    # Respect the precise rolling horizon, not just the inclusive calendar dates.
    filtered = []
    for event in events_by_id.values():
        kickoff = pd.to_datetime(event.get("date"), utc=True, errors="coerce")
        if pd.notna(kickoff) and now < kickoff <= end:
            filtered.append(event)
    result = parse_schedule_events({"events": filtered}, id_to_name, now=now)
    result.attrs["dates_checked"] = dates_checked
    result.attrs["requested_days"] = days
    return result
