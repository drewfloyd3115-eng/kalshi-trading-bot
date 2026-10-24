"""Auditable CFB historical market baselines. No executable betting prices.

Source: CFBD /lines historical closing lines, or a user-supplied CSV with
EXPLICIT home-team handicap. CFBD lines lack individual captured-at timestamps:
they may be used for retrospective market accuracy comparison only, NEVER as
historical executable entry quotes or model inputs at an earlier time.
"""
from __future__ import annotations

import re
import requests
import pandas as pd
import numpy as np

CFBD_LINES_URL = "https://api.collegefootballdata.com/lines"
LINE_COLUMNS = ("game_id", "home_team", "away_team", "provider",
                "home_handicap", "total")

def _numeric(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_closing_lines(frame: pd.DataFrame) -> pd.DataFrame:
    """Require one selected provider/fixture, stable identities and signed HOME spread."""
    missing = set(LINE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError("Missing historical line columns: " + ", ".join(sorted(missing)))
    data = frame[list(LINE_COLUMNS)].copy()
    data["game_id"] = data.game_id.astype(str).str.strip()
    for col in ("home_team", "away_team", "provider"):
        data[col] = data[col].fillna("").astype(str).str.strip()
    if data.empty:
        raise ValueError("No historical bookmaker records loaded")
    if (data.game_id.eq("") | data.game_id.eq("nan") |
        data.home_team.eq("") | data.away_team.eq("") |
        data.home_team.eq(data.away_team) | data.provider.eq("")).any():
        raise ValueError("Invalid game ID, team names or sportsbook provider")
    if data.game_id.duplicated().any():
        raise ValueError("Duplicate game_id: select ONE bookmaker per game")
    for col in ("home_handicap", "total"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if data.home_handicap.isna().all() and data.total.isna().all():
        raise ValueError("No valid spread or total values")
    if (data.home_handicap.notna() & ~data.home_handicap.between(-80, 80)).any():
        raise ValueError("Home handicap outside plausible CFB range")
    if (data.total.notna() & ~data.total.between(15, 120)).any():
        raise ValueError("Game total outside plausible CFB range")
    if (data.home_handicap.isna() & data.total.isna()).any():
        raise ValueError("At least one verified market line required per game")
    return data.sort_values("game_id").reset_index(drop=True)


def _formatted_home_handicap(formatted: str, home: str, away: str):
    """Safely infer home handicap ONLY from explicit signed full team label."""
    if not isinstance(formatted, str):
        return None
    match = re.fullmatch(r"\s*(.*?)\s+([+-]\d+(?:\.\d+)?)\s*", formatted)
    if not match:
        return None
    team, sign_value = match.groups()
    team = " ".join(team.lower().split())
    home = " ".join(str(home).lower().split())
    away = " ".join(str(away).lower().split())
    if not team or home == away:
        return None
    value = _numeric(sign_value)
    if value is None or abs(value) > 80:
        return None
    if team == home:
        return value
    if team == away:
        return -value
    return None


# Fixed tie-breaker determined before evaluating any actual game outcomes.
# Auto chooses ONE provider for a whole year based only on usable line coverage.
PROVIDER_PRIORITY = ("consensus", "DraftKings", "Caesars", "teamrankings",
                     "Bovada", "numberfire")


def available_cfbd_providers(raw: list) -> dict:
    """Sanitized availability diagnostics. No keys, raw payloads or prices emitted."""
    if not isinstance(raw, list):
        raise ValueError("CFBD /lines must return a game list")
    providers: dict[str, dict] = {}
    with_lines = 0
    malformed_games = 0
    for g in raw:
        if not isinstance(g, dict):
            malformed_games += 1
            continue
        g_lines = g.get("lines") or []
        if not isinstance(g_lines, list):
            malformed_games += 1
            continue
        if g_lines:
            with_lines += 1
        home = g.get("homeTeam", g.get("home_team"))
        away = g.get("awayTeam", g.get("away_team"))
        identifier = g.get("id", g.get("gameId", g.get("game_id")))
        valid_game = identifier is not None and home and away and home != away
        seen_provider = set()
        for line in g_lines:
            if not isinstance(line, dict):
                continue
            name = str(line.get("provider") or "").strip()
            if not name:
                continue
            item = providers.setdefault(name, {"provider": name, "game_records": 0,
                                               "usable_games": 0,
                                               "usable_spreads": 0,
                                               "usable_totals": 0})
            if name.casefold() in seen_provider:
                continue
            seen_provider.add(name.casefold())
            item["game_records"] += 1
            if not valid_game:
                continue
            formatted = line.get("formattedSpread", line.get("formatted_spread"))
            spread = _formatted_home_handicap(formatted, home, away)
            total = _numeric(line.get("overUnder", line.get("over_under")))
            if total is not None and not (15 <= total <= 120):
                total = None
            if spread is not None or total is not None:
                item["usable_games"] += 1
                item["usable_spreads"] += int(spread is not None)
                item["usable_totals"] += int(total is not None)
    sorted_providers = sorted(providers.values(),
                              key=lambda d: (-d["usable_games"], d["provider"].casefold()))
    return {"total_games_returned": len(raw),
            "games_with_line_records": with_lines,
            "malformed_games": malformed_games,
            "providers": sorted_providers}


def choose_cfbd_provider(report: dict, preference: str = "Auto") -> str:
    """Deterministic provider selection; never select by actual results/profit."""
    choices = [p for p in report.get("providers", []) if p["usable_games"] > 0]
    if not choices:
        raise ValueError("No usable provider data: CFBD returned "
                         f"{report.get('total_games_returned',0)} games, "
                         f"{report.get('games_with_line_records',0)} with line records. "
                         "Check season, access tier, and available providers.")
    if preference != "Auto":
        requested = next((p for p in choices if p["provider"].casefold() == preference.casefold()), None)
        if requested is None:
            available = ", ".join(f"{p['provider']} ({p['usable_games']} games)" for p in choices[:8])
            raise ValueError(f"Provider {preference!r} has no usable records in this season. "
                             f"Available: {available}. Use Auto or select an available provider.")
        return requested["provider"]
    preference_rank = {name.casefold(): i for i, name in enumerate(PROVIDER_PRIORITY)}
    return min(choices, key=lambda p: (-p["usable_games"],
                                      preference_rank.get(p["provider"].casefold(), 999),
                                      p["provider"].casefold()))["provider"]


def fetch_cfbd_line_inventory(year: int, token: str, session=None) -> tuple[list, dict]:
    """Single season request without provider filter to see *actual* availability."""
    if not token:
        raise ValueError("CFBD_API_KEY required for historical sportsbook lines")
    if isinstance(year, bool) or not (2013 <= int(year) <= 2030):
        raise ValueError("Historical season must be 2013–2030")
    http = session or requests
    response = http.get(CFBD_LINES_URL, params={"year": int(year)},
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    raw = response.json()
    report = available_cfbd_providers(raw)
    return raw, report


def parse_cfbd_closing_lines(raw: list, provider: str = "consensus") -> pd.DataFrame:
    """Normalize CFBD provider's closing spread/total without guessing home sign.

    An explicit formattedSpread e.g. "Away University -7.5" is necessary for
    a spread: no assumption about the sign of vendor's numeric spread.
    If not present, the total may still be compared independently.
    """
    if not isinstance(raw, list):
        raise ValueError("CFBD /lines response must be a list")
    report = available_cfbd_providers(raw)
    chosen = choose_cfbd_provider(report, provider)
    rows = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        game_id = g.get("id", g.get("gameId", g.get("game_id")))
        home = g.get("homeTeam", g.get("home_team"))
        away = g.get("awayTeam", g.get("away_team"))
        if game_id is None or not home or not away or home == away:
            continue
        matching = [line for line in (g.get("lines") or [])
                    if isinstance(line, dict) and
                    str(line.get("provider", "")).casefold() == chosen.casefold()]
        if not matching:
            continue
        if len(matching) != 1:
            raise ValueError(f"Duplicate {chosen} provider records for CFBD game {game_id}")
        line = matching[0]
        spread = _formatted_home_handicap(line.get("formattedSpread", line.get("formatted_spread")), home, away)
        reported = _numeric(line.get("spread"))
        if spread is not None and reported is not None and abs(abs(spread)-abs(reported)) > .01:
            raise ValueError(f"CFBD formatted/numeric spread discrepancy for game {game_id}")
        total = _numeric(line.get("overUnder", line.get("over_under")))
        if spread is None and total is None:
            continue
        rows.append({"game_id": str(game_id), "home_team": str(home), "away_team": str(away),
                     "provider": str(line.get("provider")), "home_handicap": spread,
                     "total": total})
    if not rows:
        raise ValueError(f"No usable historical lines after selecting {chosen}; inspect the source diagnostics")
    result = normalize_closing_lines(pd.DataFrame(rows))
    result.attrs["selected_provider"] = chosen
    result.attrs["source_diagnostics"] = report
    return result


def fetch_cfbd_closing_lines(year: int, token: str, provider: str = "Auto",
                             session=None) -> pd.DataFrame:
    """Use a single unfiltered season request, then one provider chosen locally.

    No silent fallback for a specifically requested provider. Report available
    alternatives and safely refuse if no usable lines exist.
    """
    raw, report = fetch_cfbd_line_inventory(year, token, session=session)
    return parse_cfbd_closing_lines(raw, provider=provider)


def calibration_table(predictions: pd.DataFrame, season: int) -> pd.DataFrame:
    """Holdout favorites: stated win confidence versus realized winner frequency."""
    p = predictions.loc[predictions.completed & predictions.eligible_history &
                        (predictions.season == season)].copy()
    if p.empty:
        return pd.DataFrame(columns=["confidence_band", "games", "mean_predicted_confidence",
                                     "actual_win_frequency", "calibration_gap_pp"])
    prob = pd.to_numeric(p.home_win_prob).clip(.000001, .999999)
    confidence = prob.where(prob >= .5, 1-prob)
    picked_home = prob >= .5
    won = ((p.home_points > p.away_points) == picked_home).astype(float)
    bins = pd.cut(confidence, [.5, .6, .7, .8, .9, 1.000001],
                  labels=["50–60%", "60–70%", "70–80%", "80–90%", "90–100%"],
                  include_lowest=True)
    df = pd.DataFrame({"confidence_band": bins, "confidence": confidence, "won": won})
    agg = df.groupby("confidence_band", observed=True).agg(
        games=("won","size"),
        mean_predicted_confidence=("confidence","mean"),
        actual_win_frequency=("won","mean")).reset_index()
    agg["calibration_gap_pp"] = (
        (agg.mean_predicted_confidence-agg.actual_win_frequency)*100).round(2)
    return agg.round({"mean_predicted_confidence": 3,"actual_win_frequency": 3})


def benchmark_predictions(predictions: pd.DataFrame, closing_lines: pd.DataFrame,
                          season: int = 2025) -> tuple[dict, pd.DataFrame]:
    """Honest *paired* model-versus-market MAE on games with verified exact IDs.

    Historical CFBD lines are un-timestamped 'closing' values; NOT safe for
    pregame entry backtests, CLV measurements, probability EV or market-blended
    training features. No betting return is computed.
    """
    lines = normalize_closing_lines(closing_lines)
    p = predictions.loc[predictions.completed & predictions.eligible_history &
                        (predictions.season == season)].copy()
    p["game_id"] = p.game_id.astype(str)
    if p.empty:
        raise ValueError(f"No eligible completed model forecasts for {season}")
    m = p.merge(lines,on="game_id",how="inner",validate="one_to_one",suffixes=("","_line"))
    if m.empty:
        raise ValueError("Zero matching historical game IDs: use CFBD game IDs and matching seasons")
    # Same game ID is not enough if a dataset reused IDs or team names differ.
    if (~(m.home_team == m.home_team_line) | ~(m.away_team == m.away_team_line)).any():
        raise ValueError("Historical bookmaker and model team identity mismatch; do not fuzzy-match")
    m["actual_margin"] = m.home_points - m.away_points
    m["actual_total"] = m.home_points + m.away_points
    m["market_home_margin"] = -m.home_handicap
    m["model_margin_abs_error"] = abs(m.actual_margin - m.projected_home_margin)
    m["market_margin_abs_error"] = abs(m.actual_margin - m.market_home_margin)
    m["model_total_abs_error"] = abs(m.actual_total - m.projected_total)
    m["market_total_abs_error"] = abs(m.actual_total - m.total)
    spreads = m.loc[m.home_handicap.notna()].copy()
    totals = m.loc[m.total.notna()].copy()
    def pair_metrics(sample, kind):
        if sample.empty:
            return {"games": 0, "model_mae": None, "market_mae": None,
                    "market_advantage_points": None, "paired_ci95_points": None}
        model = sample[f"model_{kind}_abs_error"].to_numpy(dtype=float)
        market = sample[f"market_{kind}_abs_error"].to_numpy(dtype=float)
        diff = market - model   # positive => model lower absolute error
        # Paired 95% bootstrap CI, fixed seed for reproducibility; descriptive
        # approximation only, not a season-clustered inference or ROI proof.
        rng = np.random.default_rng(20261024)
        draws = rng.integers(0, len(diff), size=(1500,len(diff)))
        boot = diff[draws].mean(axis=1)
        return {"games":len(sample), "model_mae":round(float(model.mean()),3),
                "market_mae":round(float(market.mean()),3),
                "market_advantage_points":round(float(diff.mean()),3),
                "paired_ci95_points":[round(float(x),3) for x in np.quantile(boot,[.025,.975])]}
    summary = {
        "season": int(season), "eligible_model_games":len(p),
        "matched_market_games":len(m), "matched_coverage_pct":round(100*len(m)/len(p),1),
        "spread_comparison":pair_metrics(spreads,"margin"),
        "total_comparison":pair_metrics(totals,"total"),
        "source_warning":("Reported historical closing lines are not timestamped executable "
                          "quotes. No EV, ROI, CLV, or betting recommendation can be inferred. "
                          "CIs are naive game-level bootstrap, not week-cluster adjusted.")
    }
    output_cols = [
        "game_id","season","week","kickoff_utc","away_team","home_team",
        "provider","actual_margin","projected_home_margin","market_home_margin",
        "model_margin_abs_error","market_margin_abs_error",
        "actual_total","projected_total","total",
        "model_total_abs_error","market_total_abs_error"
    ]
    return summary, m[output_cols].sort_values("kickoff_utc").reset_index(drop=True)
