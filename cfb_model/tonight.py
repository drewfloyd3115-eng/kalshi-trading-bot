"""Read-only same-day CFB model slate, fail-closed for unverified betting signals.

Designed for a single manual refresh: historical public FBS scores, exact-ID ESPN
pregame schedule, pregame-only model forecast, and OPTIONAL indicative ESPN lines.
No Odds API credits, no placing orders, no fabricated Kalshi prices or edge.
"""
from __future__ import annotations

import pandas as pd

from .core import walk_forward
from .sim_preview import simulate_preview, model_evidence_quality
from .data import COLUMNS, normalize_games
from ui_timezone import CENTRAL

BOARD_COLUMNS = [
    "game_id", "kickoff_utc", "matchup", "projected_away_score",
    "projected_home_score", "projected_home_margin", "projected_total",
    "home_win_probability_pct", "training_games", "home_sample", "away_sample",
    "market_home_handicap", "market_total", "spread_disagreement_points",
    "total_disagreement_points", "market_provider", "market_verification",
    "market_book_count", "market_oldest_quote_minutes", "caution",
    "decision", "home_team", "away_team", "home_espn_id", "away_espn_id",
    "margin_sigma", "total_sigma", "research_confidence", "confidence_color",
    "confidence_reason", "simulations", "sim_home_win_pct","sim_away_win_pct",
    "sim_home_cover_pct", "sim_over_pct", "sim_margin_p10", "sim_margin_p90",
    "sim_total_p10", "sim_total_p90", "market_source_label"
]


def _as_of(now=None) -> pd.Timestamp:
    value = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError("As-of clock must be timezone-aware")
    return value.tz_convert("UTC")


def tonight_slate(games: pd.DataFrame, schedule: pd.DataFrame, now=None,
                  evening_hour: int = 17, fresh_market=None) -> pd.DataFrame:
    """Only not-started games on the current Chicago calendar date.

    History is not replaced with a synthetic schedule or sportsbook projections.
    Exact ESPN event IDs are required. 'Decision' is always PASS until there is
    independently validated pricing, rules, fees and reliable probabilities.
    """
    asof = _as_of(now)
    if isinstance(evening_hour, bool) or not (0 <= int(evening_hour) <= 23):
        raise ValueError("Invalid Central evening hour")
    if not isinstance(games, pd.DataFrame) or games.empty:
        raise ValueError("Load real historical FBS games before forecasting")
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        raise ValueError("No official pregame fixtures found in the requested schedule")
    source_time = schedule.attrs.get("fetched_utc")
    checked = _as_of(source_time) if source_time is not None else None
    if checked is None or checked > asof + pd.Timedelta(seconds=10):
        raise ValueError("Missing or future-dated schedule retrieval timestamp")
    if asof - checked > pd.Timedelta(minutes=30):
        raise ValueError("Schedule is over 30 minutes old. Refresh before reviewing games.")
    historical = normalize_games(games)
    fixtures = normalize_games(schedule)
    original_ids = set(historical.game_id.astype(str))
    new = fixtures.loc[~fixtures.game_id.astype(str).str.replace(r"^espn-", "", regex=True).isin(original_ids)].copy()
    if new.empty:
        return pd.DataFrame(columns=BOARD_COLUMNS)
    if new.game_id.duplicated().any():
        raise ValueError("Duplicate scheduled event IDs")
    # Source-supplied future fixtures must be scheduled and scoreless.
    if new.completed.any() or new[["home_points", "away_points"]].notna().any().any():
        raise ValueError("Refuse pregame slate containing completed or scored fixtures")
    if (~new.game_id.astype(str).str.startswith("espn-")).any():
        raise ValueError("Schedule must have exact ESPN event IDs")
    combined = normalize_games(pd.concat([historical, new], ignore_index=True))
    forecasts, _ = walk_forward(combined)
    predictions = forecasts.loc[forecasts.game_id.isin(set(new.game_id.astype(str)))].copy()
    local = predictions.kickoff_utc.dt.tz_convert(CENTRAL)
    mask = (
        predictions.kickoff_utc.gt(asof)
        & local.dt.date.eq(asof.tz_convert(CENTRAL).date())
        & local.dt.hour.ge(int(evening_hour))
        & (~predictions.completed)
        & predictions.eligible_history
    )
    predictions = predictions.loc[mask].sort_values(["kickoff_utc", "game_id"]).copy()
    if predictions.empty:
        return pd.DataFrame(columns=BOARD_COLUMNS)
    # Optional market metadata is a RETRIEVAL-TIME UNVERIFIED ESPN snapshot;
    # it is never proof that an offer was executable or accurately timestamped.
    # Keep the ESPN reference available per unmatched game rather than
    # dropping all ESPN data once any independent bookmaker game is matched.
    lookup = {}
    for market,source in (
        (schedule.attrs.get("indicative_market"),"ESPN_REFERENCE"),
        (fresh_market,"INDEPENDENT_BOOK")
    ):
        if not isinstance(market,pd.DataFrame) or market.empty:
            continue
        required={"game_id","market_home_handicap","market_total","market_provider"}
        if not required.issubset(market.columns):
            raise ValueError(f"Malformed {source} market data; refusing ambiguous comparisons")
        if market.game_id.astype(str).duplicated().any():
            raise ValueError(f"Duplicate {source} market event IDs")
        # Independent book quotes supersede ESPN for only those game IDs.
        lookup.update(market.set_index("game_id").to_dict(orient="index"))
    ids_by_event = schedule.attrs.get("espn_event_team_ids",{})
    rows = []
    for _, p in predictions.iterrows():
        m = lookup.get(p.game_id, {})
        spread = pd.to_numeric(m.get("market_home_handicap"), errors="coerce")
        total = pd.to_numeric(m.get("market_total"), errors="coerce")
        model_margin = float(p.projected_home_margin)
        model_total = float(p.projected_total)
        origin = str(m.get("market_verification","NO MARKET DATA"))
        is_fresh = origin == "ODDS_API_FRESH"
        count = int(m.get("market_book_count",0) or 0) if origin.startswith("ODDS_API_") else 0
        confidence, color, reason = model_evidence_quality(
            int(p.home_sample),int(p.away_sample),
            float(p.margin_sigma),float(p.total_sigma),
            reference_home_handicap=spread if pd.notna(spread) else None)
        source_label = ("INDEPENDENT BOOK" if origin.startswith("ODDS_API_")
                        else "ESPN REFERENCE" if origin=="UNVERIFIED ESPN SCOREBOARD SNAPSHOT"
                        else "NO MARKET DATA")
        sim = simulate_preview(
            str(p.game_id),model_margin,model_total,
            float(p.margin_sigma),float(p.total_sigma),
            home_handicap=spread if pd.notna(spread) and is_fresh else None,
            market_total=total if pd.notna(total) and is_fresh else None)
        team_ids = ids_by_event.get(str(p.game_id), {})
        signs = []
        if int(p.home_sample) < 2 or int(p.away_sample) < 2:
            signs.append("LIMITED TEAM DATA")
        if pd.notna(spread) and abs(float(spread)) >= 21:
            signs.append("LARGE FAVORITE: 2025 MODEL WEAKNESS")
        if not is_fresh:
            signs.append("NOT A CURRENT EXECUTABLE SPORTSBOOK QUOTE")
        if pd.notna(spread) and origin=="UNVERIFIED ESPN SCOREBOARD SNAPSHOT":
            signs.append("ESPN INDICATIVE LINE ONLY")
        if pd.isna(spread):
            signs.append("NO SPREAD LINE")
        rows.append({
            "game_id": str(p.game_id), "kickoff_utc": p.kickoff_utc,
            "matchup": f"{p.away_team} @ {p.home_team}",
            "projected_away_score": round((model_total - model_margin)/2, 1),
            "projected_home_score": round((model_total + model_margin)/2, 1),
            "projected_home_margin": round(model_margin,1),
            "projected_total": round(model_total,1),
            "home_win_probability_pct": round(100*float(p.home_win_prob),1),
            "training_games": int(p.training_games),
            "home_sample": int(p.home_sample), "away_sample": int(p.away_sample),
            "market_home_handicap": round(float(spread),1) if pd.notna(spread) else None,
            "market_total": round(float(total),1) if pd.notna(total) else None,
            "spread_disagreement_points": round(model_margin+float(spread),1) if pd.notna(spread) else None,
            "total_disagreement_points": round(model_total-float(total),1) if pd.notna(total) else None,
            "market_provider": str(m.get("market_provider","NO SOURCE")),
            "market_verification": origin,
            "market_source_label": source_label,
            "market_book_count": count,
            "market_oldest_quote_minutes": m.get("market_oldest_quote_minutes"),
            "caution": " · ".join(signs),
            "decision": "PASS — NO VERIFIED POSITIVE EV",
            "home_team": str(p.home_team), "away_team": str(p.away_team),
            "home_espn_id": str(team_ids.get("home","")),
            "away_espn_id": str(team_ids.get("away","")),
            "margin_sigma": float(p.margin_sigma), "total_sigma":float(p.total_sigma),
            "research_confidence": confidence, "confidence_color":color,
            "confidence_reason": reason,
            "simulations":int(sim["simulations"]),
            "sim_home_win_pct":sim["home_win_pct"], "sim_away_win_pct":sim["away_win_pct"],
            "sim_home_cover_pct":sim["home_cover_pct"], "sim_over_pct":sim["over_pct"],
            "sim_margin_p10":sim["margin_p10"], "sim_margin_p90":sim["margin_p90"],
            "sim_total_p10":sim["total_p10"], "sim_total_p90":sim["total_p90"],
        })
    return pd.DataFrame(rows, columns=BOARD_COLUMNS)
