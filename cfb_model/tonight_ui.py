"""Mobile-first CFB matchup cards with validated ESPN team logos and Vegas quotes.

UI labels are intentionally conservative: this score-only model loses to
historical sportsbooks and cannot have a confirmed profitable/green confidence.
"""
from __future__ import annotations

from html import escape
import os
import re
import pandas as pd
import streamlit as st

from .data import fetch_public_years
from .schedule import fetch_upcoming_schedule
from .tonight import tonight_slate
from .vegas import fetch_vegas_spreads, match_fresh_spreads, explain_unmatched_vegas
from ui_timezone import format_central, CENTRAL


def _vegas_key():
    try:
        return st.secrets.get("ODDS_API_KEY","") or os.getenv("ODDS_API_KEY","")
    except (KeyError,FileNotFoundError):
        return os.getenv("ODDS_API_KEY","")


def logo_url(team_id):
    """Only numeric IDs verified from ESPN's own exact-id FBS schedule."""
    value=str(team_id or "").strip()
    if not re.fullmatch(r"[0-9]{1,7}",value):
        return None
    return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{value}.png"


def display_spread(home: str,away: str,home_handicap) -> str:
    """A negative HOME handicap favors home; positive favors away."""
    value=pd.to_numeric(home_handicap,errors="coerce")
    if pd.isna(value):
        return "Unavailable"
    if abs(float(value))<0.01:
        return "Pick’em"
    favorite=home if float(value)<0 else away
    return f"{favorite} -{abs(float(value)):.1f}"


def model_spread(home: str,away: str,home_margin: float) -> str:
    # Forecast is a home-minus-away margin, the *opposite sign* of handicap.
    return display_spread(home,away,-home_margin)


def _logo(team_id: str):
    src=logo_url(team_id)
    if src:
        st.image(src,width=46)
    else:
        st.markdown("🏈")


def _colored_reliability(label: str, color: str, reason: str):
    palette={"amber":("#B45309","#FEF3C7"),"red":("#B91C1C","#FEE2E2"),
             "neutral":("#475569","#E2E8F0")}
    fg,bg=palette.get(color,palette["neutral"])
    st.markdown(
        f'<div style="border-radius:8px;padding:8px 10px;background:{bg};'
        f'color:{fg};font-size:0.88rem">'
        f'<strong>Model evidence: {escape(label)}</strong>'
        f'<div style="font-size:0.75rem;margin-top:3px">{escape(reason)}</div>'
        '</div>',unsafe_allow_html=True)


def render_tonight_ui():
    """A compact mobile-first, read-only game-day board.

    All controls below use session state. Only the Refresh button performs
    network requests, consumes Odds API quota and recalculates simulations.
    """
    from .card_design import card_view, market_view, game_card_html, summary_html

    st.markdown('<div class="tl-page-kicker">GAME CENTER <span>●</span> COLLEGE FOOTBALL</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="tl-page-title">Tonight’s Games</h1>', unsafe_allow_html=True)
    st.caption("Vegas vs model · 20,000 simulations · All times Central")
    now=pd.Timestamp.now(tz="UTC")
    day=now.tz_convert(CENTRAL).date().isoformat()

    if st.button("↻  Refresh matchups & lines",key="cfb_tonight_refresh",
                 type="primary",use_container_width=True):
        for key in ("cfb_tonight_rows","cfb_tonight_at","cfb_tonight_error",
                    "cfb_tonight_vegas_error","cfb_tonight_vegas_diagnostics"):
            st.session_state.pop(key,None)
        st.session_state.pop("cfb_tonight_quota",None)
        try:
            games=st.session_state.get("cfb_games")
            if not isinstance(games,pd.DataFrame) or games.empty or not games.attrs.get("espn_team_ids"):
                with st.spinner("Loading verified FBS historical results..."):
                    games=fetch_public_years(2020,2026)
                st.session_state.cfb_games=games
            ids=games.attrs.get("espn_team_ids",{})
            if not ids:
                raise ValueError("Historical source does not contain verified FBS team IDs")
            with st.spinner("Loading tonight’s remaining games..."):
                schedule=fetch_upcoming_schedule(ids,days=1)
            fresh=None
            key=_vegas_key()
            if key:
                try:
                    with st.spinner("Checking US sportsbook spreads (one Odds API request)..."):
                        odds,remaining=fetch_vegas_spreads(key)
                        fresh=match_fresh_spreads(schedule,odds)
                        diagnostics=explain_unmatched_vegas(schedule,odds)
                    st.session_state.cfb_tonight_quota=remaining
                    st.session_state.cfb_tonight_vegas_diagnostics=diagnostics
                except Exception as exc:
                    # Preserve app functionality if Odds API quota is exhausted.
                    st.session_state.cfb_tonight_vegas_error=str(exc)
            else:
                st.session_state.cfb_tonight_vegas_error="ODDS_API_KEY is not configured."
            with st.spinner("Building score forecasts and simulations..."):
                board=tonight_slate(games,schedule,fresh_market=fresh)
            st.session_state.cfb_tonight_rows=board
            st.session_state.cfb_tonight_at=pd.Timestamp.now(tz="UTC")
            st.session_state.cfb_tonight_day=day
            st.session_state.cfb_tonight_snapshot=schedule.attrs.get("fetched_utc")
            st.session_state.cfb_tonight_missing_years=games.attrs.get("missing_seasons",[])
        except Exception as exc:
            st.session_state.cfb_tonight_error=str(exc)

    if st.session_state.get("cfb_tonight_error"):
        st.error("Unable to load the game slate: "+str(st.session_state.cfb_tonight_error))
    board=st.session_state.get("cfb_tonight_rows")
    fetched=st.session_state.get("cfb_tonight_at")
    if not isinstance(board,pd.DataFrame) or fetched is None:
        st.markdown('<div class="tl-empty"><strong>Ready for game day</strong><p>Tap Refresh to load unstarted FBS games, the latest available sportsbook spreads, and our simulations. One refresh may consume Odds API credits.</p></div>',unsafe_allow_html=True)
        st.caption("Research only. No automatic wagers, simulated profitability claims, or background scans.")
        return
    if st.session_state.get("cfb_tonight_day")!=now.tz_convert(CENTRAL).date().isoformat():
        st.warning("This board belongs to a different Central calendar day. Refresh.")
        return
    age=max(0,(pd.Timestamp.now(tz="UTC")-pd.Timestamp(fetched)).total_seconds()/60)
    if board.empty:
        st.info("No eligible unstarted games at or after 5 PM Central in the returned schedule.")
        return
    active=board.loc[board.kickoff_utc>now].sort_values("kickoff_utc").copy()
    if active.empty:
        st.info("All saved game kickoffs have passed. Refresh on another game day.")
        return

    views=[card_view(r,age) for _,r in active.iterrows()]
    line_count=sum(v["market"]["show"] for v in views)
    gap_count=sum(v["spread_gap"] is not None and v["spread_gap"]>=7 for v in views)
    st.markdown(summary_html(len(active),line_count,gap_count,format_central(fetched)),unsafe_allow_html=True)

    if age>15:
        st.warning("Cached sportsbook quotes have aged. Old prices are shown as references, not current lines.")
    if st.session_state.get("cfb_tonight_vegas_error"):
        st.caption("Odds feed: "+str(st.session_state.cfb_tonight_vegas_error))
    missing_years=st.session_state.get("cfb_tonight_missing_years") or []
    if missing_years:
        st.caption("Historical coverage gap: "+", ".join(map(str,missing_years)))
    st.markdown('<div class="tl-section-label">MATCHUPS</div>',unsafe_allow_html=True)

    filter_name=st.segmented_control("Games filter",["All","Lines available","7+ pt gaps"],
                                      default="All",key="tl_game_filter")
    sort_name=st.selectbox("Sort",["Kickoff time","Largest spread difference"],
                           key="tl_sort",label_visibility="collapsed")
    indexed=[(i, r, views[i]) for i,(_,r) in enumerate(active.iterrows())]
    if filter_name=="Lines available":
        indexed=[x for x in indexed if x[2]["market"]["show"]]
    elif filter_name=="7+ pt gaps":
        indexed=[x for x in indexed if x[2]["spread_gap"] is not None and x[2]["spread_gap"]>=7]
    if sort_name=="Largest spread difference":
        indexed.sort(key=lambda x:(x[2]["spread_gap"] is not None,
                                   x[2]["spread_gap"] or 0),reverse=True)
    if not indexed:
        st.info("No games match this filter. Try All games.")
    for i,row,view in indexed:
        st.markdown(game_card_html(row,age),unsafe_allow_html=True)
        with st.expander("Details · simulation ranges and data checks",expanded=False):
            st.caption("These probabilities come from a score-only Gaussian model, not a validated betting market model.")
            c1,c2=st.columns(2)
            c1.metric("Margin 10–90%",f"{float(row.sim_margin_p10):+.1f} to {float(row.sim_margin_p90):+.1f}")
            c2.metric("Total 10–90%",f"{float(row.sim_total_p10):.1f} to {float(row.sim_total_p90):.1f}")
            st.caption("Model evidence: "+str(row.confidence_reason))
            st.caption("Market: "+view["market"]["detail"])
            st.caption("Important inputs missing: injury reports, starting QBs, weather, pace and opponent-adjusted play-by-play efficiency.")
            if view["market"]["status"]=="CURRENT" and pd.notna(row.sim_home_cover_pct):
                st.metric("Illustrative home cover frequency",f"{float(row.sim_home_cover_pct):.1f}%")
            if view["market"]["status"]=="CURRENT" and pd.notna(row.sim_over_pct):
                st.metric("Illustrative over frequency",f"{float(row.sim_over_pct):.1f}%")
            diagnosis=st.session_state.get("cfb_tonight_vegas_diagnostics") or {}
            reason=diagnosis.get("per_game",{}).get(str(row.game_id)) if isinstance(diagnosis,dict) else None
            if reason and view["market"]["status"] in ("ESPN","MISSING"):
                st.caption("Book matching diagnostic: "+str(reason))
            st.caption("Trading status: PASS. No verified Kalshi entry price, contract settlement check, or demonstrated positive expected value.")
    with st.expander("About this model & downloads",expanded=False):
        st.caption("The 2025 benchmark found the baseline less accurate than sportsbooks on spreads and totals. Line differences are not proven edges, and badges describe only model evidence and quote provenance.")
        st.caption("Quotes are only requested on Refresh. No live trading occurs.")
        if st.session_state.get("cfb_tonight_quota") is not None:
            st.caption("Odds API requests remaining (provider estimate): "+str(st.session_state.cfb_tonight_quota))
        st.download_button("Download raw research CSV (UTC)",active.to_csv(index=False).encode("utf-8"),
                           file_name="cfb_tonight_research.csv",mime="text/csv",key="cfb_tonight_export")
