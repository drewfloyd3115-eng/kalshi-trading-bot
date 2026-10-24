"""Descriptive audit of model weaknesses on paired historical CFB games.

Never turns observed closing lines into past executable bet prices. All results
come from the model/book/actual triples for identical completed fixtures, not
from unmatched aggregate samples. No training, wager selection or tuning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = {
    "game_id","week","away_team","home_team","provider",
    "actual_margin","projected_home_margin","market_home_margin",
    "actual_total","projected_total","total",
}


def _summary(group: pd.DataFrame, metric: str) -> dict:
    actual, prediction, book = (
        ("actual_margin","projected_home_margin","market_home_margin")
        if metric=="spread" else
        ("actual_total","projected_total","total")
    )
    group = group.loc[group[[actual,prediction,book]].notna().all(axis=1)]
    if group.empty:
        return {"games": 0, "model_mae": None, "book_mae": None,
                "book_advantage_points": None, "model_bias_points": None}
    model_error = group[actual] - group[prediction]
    book_error = group[actual] - group[book]
    return {
        "games": int(len(group)),
        "model_mae": round(float(model_error.abs().mean()),2),
        "book_mae": round(float(book_error.abs().mean()),2),
        # Positive = book had lower error.
        "book_advantage_points": round(float(model_error.abs().mean()-book_error.abs().mean()),2),
        # Positive = model overpredicts, negative = underpredicts.
        "model_bias_points": round(float((group[prediction]-group[actual]).mean()),2),
    }


def _table(groups, metric: str, key: str) -> pd.DataFrame:
    entries=[]
    for name, rows in groups:
        if rows.empty:
            continue
        entries.append({key: str(name), **_summary(rows,metric)})
    return pd.DataFrame(entries, columns=[key,"games","model_mae","book_mae",
                                          "book_advantage_points","model_bias_points"])


def market_failure_audit(paired: pd.DataFrame) -> dict:
    """Pure post-hoc diagnostic tables for model improvement planning.

    Positive 'book_advantage_points' means sportsbook predictions were better.
    Group definitions are fixed before looking at outcomes. No bets or
    purported out-of-sample model recalibrations are generated.
    """
    if not isinstance(paired,pd.DataFrame) or paired.empty:
        raise ValueError("A nonempty paired historical model-market CSV is required")
    missing=REQUIRED - set(paired.columns)
    if missing:
        raise ValueError("Missing historical audit columns: " + ", ".join(sorted(missing)))
    source=paired.copy()
    source["game_id"]=source.game_id.astype(str)
    if source.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs are not acceptable for a paired audit")
    for column in ("week","actual_margin","projected_home_margin","market_home_margin",
                   "actual_total","projected_total","total"):
        source[column]=pd.to_numeric(source[column],errors="coerce")
    if source.actual_margin.isna().any() or source.projected_home_margin.isna().any():
        raise ValueError("Invalid actual or projected margin in paired game data")
    if source.week.isna().any() or ~source.week.between(0,20).all():
        raise ValueError("Invalid schedule week")
    source["spread_book_abs"]=source.market_home_margin.abs()
    source["model_spread_abs"]=source.projected_home_margin.abs()
    source["margin_disagreement"]=(
        source.projected_home_margin-source.market_home_margin).abs()
    groups_week=[
        ("Weeks 1–4",source.loc[source.week.between(1,4)]),
        ("Weeks 5–8",source.loc[source.week.between(5,8)]),
        ("Weeks 9–14",source.loc[source.week.between(9,14)]),
        ("Week 15+",source.loc[source.week>=15]),
    ]
    bins_fav = [
        ("Under 3",0,3),("3–6.5",3,7),("7–13.5",7,14),
        ("14–20.5",14,21),("21+",21,float("inf")),
    ]
    groups_fav=[(name,source.loc[(source.spread_book_abs>=lo) &
                                   (source.spread_book_abs<hi)])
                for name,lo,hi in bins_fav]
    groups_disagreement = [
        ("Under 3",0,3),("3–6.5",3,7),("7–13.5",7,14),("14+",14,float("inf")),
    ]
    groups_disc=[(name,source.loc[(source.margin_disagreement>=lo) &
                                     (source.margin_disagreement<hi)])
                  for name,lo,hi in groups_disagreement]
    groups_total = [
        ("Under 45",0,45),("45–49.5",45,50),("50–54.5",50,55),
        ("55–59.5",55,60),("60+",60,float("inf")),
    ]
    total_groups=[(name,source.loc[(source.total>=lo)&(source.total<hi)])
                  for name,lo,hi in groups_total]
    failures=source.loc[source.market_home_margin.notna()].copy()
    failures["model_error_points"]=(failures.actual_margin-failures.projected_home_margin).abs()
    failures["book_error_points"]=(failures.actual_margin-failures.market_home_margin).abs()
    failures["book_advantage_points"]=(failures.model_error_points-failures.book_error_points).round(2)
    failures=failures.sort_values(["book_advantage_points","game_id"],
                                   ascending=[False,True]).head(15)
    failures=failures[["week","away_team","home_team","actual_margin",
                       "projected_home_margin","market_home_margin",
                       "model_error_points","book_error_points","book_advantage_points"]]
    paired_spread=source.loc[source.market_home_margin.notna()]
    paired_total=source.loc[source.total.notna()]
    providers=sorted({str(v) for v in source.provider.dropna()})
    return {
        "summary":{
            "paired_games":len(source),
            "provider_names":providers,
            "spread":_summary(paired_spread,"spread"),
            "total":_summary(paired_total,"total"),
            "important_limit":("Descriptive holdout audit. 2025 is now exposed to "
                               "model development decisions and is not a fresh "
                               "confirmation set. Closing lines are not "
                               "historical executable Kalshi quotes.")
        },
        "by_week_spread": _table(groups_week,"spread","season_phase"),
        "by_favorite_spread": _table(groups_fav,"spread","book_favorite_points"),
        "by_disagreement_spread": _table(groups_disc,"spread","margin_disagreement"),
        "by_total_band": _table(total_groups,"total","book_total_points"),
        "largest_spread_failures": failures.reset_index(drop=True),
    }
