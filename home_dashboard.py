"""A focused, quiet home screen for the football research workflow.

No API calls, background jobs, trade approval, or generated market lines.
Only current session state is summarized.
"""
from __future__ import annotations

from html import escape
import pandas as pd
import streamlit as st

from ui_timezone import CENTRAL, format_central


def open_page(destination: str):
    """Navigation callback; no network operation and no orders."""
    st.session_state["sports_nav"]=destination


def home_dashboard():
    now=pd.Timestamp.now(tz="UTC")
    local=now.tz_convert(CENTRAL)
    st.markdown('<div class="tl-page-kicker">YOUR GAME-DAY COMMAND CENTER</div>',
                unsafe_allow_html=True)
    st.markdown('<h1 class="tl-page-title">Make the numbers easy.</h1>',
                unsafe_allow_html=True)
    st.caption(local.strftime("%A, %b %d")+" · Central Time · Read-only research")
    st.markdown("### Where to start")

    a,b=st.columns(2,gap="small")
    with a:
        st.markdown('<div class="tl-action-card"><strong>🏈 Games</strong><p>Vegas spread vs model, team logos, simulations and evidence.</p></div>',
                    unsafe_allow_html=True)
        st.button("Open Games",key="home_go_games",type="primary",
                  use_container_width=True,on_click=open_page,args=("Tonight CFB",))
    with b:
        st.markdown('<div class="tl-action-card"><strong>📊 Kalshi Markets</strong><p>Review last scanned contracts, prices, and trade blockers.</p></div>',
                    unsafe_allow_html=True)
        st.button("Open Markets",key="home_go_markets",
                  use_container_width=True,on_click=open_page,args=("Opportunities",))

    saved=st.session_state.get("cfb_tonight_rows")
    stamp=st.session_state.get("cfb_tonight_at")
    valid_day=st.session_state.get("cfb_tonight_day")==local.date().isoformat()
    valid=isinstance(saved,pd.DataFrame) and stamp is not None and valid_day
    if valid:
        remaining=saved.loc[saved.kickoff_utc>now].copy()
        from cfb_model.card_design import card_view, summary_html
        age=max(0,(now-pd.Timestamp(stamp)).total_seconds()/60)
        views=[card_view(r,age) for _,r in remaining.iterrows()]
        shown=sum(v["market"]["show"] for v in views)
        gaps=sum(v["spread_gap"] is not None and v["spread_gap"]>=7 for v in views)
        st.markdown('<div class="tl-section-label">YOUR LAST GAME SCAN</div>',
                    unsafe_allow_html=True)
        st.markdown(summary_html(len(remaining),shown,gaps,format_central(stamp)),
                    unsafe_allow_html=True)
        if age>15:
            st.caption("Prices have aged. Refresh from Games for current data.")
        if not remaining.empty:
            leader=sorted((v for v in views if v["spread_gap"] is not None),
                          key=lambda v:v["spread_gap"],reverse=True)
            if leader:
                best=leader[0]
                st.caption("Largest recorded model disagreement: "
                           +best["away"]+" @ "+best["home"]+" · "
                           +f'{best["spread_gap"]:.1f} points'
                           +" (research flag, not betting edge).")
    else:
        st.markdown('<div class="tl-empty"><strong>No game slate loaded yet</strong><p>Open Games and refresh to see the remaining kickoffs. This home screen does not spend API credits.</p></div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="tl-section-label">KALSHI SCANNER</div>',
                unsafe_allow_html=True)
    scan=st.session_state.get("quick_results")
    if isinstance(scan,dict) and scan:
        st.caption("Last scan: "+format_central(scan.get("time"))+
                   " · Matched outcome sides: "+str(scan.get("matched",0)))
    else:
        st.caption("No scan results in this session. Open the scanner below to start one.")

    st.caption("Our 2025 baseline was less accurate than sportsbook closing lines. "
               "Simulated win chances and spread differences are not verified profitable bets.")
