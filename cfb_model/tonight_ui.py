"""One-tap Central Time evening CFB screen; read-only research."""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from .data import fetch_public_years
from .schedule import fetch_upcoming_schedule
from .tonight import tonight_slate
from ui_timezone import format_central, display_central_columns, CENTRAL


def render_tonight_ui():
    st.title("Tonight's CFB")
    st.caption("Central Time (CDT/CST) · Read-only football research · No live orders")
    st.warning("2025 audit: our baseline lost to the sportsbook on spreads (13.32 vs 11.87 points MAE) and totals (12.77 vs 12.39). A model discrepancy is NOT a profitable bet. No Kalshi trades are authorized here.")
    now = pd.Timestamp.now(tz="UTC")
    today = now.tz_convert(CENTRAL).strftime("%A, %B %d")
    st.caption(f"Now: {format_central(now)} · Tonight = {today}, kickoffs from 5:00 PM Central onward.")
    st.caption("One tap uses FREE public game results and ESPN's read-only schedule. It does not consume CFBD or Odds API credits. Last updated data must be refreshed before game lock.")
    if st.button("Refresh tonight's remaining FBS games",key="cfb_tonight_refresh",type="primary",use_container_width=True):
        for key in ("cfb_tonight_rows","cfb_tonight_at","cfb_tonight_error"):
            st.session_state.pop(key,None)
        try:
            games = st.session_state.get("cfb_games")
            if not isinstance(games,pd.DataFrame) or games.empty or not games.attrs.get("espn_team_ids"):
                with st.spinner("Loading actual FBS scores and ESPN team IDs..."):
                    games=fetch_public_years(2020,2026)
                st.session_state.cfb_games=games
            team_ids=games.attrs.get("espn_team_ids",{})
            if not team_ids:
                raise ValueError("No verified team ID history; reload public FBS scores")
            with st.spinner("Checking future games and calculating pregame projections..."):
                schedule=fetch_upcoming_schedule(team_ids,days=1)
                board=tonight_slate(games,schedule)
            st.session_state.cfb_tonight_rows=board
            st.session_state.cfb_tonight_at=pd.Timestamp.now(tz="UTC")
            st.session_state.cfb_tonight_day=now.tz_convert(CENTRAL).date().isoformat()
            st.session_state.cfb_tonight_snapshot=schedule.attrs.get("fetched_utc")
            if board.empty:
                st.info("No eligible unstarted FBS games after 5 PM Central today in the retrieved schedule. This does not guarantee the absence of games.")
            else:
                st.success(f"Found {len(board)} remaining evening matchups. Predictions are provisional, not verified betting edges.")
            missing=games.attrs.get("missing_seasons",[])
            if missing:
                st.warning(f"Historical scores missing seasons: {', '.join(map(str,missing))}. Model limitations remain.")
        except Exception as exc:
            st.session_state.cfb_tonight_error=str(exc)
            st.error(f"Evening slate unavailable: {exc}. No game or betting signal will be invented.")
    if st.session_state.get("cfb_tonight_error"):
        st.warning(st.session_state.cfb_tonight_error)
    board=st.session_state.get("cfb_tonight_rows")
    fetched=st.session_state.get("cfb_tonight_at")
    if not isinstance(board,pd.DataFrame) or fetched is None:
        st.info("Tap the refresh button to load this evening's games. Saved historical benchmark results in the separate CFB Model tab are unchanged.")
        return
    if st.session_state.get("cfb_tonight_day")!=now.tz_convert(CENTRAL).date().isoformat():
        st.warning("This board is from a different Central calendar day. Refresh to use it.")
        return
    age=(pd.Timestamp.now(tz="UTC")-pd.Timestamp(fetched)).total_seconds()/60
    st.caption(f"Last retrieved: {format_central(fetched)} · Age: {age:.0f} min · ESPN schedule: {format_central(st.session_state.get('cfb_tonight_snapshot'))}")
    if age>30:
        st.warning("STALE — data is older than 30 minutes. Refresh before evaluating any remaining game.")
    if board.empty:
        st.info("No remaining eligible evening games were returned. The source may be incomplete.")
        return
    remaining=board.loc[board.kickoff_utc>pd.Timestamp.now(tz="UTC")].copy()
    if remaining.empty:
        st.warning("All cached evening kickoffs have passed. No pregame markets can be evaluated.")
        return
    st.subheader("Evening slate overview")
    cols=["kickoff_utc","matchup","projected_away_score","projected_home_score",
          "home_win_probability_pct","market_home_handicap","market_total","caution","decision"]
    st.dataframe(display_central_columns(remaining[cols]),hide_index=True,use_container_width=True)
    st.download_button("Export full tonight research CSV (UTC)",remaining.to_csv(index=False).encode("utf-8"),
                       file_name="cfb_tonight_research.csv",mime="text/csv",key="cfb_tonight_export")
    st.subheader("Game deep dive")
    labels={str(r.game_id):f"{r.matchup} · {format_central(r.kickoff_utc)}"
            for _,r in remaining.iterrows()}
    chosen=st.selectbox("Select remaining matchup",list(labels),format_func=lambda x:labels[x],key="cfb_tonight_game")
    r=remaining.loc[remaining.game_id.astype(str)==chosen].iloc[0]
    a,b=st.columns(2)
    a.metric("Projected away",f"{r.projected_away_score:.1f}")
    b.metric("Projected home",f"{r.projected_home_score:.1f}")
    a,b=st.columns(2)
    a.metric("Home win model",f"{r.home_win_probability_pct:.1f}%")
    b.metric("Model game total",f"{r.projected_total:.1f}")
    if pd.notna(r.market_home_handicap) or pd.notna(r.market_total):
        st.caption(f"Indicative ESPN book provider: {r.market_provider}. These are NOT executable Kalshi or sportsbook offers.")
        if pd.notna(r.market_home_handicap):
            st.write(f"Home-team market handicap: {r.market_home_handicap:+.1f}; model home margin: {r.projected_home_margin:+.1f}; directional disagreement: {r.spread_disagreement_points:+.1f} points.")
        if pd.notna(r.market_total):
            st.write(f"Market total: {r.market_total:.1f}; model total: {r.projected_total:.1f}; disagreement: {r.total_disagreement_points:+.1f} points.")
    else:
        st.info("ESPN supplied no usable betting line for this matchup. No market comparison available.")
    st.write("**Data cautions:** "+r.caution)
    st.error("PASS — uncalibrated forecast; no verified contract rules, executable Kalshi price, fee or positive expected value.")
    st.caption("For manual Kalshi quote inspection and specific contract rules, use CFB Model. This quick view never places an order.")
