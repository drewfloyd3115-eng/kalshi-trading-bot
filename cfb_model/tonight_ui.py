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
    st.title("Tonight’s CFB")
    st.caption("Vegas vs. model · Simulations · Central Time · Research only")
    st.info("Market source and model evidence are two SEPARATE assessments. The 2025 score-only model trailed sportsbooks; none of these ratings verifies profitable odds. Injuries, starting QBs, weather and advanced efficiency are not yet modeled.")
    now=pd.Timestamp.now(tz="UTC")
    day=now.tz_convert(CENTRAL).date().isoformat()
    st.caption(f"Today: {now.tz_convert(CENTRAL).strftime('%a, %b %d')} · Only unstarted 5 PM+ Central kickoffs.")
    st.caption("Refresh uses the free ESPN schedule and, if configured, **one paid-quota Odds API request** for US sportsbook spreads. It does not submit trades.")
    if st.button("Refresh tonight’s games + Vegas spreads",key="cfb_tonight_refresh",
                 type="primary",use_container_width=True):
        for key in ("cfb_tonight_rows","cfb_tonight_at","cfb_tonight_error",
                    "cfb_tonight_vegas_error","cfb_tonight_vegas_diagnostics"):
            st.session_state.pop(key,None)
        try:
            games=st.session_state.get("cfb_games")
            if not isinstance(games,pd.DataFrame) or games.empty or not games.attrs.get("espn_team_ids"):
                with st.spinner("Loading historical FBS results..."):
                    games=fetch_public_years(2020,2026)
                st.session_state.cfb_games=games
            ids=games.attrs.get("espn_team_ids",{})
            if not ids:
                raise ValueError("Historical source does not contain verified FBS team IDs")
            with st.spinner("Loading remaining verified FBS kickoffs..."):
                schedule=fetch_upcoming_schedule(ids,days=1)
            fresh=None
            key=_vegas_key()
            if key:
                try:
                    with st.spinner("Fetching recent US sportsbook spread quotes (one Odds API request)..."):
                        odds,remaining=fetch_vegas_spreads(key)
                        fresh=match_fresh_spreads(schedule,odds)
                        diagnostics=explain_unmatched_vegas(schedule,odds)
                    st.session_state.cfb_tonight_quota=remaining
                    st.session_state.cfb_tonight_vegas_diagnostics=diagnostics
                except Exception as exc:
                    # A failed sportsbook request never blocks projections.
                    st.session_state.cfb_tonight_vegas_error=str(exc)
            else:
                st.session_state.cfb_tonight_vegas_error="ODDS_API_KEY not configured; live Vegas quotes unavailable"
            with st.spinner("Running 20,000 reproducible model simulations per game..."):
                board=tonight_slate(games,schedule,fresh_market=fresh)
            st.session_state.cfb_tonight_rows=board
            st.session_state.cfb_tonight_at=pd.Timestamp.now(tz="UTC")
            st.session_state.cfb_tonight_day=day
            st.session_state.cfb_tonight_snapshot=schedule.attrs.get("fetched_utc")
            st.session_state.cfb_tonight_missing_years=games.attrs.get("missing_seasons",[])
            st.session_state.cfb_tonight_fresh_count=0 if fresh is None else len(fresh)
        except Exception as exc:
            st.session_state.cfb_tonight_error=str(exc)
    if st.session_state.get("cfb_tonight_error"):
        st.error("Tonight’s pregame feed unavailable: "+st.session_state.cfb_tonight_error)
    if st.session_state.get("cfb_tonight_vegas_error"):
        st.warning("Vegas data: "+st.session_state.cfb_tonight_vegas_error)
    board=st.session_state.get("cfb_tonight_rows")
    fetched=st.session_state.get("cfb_tonight_at")
    if not isinstance(board,pd.DataFrame) or fetched is None:
        st.caption("Tap refresh to load tonight’s matchup cards.")
        return
    now=pd.Timestamp.now(tz="UTC")
    if st.session_state.get("cfb_tonight_day")!=now.tz_convert(CENTRAL).date().isoformat():
        st.warning("Old local date. Refresh for this evening’s fixtures.")
        return
    age=max(0,(now-pd.Timestamp(fetched)).total_seconds()/60)
    if board.empty:
        st.warning("No eligible future evening FBS games found. The source may be incomplete.")
        return
    active=board.loc[board.kickoff_utc>now].sort_values("kickoff_utc").copy()
    if active.empty:
        st.warning("Every cached kickoff has passed. Refresh for another slate.")
        return
    a,b=st.columns(2)
    a.metric("Remaining games",len(active))
    b.metric("Current book lines",sum(
        str(r.market_verification)=="ODDS_API_FRESH" and
        pd.notna(r.market_home_handicap) and
        age+float(r.market_oldest_quote_minutes or 0)<=15
        for _,r in active.iterrows()))
    st.caption(f"Refreshed {format_central(fetched)} · {age:.0f} minutes ago"
               + (f" · Odds API requests remaining: {st.session_state.cfb_tonight_quota}" if st.session_state.get("cfb_tonight_quota") else ""))
    if age>15:
        st.warning("Cached sportsbook prices are older than 15 minutes. They will only appear as labeled historical references; refresh before assessing current lines.")
    diagnostic=st.session_state.get("cfb_tonight_vegas_diagnostics",{})
    if isinstance(diagnostic,dict):
        st.caption("Odds API events returned: "+
                   str(diagnostic.get("events_returned","?"))+
                   " · Unmatched games explain their exclusions below. No further API call is used for diagnostics.")
    if st.session_state.get("cfb_tonight_missing_years"):
        st.caption("Historical coverage incomplete: "+", ".join(map(str,st.session_state.cfb_tonight_missing_years)))
    current=sum(str(r.market_verification)=="ODDS_API_FRESH" and
                pd.notna(r.market_home_handicap) and
                age+float(r.market_oldest_quote_minutes or 0)<=15 for _,r in active.iterrows())
    reference=sum(str(r.market_source_label)=="ESPN REFERENCE" and
                  pd.notna(r.market_home_handicap) for _,r in active.iterrows())
    older=sum(str(r.market_source_label)=="INDEPENDENT BOOK" and
              not (str(r.market_verification)=="ODDS_API_FRESH" and
                   age+float(r.market_oldest_quote_minutes or 0)<=15) and
              pd.notna(r.market_home_handicap) for _,r in active.iterrows())
    st.caption(f"Market coverage: {current} current sportsbook · {older} older sportsbook · "
               f"{reference} ESPN reference · {len(active)-current-older-reference} without a line. "
               "Source status does not determine model evidence quality.")
    st.markdown("### Matchups")
    for _,r in active.iterrows():
        # Each card is intentionally readable on a narrow iPhone screen.
        with st.container(border=True):
            st.caption(format_central(r.kickoff_utc))
            al,at,vs,ht,hl=st.columns([1,4,1,4,1])
            with al:_logo(r.away_espn_id)
            at.markdown(f"**{escape(str(r.away_team))}**")
            vs.markdown("**@**")
            ht.markdown(f"**{escape(str(r.home_team))}**")
            with hl:_logo(r.home_espn_id)
            quote_age=pd.to_numeric(r.market_oldest_quote_minutes,errors="coerce")
            total_age=age+float(quote_age) if pd.notna(quote_age) else float("inf")
            origin=str(r.market_verification)
            quoted=pd.notna(r.market_home_handicap)
            is_fresh=(origin=="ODDS_API_FRESH" and quoted and total_age<=15)
            book_reference=(origin in ("ODDS_API_FRESH","ODDS_API_OLDER_REFERENCE")
                            and quoted and not is_fresh and total_age<=180)
            espn_reference=(origin=="UNVERIFIED ESPN SCOREBOARD SNAPSHOT" and quoted)
            if is_fresh:
                line_label="VEGAS SPREAD · CURRENT SNAPSHOT"
            elif book_reference:
                line_label=f"BOOK REFERENCE · {total_age:.0f} MIN OLD"
            elif espn_reference:
                line_label="ESPN REFERENCE · UNVERIFIED"
            else:
                line_label="VEGAS SPREAD · UNAVAILABLE"
            left,right=st.columns(2)
            left.caption(line_label)
            if is_fresh or book_reference or espn_reference:
                left.markdown("**"+display_spread(r.home_team,r.away_team,r.market_home_handicap)+"**")
            else:
                left.markdown("**Unavailable**")
            right.caption("OUR MODEL SPREAD")
            right.markdown("**"+model_spread(r.home_team,r.away_team,r.projected_home_margin)+"**")
            if is_fresh:
                st.caption(str(r.market_provider)+" · "+
                           str(int(r.market_book_count))+" fresh book(s) · "+
                           f"Model-line difference {r.spread_disagreement_points:+.1f} pts")
            elif book_reference:
                st.caption(str(r.market_provider)+" · Older sportsbook reference only; "+
                           f"model-line difference {r.spread_disagreement_points:+.1f} pts. DO NOT treat as a live line.")
            elif espn_reference:
                st.caption(str(r.market_provider)+" · ESPN scoreboard snapshot; "+
                           "not an independently verified sportsbook price or actionable spread.")
            else:
                reason=diagnostic.get("per_game",{}).get(str(r.game_id)) if isinstance(diagnostic,dict) else None
                codes={
                    "NOT_IN_FEED_OR_TEAM_NAME_MISMATCH":"Event missing from Odds API or team names did not match ESPN aliases",
                    "KICKOFF_MISMATCH":"Odds API kickoff did not match the ESPN event",
                    "AMBIGUOUS_DUPLICATE_EVENTS":"Multiple sportsbook events matched; safely withheld",
                    "NO_SPREAD_MARKET_IN_API_RESPONSE":"No US spread market in the returned event",
                    "NO_USABLE_QUOTE_TIMESTAMP":"The feed did not provide a reliable market-update time",
                    "QUOTES_OVER_180_MIN_OLD_OR_FUTURE_DATED":"Returned quotes were too old or future-dated",
                    "QUOTES_OLDER_THAN_15_MIN":"Bookmaker updates are older than 15 minutes",
                    "SPREAD_OUTCOME_OR_SIGN_UNMATCHED":"Team outcome names or signed spread values failed validation",
                }
                st.caption("Line unavailable · "+codes.get(reason,"No safely matched sportsbook spread")+".")
            st.caption(f"Projected score: {r.away_team} {r.projected_away_score:.0f}  ·  {r.home_team} {r.projected_home_score:.0f}  |  Total {r.projected_total:.1f}")
            confidence=str(r.research_confidence)
            color=str(r.confidence_color)
            reason=str(r.confidence_reason)
            st.caption(f"Market source: {r.market_source_label} · "
                       +("fresh sportsbook quote" if is_fresh else
                         "not verified as a live executable quote"))
            _colored_reliability(confidence,color,reason)
            st.caption(f"SIMULATIONS · {int(r.simulations):,} draws · Illustrative Gaussian model")
            st.progress(float(r.sim_home_win_pct)/100,
                        text=f"Home win {r.sim_home_win_pct:.0f}% · Away win {r.sim_away_win_pct:.0f}%")
            if is_fresh and pd.notna(r.sim_home_cover_pct):
                st.caption(f"Home covers displayed spread: ≈{r.sim_home_cover_pct:.0f}%")
            with st.expander("Simulation range & market details"):
                st.write(f"Margin P10–P90 (home–away): {r.sim_margin_p10:+.1f} to {r.sim_margin_p90:+.1f} pts")
                st.write(f"Game total P10–P90: {r.sim_total_p10:.1f}–{r.sim_total_p90:.1f}")
                st.write("**Available factors:** historical scoring, opponent adjustments, venue, and model residual uncertainty.")
                st.write("**Missing factors:** injury reports, starting-quarterback status, weather, pace and efficiency data.")
                if is_fresh and pd.notna(r.sim_over_pct):
                    st.write(f"Total threshold: {r.market_total:.1f}; simulated over: ≈{r.sim_over_pct:.0f}% (not calibrated)")
                st.caption("Normal simulations omit discrete scoring and exact push probabilities. The 2025 model lost to sportsbook benchmarks.")
            st.caption("BETTING STATUS: PASS — no proven edge, settled contract verification or Kalshi execution price.")
    st.download_button("Export slate data (raw UTC)",active.to_csv(index=False).encode("utf-8"),
                       file_name="cfb_tonight_model_vegas_sims.csv",mime="text/csv",
                       key="cfb_tonight_export")
