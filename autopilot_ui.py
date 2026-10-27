"""Mobile control room for planned unattended cross-venue trading.

This is a paper-only control surface, not a deployed cloud worker or
an authenticated trading integration. It makes no requests on page load.
"""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from autopilot_core import Policy, State, public_market_to_candidate
from autopilot_cycle import evaluate_cycle
from config import DEFAULT_BANKROLL
from position_ledger import ledger_summary
from scanner import fetch_sports_markets
from ui_timezone import format_central


def render_autopilot():
    st.subheader("Autopilot · Control Room")
    st.caption("Cross-venue architecture | Paper decisions only | Central Time")
    st.error("REAL TRADING LOCKED. No authenticated orders, no 24/7 bot deployment and no verified independent signals yet.")

    st.markdown("**Exchange connections**")
    a, b, c = st.columns(3)
    a.metric("Kalshi", "PUBLIC")
    b.metric("Polymarket US", "NOT LINKED")
    c.metric("Novig", "NOT LINKED")
    st.caption("Kalshi public game-winner data is available by manual request. Polymarket US and Novig APIs are not connected. No credentials are requested or stored by this page.")

    ledger = ledger_summary(st.session_state["position_ledger"])
    exposure = (float(ledger["open_cost_usd"]) + float(st.session_state.get("paper_exposure", 0))
                + float(st.session_state.get("quick_exposure", 0)))
    policy = Policy()
    bankroll = DEFAULT_BANKROLL
    left, middle, right = st.columns(3)
    left.metric("Paper bankroll", f"${bankroll:.0f}")
    middle.metric("Position cap", f"${bankroll * 0.01:.2f}")
    right.metric("Total exposure cap", f"${bankroll * 0.03:.2f}")
    st.caption(f"Registered paper exposure: ${exposure:.2f} | Maximum daily realized loss: ${float(policy.daily_stop_usd):.2f} | Maximum equity drawdown: ${float(policy.max_drawdown_usd):.2f}")
    st.caption("Profit threshold: +5 percentage-point net edge, independent and calibrated model required; max 3 open positions; max 20 paper proposals/day. Those are limits, not quotas.")

    paused = st.toggle("Pause paper decision engine", value=True, key="autopilot_paused")
    st.caption("Pause is ON by default. This control never enables real trading or API key access.")

    st.markdown("**Manual public feed snapshot**")
    st.caption("Only NFL and CFB Kalshi game-winner contracts are wired to the existing public data scanner. No Odds API, paid Firecrawl credits, or wallet login required.")
    if st.button("Refresh public Kalshi game markets", key="ap_refresh", use_container_width=True):
        st.session_state.pop("ap_results", None)
        st.session_state.pop("ap_market_cache", None)
        try:
            with st.spinner("Reading public Kalshi market listings..."):
                markets = fetch_sports_markets(("NFL", "CFB"), max_pages=1)
            st.session_state["ap_market_cache"] = markets
            st.session_state["ap_market_time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        except Exception as exc:
            st.error("Market refresh failed: " + str(exc)[:180])
    markets = st.session_state.get("ap_market_cache")
    if markets is not None:
        st.caption(f"Observation time (Central): {format_central(st.session_state.get('ap_market_time'))} | {len(markets)} markets retrieved; coverage limited.")
        if not markets.empty:
            st.dataframe(markets[["league", "event", "ticker", "yes_ask_cents", "no_ask_cents"]].head(25),
                         hide_index=True, use_container_width=True)
    if st.button("Evaluate paper risk gates", key="ap_evaluate", use_container_width=True,
                 disabled=paused or markets is None or markets.empty if isinstance(markets,pd.DataFrame) else True):
        # These observations have no validated independent model or executable
        # book-level timestamp. All must BLOCK; never invent proof of an edge.
        candidates = []
        for _, row in markets.head(25).iterrows():
            for side in ("YES", "NO"):
                candidates.append(public_market_to_candidate(row, side))
        state = State(
            bankroll_usd=bankroll,
            current_equity_usd=bankroll,
            open_exposure_usd=exposure,
            existing_event_keys=tuple(),
            kill_switch=paused,
        )
        st.session_state["ap_results"] = evaluate_cycle(
            candidates, state, policy, now=datetime.now(timezone.utc))
        st.session_state["ap_results_time"] = st.session_state.get("ap_market_time")

    report = st.session_state.get("ap_results")
    if report is not None:
        if st.session_state.get("ap_results_time") != st.session_state.get("ap_market_time"):
            st.info("Market refresh changed. Previous risk decisions invalidated.")
        else:
            a, b = st.columns(2)
            a.metric("Paper candidates", report["paper_proposals"])
            b.metric("Blocked", report["blocked"])
            st.warning("These are public listing observations only; no verified model, current order-book depth, fee certification, or settlement review. BLOCK is the expected safe result.")
            rows = [{ "Venue": x["venue"], "Identity": x["identity"],
                      "Decision": x["status"],
                      "Primary reason": x["reasons"][0] if x["reasons"] else "N/A"}
                    for x in report["decisions"]]
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.download_button("Download decision audit CSV",
                pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
                file_name="autopilot_paper_decisions.csv",mime="text/csv",key="ap_csv")

    st.markdown("**Autonomous rollout requirements**")
    st.caption("Before real unattended execution: venue-specific read/write API authorization, independent live probability feeds, event ID mapping across venues, market-specific fees and settlement checks, atomic risk ledger, duplicate-order prevention, authenticated fill reconciliation, emergency shutdown, paper performance review, and private cloud worker deployment.")
    st.info("Automated trading is not running. Nothing on this page creates a paper fill, submits an order, requests an API key, or watches markets while the app is closed.")
