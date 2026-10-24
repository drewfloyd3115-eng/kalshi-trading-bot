"""Reproducible preview simulations and conservative research-quality assessment.

Model input is historical FINAL scores only. Gaussian spread/total draws are
illustrative (no injury/weather/pace adjustments, no discrete push modeling).
NEVER equate the research-quality label or simulated outcome with positive EV.
"""
from __future__ import annotations
from hashlib import sha256
import numpy as np
import pandas as pd


def simulate_preview(game_id: str, home_margin: float, total: float,
                     margin_sigma: float, total_sigma: float,
                     home_handicap=None, market_total=None,
                     n: int = 20000) -> dict:
    if not game_id or not (1000 <= n <= 100000):
        raise ValueError("Invalid event or simulation count")
    nums=np.asarray([home_margin,total,margin_sigma,total_sigma],dtype=float)
    if not np.isfinite(nums).all() or margin_sigma <= 0 or total_sigma <= 0:
        raise ValueError("Model requires finite means and positive dispersions")
    seed=int.from_bytes(sha256(str(game_id).encode("utf-8")).digest()[:8],"little")
    rng=np.random.default_rng(seed)
    margins=rng.normal(float(home_margin),float(margin_sigma),n)
    totals=rng.normal(float(total),float(total_sigma),n)
    result={
        "simulations":n,
        "home_win_pct":round(100*float(np.mean(margins>0)),1),
        "away_win_pct":round(100*float(np.mean(margins<0)),1),
        "margin_p10":round(float(np.quantile(margins,.10)),1),
        "margin_p90":round(float(np.quantile(margins,.90)),1),
        "total_p10":round(float(np.quantile(totals,.10)),1),
        "total_p90":round(float(np.quantile(totals,.90)),1),
        "home_cover_pct":None,
        "over_pct":None,
    }
    if home_handicap is not None and pd.notna(home_handicap):
        if not np.isfinite(float(home_handicap)):
            raise ValueError("Nonfinite spread")
        result["home_cover_pct"]=round(100*float(np.mean(margins+float(home_handicap)>0)),1)
    if market_total is not None and pd.notna(market_total):
        if not np.isfinite(float(market_total)):
            raise ValueError("Nonfinite game total")
        result["over_pct"]=round(100*float(np.mean(totals>float(market_total))),1)
    return result


def research_confidence(home_sample: int, away_sample: int,
                        home_handicap=None, disagreement=None,
                        market_source: str = "UNAVAILABLE",
                        book_count: int = 0) -> tuple[str,str,str]:
    """Traffic-light data quality, NOT calibrated bet confidence.

    The 2025 scoreboard baseline was demonstrably less accurate than books;
    therefore this model cannot earn a HIGH/GREEN betting-confidence label.
    """
    if market_source != "ODDS_API_FRESH":
        return ("UNVERIFIED","neutral","No fresh independent sportsbook quote; injuries and weather not modeled")
    reasons=[]
    if home_sample < 3 or away_sample < 3:
        reasons.append("limited team sample")
    if home_handicap is not None and pd.notna(home_handicap) and abs(float(home_handicap))>=21:
        reasons.append("large favorite: known model weakness")
    if disagreement is not None and pd.notna(disagreement) and abs(float(disagreement))>=7:
        reasons.append("large disagreement: model historically trails the market")
    if book_count < 2:
        reasons.append("only one fresh sportsbook")
    if reasons:
        return ("LOW","red","; ".join(reasons)+"; injuries and weather not modeled")
    return ("CAUTIOUS","amber","Multiple fresh books and sufficient team results, but model is uncalibrated and excludes injuries/weather")
