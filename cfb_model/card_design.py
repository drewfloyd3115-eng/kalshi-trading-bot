"""Pure, secure presentation helpers for the compact CFB dashboard.

Never calls remote APIs, places orders, assigns betting confidence, or
manufactures sportsbook prices. This is a display-only transformation.
"""
from __future__ import annotations

from html import escape
import math
import re

import pandas as pd

from ui_timezone import format_central


def _text(value):
    return escape(str(value), quote=True)


def _float(value):
    try:
        number=float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _team_image(team_id: str, team_name: str) -> str:
    """ESPN-issued IDs only; any other ID displays a fallback icon."""
    tid=str(team_id or "").strip()
    alt=_text(f"{team_name} logo")
    if not re.fullmatch(r"[0-9]{1,7}",tid):
        return '<div class="tl-logo-placeholder" aria-hidden="true">🏈</div>'
    return (f'<img class="tl-logo" loading="lazy" alt="{alt}" '
            f'src="https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png"/>')


def spread_label(home, away, signed_home_handicap) -> str:
    h=_float(signed_home_handicap)
    if h is None:
        return "No line"
    if abs(h)<.01:
        return "Pick’em"
    return f"{home if h<0 else away} -{abs(h):.1f}"


def market_view(row, cache_age_minutes: float) -> dict:
    """Distinguish current independent quote, aged quote, ESPN, and missing."""
    origin=str(row.get("market_verification") or "")
    line=_float(row.get("market_home_handicap"))
    quote_age=_float(row.get("market_oldest_quote_minutes"))
    current_age=max(0., float(cache_age_minutes))
    age=(current_age+quote_age) if quote_age is not None else float("inf")
    if line is not None and origin=="ODDS_API_FRESH" and age<=15:
        return {"status":"CURRENT", "label":"Current sportsbook",
                "detail":f"{int(row.get('market_book_count') or 1)} book(s) · updated within 15m",
                "source":"independent","age":age,"show":True}
    if line is not None and origin.startswith("ODDS_API_") and age<=180:
        return {"status":"OLDER", "label":"Older sportsbook line",
                "detail":f"Updated {age:.0f} minutes ago · reference only",
                "source":"older","age":age,"show":True}
    if line is not None and origin=="UNVERIFIED ESPN SCOREBOARD SNAPSHOT":
        return {"status":"ESPN", "label":"ESPN reference",
                "detail":"Indicative only · not a current sportsbook quote",
                "source":"reference","age":None,"show":True}
    return {"status":"MISSING","label":"No matched sportsbook line",
            "detail":"Market price unavailable; model still shown",
            "source":"missing","age":None,"show":False}


def card_view(row, age_minutes: float) -> dict:
    """One simple, auditable view model per game, with no EV inference."""
    market=market_view(row,age_minutes)
    home=str(row.get("home_team") or "Home")
    away=str(row.get("away_team") or "Away")
    margin=_float(row.get("projected_home_margin"))
    if margin is None:
        raise ValueError("A model spread requires a finite projected margin")
    model=spread_label(home,away,-margin)
    vegas=spread_label(home,away,row.get("market_home_handicap")) if market["show"] else "Not available"
    market_home=_float(row.get("market_home_handicap"))
    gap=abs(margin+market_home) if market["show"] and market_home is not None else None
    grade=str(row.get("research_confidence") or "INSUFFICIENT").upper()
    color=str(row.get("confidence_color") or "neutral")
    if grade not in ("PRELIMINARY","LOW","INSUFFICIENT"):
        grade="INSUFFICIENT"
        color="neutral"
    if color not in ("amber","red","neutral"):
        color="neutral"
    home_sim=_float(row.get("sim_home_win_pct"))
    away_sim=_float(row.get("sim_away_win_pct"))
    if home_sim is None or away_sim is None or not(0<=home_sim<=100 and 0<=away_sim<=100):
        home_sim=away_sim=None
    return {
        "market":market, "home":home, "away":away,
        "home_logo":_team_image(row.get("home_espn_id"),home),
        "away_logo":_team_image(row.get("away_espn_id"),away),
        "market_spread":vegas, "model_spread":model,"spread_gap":gap,
        "home_sim":home_sim,"away_sim":away_sim,
        "grade":grade,"grade_color":color,
        "grade_reason":str(row.get("confidence_reason") or "Historical-model quality only"),
        "provider":str(row.get("market_provider") or "Unknown provider"),
        "kickoff":format_central(row.get("kickoff_utc")),
        "home_score":_float(row.get("projected_home_score")),
        "away_score":_float(row.get("projected_away_score")),
        "total":_float(row.get("projected_total")),
        "sim_count":int(row.get("simulations") or 0)
    }


def _pct(value):
    return "—" if value is None else f"{value:.0f}%"


def game_card_html(row, age_minutes: float) -> str:
    v=card_view(row,age_minutes)
    m=v["market"]
    status=m["status"].lower()
    line_gap="No spread comparison" if v["spread_gap"] is None else f'{v["spread_gap"]:.1f} pts apart'
    if v["spread_gap"] is not None and m["status"]!="CURRENT":
        line_gap+=" · reference only"
    away_pct=v["away_sim"]
    home_pct=v["home_sim"]
    away_width=f"{max(0,min(100,away_pct)):.1f}%" if away_pct is not None else "50%"
    hscore="—" if v["home_score"] is None else f'{v["home_score"]:.0f}'
    ascore="—" if v["away_score"] is None else f'{v["away_score"]:.0f}'
    total="—" if v["total"] is None else f'{v["total"]:.1f}'
    return f"""
<div class="tl-card" role="group" aria-label="{_text(v['away'])} at {_text(v['home'])}">
 <div class="tl-card-kickoff">{_text(v['kickoff'])} <span class="tl-chip source-{status}">{_text(m['label'])}</span></div>
 <div class="tl-teams">
  <div class="tl-team">{v['away_logo']}<strong>{_text(v['away'])}</strong><small>AWAY</small></div>
  <div class="tl-vs">@</div>
  <div class="tl-team">{v['home_logo']}<strong>{_text(v['home'])}</strong><small>HOME</small></div>
 </div>
 <div class="tl-linegrid">
  <div class="tl-line"><span>MARKET SPREAD</span><strong>{_text(v['market_spread'])}</strong><small>{_text(v['provider'] if m['show'] else m['detail'])}</small></div>
  <div class="tl-line"><span>OUR MODEL</span><strong>{_text(v['model_spread'])}</strong><small>Score-only projection</small></div>
 </div>
 <div class="tl-gap"><strong>{_text(line_gap)}</strong><span>Line disagreement, not betting edge</span></div>
 <div class="tl-predicted">Projected score <strong>{_text(v['away'])} {ascore} · {_text(v['home'])} {hscore}</strong><span>Game total {total}</span></div>
 <div class="tl-sim-head"><span>SIMULATED WIN CHANCE</span><small>{v['sim_count']:,} draws</small></div>
 <div class="tl-sim-sides"><strong>{_pct(away_pct)} {_text(v['away'])}</strong><strong>{_text(v['home'])} {_pct(home_pct)}</strong></div>
 <div class="tl-prob-track"><div class="tl-prob-away" style="width:{away_width}"></div></div>
 <div class="tl-card-bottom">
  <span class="tl-chip model-{v['grade_color']}">Model evidence: {_text(v['grade'].title())}</span>
  <span class="tl-research-status">Research only · no verified bet</span>
 </div>
</div>
"""


def summary_html(total: int, lines: int, gap_count: int, refreshed: str) -> str:
    """Compact single-line visual hierarchy; no performance recommendations."""
    return (f'<div class="tl-summary">'
            f'<div><small>UPCOMING</small><strong>{int(total)}</strong></div>'
            f'<div><small>LINES SHOWN</small><strong>{int(lines)}</strong></div>'
            f'<div><small>GAPS ≥7 PT</small><strong>{int(gap_count)}</strong></div>'
            f'</div><div class="tl-refresh-note">Last refresh: {_text(refreshed)} · Central Time</div>')
