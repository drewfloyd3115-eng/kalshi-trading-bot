"""CFBD historical games ingestion. Dates are timezone-aware UTC; no guessing scores."""
from __future__ import annotations
from datetime import datetime, timezone
import io
import os
import requests
import pandas as pd

COLUMNS = ["game_id", "season", "week", "kickoff_utc", "home_team", "away_team",
           "home_points", "away_points", "completed", "neutral_site"]
CFBD_URL = "https://api.collegefootballdata.com/games"


def parse_games(raw: list[dict]) -> pd.DataFrame:
    rows = []
    for g in raw:
        home = g.get("homeTeam", g.get("home_team"))
        away = g.get("awayTeam", g.get("away_team"))
        kickoff = g.get("startDate", g.get("kickoff_utc"))
        # Official CFBD schema uses homeClassification / awayClassification.
        # Never silently mix FCS results into the FBS-only baseline.
        home_class = g.get("homeClassification", g.get("homeDivision"))
        away_class = g.get("awayClassification", g.get("awayDivision"))
        if str(home_class).lower() != "fbs" or str(away_class).lower() != "fbs":
            continue
        if not home or not away or not kickoff or home == away:
            continue
        date = pd.to_datetime(kickoff, utc=True, errors="coerce")
        if pd.isna(date):
            continue
        hp, ap = g.get("homePoints", g.get("home_points")), g.get("awayPoints", g.get("away_points"))
        is_done = g.get("completed", hp is not None and ap is not None)
        is_done = str(is_done).lower() == "true" if not isinstance(is_done, bool) else is_done
        if is_done and (hp is None or ap is None):
            continue
        rows.append({"game_id": str(g.get("id", g.get("game_id", ""))),
                     "season": int(g.get("season", date.year)), "week": int(g.get("week", 0) or 0),
                     "kickoff_utc": date.isoformat(), "home_team": str(home), "away_team": str(away),
                     "home_points": float(hp) if is_done else None,
                     "away_points": float(ap) if is_done else None,
                     "completed": is_done,
                     "neutral_site": bool(g.get("neutralSite", g.get("neutral_site", False)))})
    return normalize_games(pd.DataFrame(rows, columns=COLUMNS))


def normalize_games(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError("Missing game columns: " + ", ".join(sorted(missing)))
    df = df[COLUMNS].copy()
    df["kickoff_utc"] = pd.to_datetime(df["kickoff_utc"], utc=True, errors="coerce")
    if df["kickoff_utc"].isna().any():
        raise ValueError("Every kickoff must be an explicit timezone-aware timestamp")
    # Prevent ambiguous order or duplicate event identities in training/backtests.
    df["game_id"] = df["game_id"].astype(str)
    if df["game_id"].eq("").any() or df["game_id"].duplicated().any():
        raise ValueError("Every game must have a unique, nonblank game_id")
    for col in ("home_points", "away_points"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["completed"] = df["completed"].astype(str).str.lower().eq("true")
    df["neutral_site"] = df["neutral_site"].astype(str).str.lower().eq("true")
    if (df["completed"] & (df["home_points"].isna() | df["away_points"].isna())).any():
        raise ValueError("Completed games must contain both scores")
    if ((df["home_points"].dropna() < 0).any() or (df["away_points"].dropna() < 0).any()):
        raise ValueError("Scores cannot be negative")
    return df.sort_values(["kickoff_utc", "game_id"]).reset_index(drop=True)


def fetch_year(year: int, token: str, session=None) -> pd.DataFrame:
    if not token:
        raise ValueError("CFBD_API_KEY is required; do not store the API key in GitHub")
    session = session or requests
    response = session.get(CFBD_URL, params={"year": int(year), "classification": "fbs"},
                           headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    return parse_games(response.json())


def fetch_years(start: int, end: int, token: str) -> pd.DataFrame:
    if start > end or end - start > 15:
        raise ValueError("Select a range of up to 16 seasons")
    pieces = [fetch_year(y, token) for y in range(start, end + 1)]
    return normalize_games(pd.concat(pieces, ignore_index=True))


def read_games_csv(uploaded) -> pd.DataFrame:
    return normalize_games(pd.read_csv(uploaded))

# Public season scoreboards: https://github.com/jackwarfield/cfb_rankings
# Third-party research fallback. Not an official CFBD source.
PUBLIC_GAMES_BASE = "https://raw.githubusercontent.com/jackwarfield/cfb_rankings/main"


def parse_public_games_csv(content: str) -> pd.DataFrame:
    """Adapt raw public scoreboards to FBS-only games, no invented outcomes."""
    df = pd.read_csv(io.StringIO(content))
    required = {"id","season","week","start_date","neutral_site","home_team",
                "away_team","home_points","away_points","home_level","away_level"}
    if not required.issubset(df.columns):
        raise ValueError("Public scoreboard missing fields: " + ", ".join(sorted(required-set(df.columns))))
    df = df.loc[df.home_level.astype(str).str.lower().eq("fbs") &
                df.away_level.astype(str).str.lower().eq("fbs")].copy()
    # Collect stable ESPN numeric team IDs from the SAME filtered FBS data.
    # A numeric ID with conflicting recorded team names is considered ambiguous.
    id_names: dict[str, set[str]] = {}
    if {"home_id", "away_id"}.issubset(df.columns):
        for side in ("home", "away"):
            for raw_id, team in zip(df[f"{side}_id"], df[f"{side}_team"]):
                try:
                    numeric_id = pd.to_numeric(raw_id, errors="coerce")
                    if pd.isna(numeric_id) or float(numeric_id) != int(numeric_id):
                        continue
                    tid = str(int(numeric_id))
                    name = str(team).strip()
                    if name and name.lower() != "nan":
                        id_names.setdefault(tid, set()).add(name)
                except (TypeError, ValueError, OverflowError):
                    continue
    stable_ids = {tid: next(iter(names)) for tid, names in id_names.items() if len(names) == 1}
    ambiguous_ids = [tid for tid, names in id_names.items() if len(names) > 1]
    # No final-status field in this source: withhold recent games even if scores
    # appear, so in-progress numbers cannot become training results.
    kickoff = pd.to_datetime(df.start_date,utc=True,errors="coerce")
    completed = df.home_points.notna() & df.away_points.notna() & (
        kickoff + pd.Timedelta(hours=8) <= pd.Timestamp.now(tz="UTC"))
    converted = pd.DataFrame({
        "game_id":df["id"].astype(str),
        "season":df["season"], "week":df["week"],
        "kickoff_utc":df["start_date"],
        "home_team":df["home_team"], "away_team":df["away_team"],
        "home_points":df["home_points"].where(completed),
        "away_points":df["away_points"].where(completed),
        "completed":completed, "neutral_site":df["neutral_site"]})
    result = normalize_games(converted)
    result.attrs["espn_team_ids"] = stable_ids
    result.attrs["ambiguous_espn_ids"] = ambiguous_ids
    return result


def fetch_public_years(start: int = 2020, end: int = 2026, session=None) -> pd.DataFrame:
    """Fetch genuine FBS results; disclose source gaps rather than fabricate games.

    The third-party 2022 file is currently header-only. Missing seasons are
    excluded and carried as DataFrame metadata for a prominent UI warning.
    Other data corruption, HTTP errors or mismatched season labels fail closed.
    """
    if start < 2020 or end > 2026 or end < start or end - start > 6:
        raise ValueError("Public data source currently covers 2020–2026 only")
    session = session or requests
    parts,missing = [],[]
    for year in range(start,end+1):
        response=session.get(f"{PUBLIC_GAMES_BASE}/games{year}.csv",timeout=30)
        response.raise_for_status()
        part=parse_public_games_csv(response.text)
        if part.empty:
            missing.append(year)
            continue
        if not part.season.eq(year).all():
            raise ValueError(f"Public scoreboard {year} has records from another season")
        parts.append(part)
    if not parts:
        raise ValueError(f"No actual FBS games available for requested seasons {start}–{end}")
    # Cross-year team-name conflicts invalidate an ID instead of guessing.
    names_by_id: dict[str, set[str]] = {}
    invalid_ids = set()
    for part in parts:
        invalid_ids.update(part.attrs.get("ambiguous_espn_ids", []))
        for tid, name in part.attrs.get("espn_team_ids", {}).items():
            names_by_id.setdefault(tid, set()).add(name)
    stable_ids = {tid: next(iter(names)) for tid, names in names_by_id.items()
                  if tid not in invalid_ids and len(names) == 1}
    result=normalize_games(pd.concat(parts,ignore_index=True))
    result.attrs["espn_team_ids"] = stable_ids
    result.attrs["ambiguous_espn_ids"] = sorted(set(names_by_id) - set(stable_ids))
    result.attrs["missing_seasons"] = missing
    result.attrs["source"] = "jackwarfield/cfb_rankings (public third-party scoreboard)"
    return result
