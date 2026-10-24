"""Read-only model vs ESPN scoreboard comparison.

This module never infers executable odds, net EV, or buy recommendations from
a sportsbook spread or total. Quoted lines are OPTIONAL and may be unavailable.
"""
from __future__ import annotations

import pandas as pd

OUTPUT = [
    "game_id", "kickoff_utc", "matchup", "market_provider", "quote_age_minutes",
    "model_home_margin", "market_home_handicap",
    "model_minus_market_margin", "model_total", "market_total",
    "model_minus_market_total", "quality_status",
]


def discrepancy_table(predictions: pd.DataFrame, market: pd.DataFrame,
                      now=None, max_age_minutes: float = 30) -> pd.DataFrame:
    """Produce descriptive, not actionable, market disagreements for future games."""
    empty = pd.DataFrame(columns=OUTPUT)
    if not isinstance(predictions, pd.DataFrame) or predictions.empty:
        return empty
    if not isinstance(market, pd.DataFrame) or market.empty:
        return empty
    required = {
        "game_id", "market_home_handicap", "market_total",
        "market_observed_utc", "market_provider",
    }
    if not required.issubset(market.columns):
        raise ValueError("Missing market snapshot fields: " + ", ".join(sorted(required-set(market.columns))))
    needed = {"game_id", "home_team", "away_team", "kickoff_utc", "completed",
              "eligible_history", "projected_home_margin", "projected_total"}
    if not needed.issubset(predictions.columns):
        raise ValueError("Missing model forecast fields")
    if max_age_minutes <= 0 or max_age_minutes > 120:
        raise ValueError("Quote age threshold must be from 0 to 120 minutes")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        raise ValueError("Current timestamp must be timezone-aware")
    current = current.tz_convert("UTC")
    p = predictions.copy()
    p["game_id"] = p.game_id.astype(str)
    p["kickoff_utc"] = pd.to_datetime(p.kickoff_utc, utc=True, errors="coerce")
    p = p.loc[(p.kickoff_utc > current) & (~p.completed.astype(bool)) &
              p.eligible_history.astype(bool)].copy()
    if p.empty:
        return empty
    m = market.copy()
    m["game_id"] = m.game_id.astype(str)
    if m.game_id.duplicated().any():
        raise ValueError("Duplicate indicative market event IDs")
    m["market_observed_utc"] = pd.to_datetime(m.market_observed_utc, utc=True, errors="coerce")
    if m.market_observed_utc.isna().any():
        raise ValueError("Missing or invalid observed-at timestamp")
    combined = p.merge(m, on="game_id", how="inner", validate="one_to_one")
    if combined.empty:
        return empty
    if (combined.market_observed_utc > current + pd.Timedelta(seconds=10)).any():
        raise ValueError("Market snapshot cannot be in the future")
    rows = []
    for _, r in combined.iterrows():
        age = (current-r.market_observed_utc).total_seconds()/60
        spread = pd.to_numeric(r.market_home_handicap, errors="coerce")
        total = pd.to_numeric(r.market_total, errors="coerce")
        fair_margin = float(r.projected_home_margin)
        fair_total = float(r.projected_total)
        has_line = pd.notna(spread) or pd.notna(total)
        status = ("STALE — NO SIGNAL" if age > max_age_minutes else
                  "INDICATIVE ONLY — NOT VERIFIED EV" if has_line else
                  "NO QUOTED LINES")
        rows.append({
            "game_id": r.game_id,
            "kickoff_utc": r.kickoff_utc,
            "matchup": f"{r.away_team} @ {r.home_team}",
            "market_provider": str(r.market_provider),
            "quote_age_minutes": round(age, 1),
            "model_home_margin": round(fair_margin, 2),
            "market_home_handicap": round(float(spread), 2) if pd.notna(spread) else None,
            "model_minus_market_margin": round(fair_margin + float(spread), 2) if pd.notna(spread) else None,
            "model_total": round(fair_total, 2),
            "market_total": round(float(total), 2) if pd.notna(total) else None,
            "model_minus_market_total": round(fair_total-float(total), 2) if pd.notna(total) else None,
            "quality_status": status,
        })
    return pd.DataFrame(rows, columns=OUTPUT).sort_values("kickoff_utc").reset_index(drop=True)
