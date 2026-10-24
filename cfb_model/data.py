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
        # FBS-only: if division data is provided, reject FCS matchups.
        if (g.get("homeDivision") not in (None, "fbs", "FBS") or
                g.get("awayDivision") not in (None, "fbs", "FBS")):
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
    response = session.get(CFBD_URL, params={"year": int(year), "division": "fbs"},
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
