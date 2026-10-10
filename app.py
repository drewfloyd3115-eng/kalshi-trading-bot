"""Phone-friendly paper-only Kalshi scanner and approval queue."""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from config import DEFAULT_BANKROLL
from risk import evaluate
from edge_engine import no_vig, assess, taker_fee
from scanner import fetch_sports_markets, fetch_orderbook

st.set_page_config(page_title="Kalshi Trade Lab", page_icon="📈", layout="centered")
st.title("Kalshi Trade Lab")
st.caption("Version 0.4 • CFB/NFL research + paper approvals only • LIVE TRADING DISABLED")
st.warning("Market prices are indicative snapshots. Verify executable quotes, fees, liquidity, event rules and live-game timing before any real trade. A quoted price alone does not establish positive EV.")
if "queue" not in st.session_state:
    st.session_state.queue = []
if "paper_exposure" not in st.session_state:
    st.session_state.paper_exposure = 0.0

scan, edge_tab, evaluate_tab, queue_tab = st.tabs(["Market scan", "Edge lab", "Evaluate", "Paper queue"])
with scan:
    st.write("CFB / NFL single-market discovery. Quotes are read-only and may be stale.")
    leagues = st.multiselect("Leagues", ["CFB", "NFL"], default=["CFB", "NFL"])
    pages = st.slider("Pages to scan (1,000 markets per page)", 1, 20, 8)
    if st.button("Scan CFB / NFL", type="primary"):
        if not leagues:
            st.warning("Choose at least one league.")
        else:
            try:
                with st.spinner("Reading public markets..."):
                    st.session_state.markets = fetch_sports_markets(tuple(leagues), pages)
                    st.session_state.snapshot_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            except Exception as exc:
                st.error(f"Market feed unavailable: {exc}")
    if "markets" in st.session_state:
        st.caption(f"Retrieved (UTC): {st.session_state.snapshot_at}. Results are limited by pages and ticker filters; not exhaustive.")
        df = st.session_state.markets
        if df.empty:
            st.info("No matching markets found. Sports tickers may have changed, or more pages may be needed.")
        else:
            st.metric("Matching markets", len(df))
            query = st.text_input("Search teams, title or ticker")
            if query:
                df = df[df["title"].str.contains(query, case=False, na=False) | df["ticker"].str.contains(query, case=False, na=False)]
            st.dataframe(df, hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("Order-book lookup")
    depth_ticker = st.text_input("Exact Kalshi market ticker for depth")
    if st.button("Fetch public order book"):
        if not depth_ticker.strip():
            st.warning("Enter a ticker.")
        else:
            try:
                book = fetch_orderbook(depth_ticker.strip())
                st.caption("These are BID levels, not executable asks. Opposite-side bids imply asks, subject to order-book semantics and freshness.")
                st.json(book)
            except Exception as exc:
                st.error(f"Order-book lookup failed: {exc}")
    st.info("NO VERIFIED EDGE: external no-vig odds, injury context and synchronized fair probabilities are not integrated. Do not treat quotes as trade recommendations.")

with edge_tab:
    st.subheader("Independent odds comparison")
    st.caption("Manual verified odds entry; no automatic sportsbook feed yet. Enter both sides of the SAME binary event.")
    market = st.text_input("Exact Kalshi ticker", key="edge_ticker")
    yes_odds = st.number_input("Sportsbook YES American odds", value=-110, step=5)
    no_odds = st.number_input("Sportsbook NO American odds", value=-110, step=5)
    yes_ask = st.number_input("Kalshi YES ask (cents)", 0.0, 100.0, 50.0, step=1.0)
    no_ask = st.number_input("Kalshi NO ask (cents)", 0.0, 100.0, 50.0, step=1.0)
    yes_depth = st.number_input("Verified YES ask depth (shares)", min_value=0, value=0, step=1)
    no_depth = st.number_input("Verified NO ask depth (shares)", min_value=0, value=0, step=1)
    edge_bankroll = st.number_input("Paper bankroll ($)", min_value=1.0, value=DEFAULT_BANKROLL, key="edge_bankroll")
    edge_exposure = st.number_input("Other open exposure ($)", min_value=0.0, value=0.0, key="edge_exposure")
    fee_multiplier = st.number_input("Verified fee multiplier (1 = standard formula)", min_value=0.0, value=1.0, step=0.1)
    st.warning("Confirm the market rules, current sportsbook lines, fee schedule and executable ask depth yourself. This is a research calculator, not a verified live signal.")
    if st.button("Calculate fee-adjusted edges"):
        try:
            fy, fn = no_vig(yes_odds, no_odds)
            st.write(f"No-vig fair probability: YES {fy:.1%} / NO {fn:.1%}")
            results = assess(yes_odds, no_odds, yes_ask, no_ask, edge_bankroll,
                             edge_exposure + st.session_state.paper_exposure,
                             fee_multiplier, yes_depth, no_depth)
            st.dataframe(pd.DataFrame(results), hide_index=True, use_container_width=True)
            st.info("PAPER CANDIDATE is conditional, not BUY. Recheck all inputs immediately before acting.")
        except Exception as exc:
            st.error(f"Cannot evaluate: {exc}")

with evaluate_tab:
    st.info("Enter an independently estimated probability. The app does not estimate fair probabilities yet. NO price must be the executable NO ask, not 1 minus the YES ask.")
    ticker = st.text_input("Market ticker")
    side = st.selectbox("Contract", ["YES", "NO"])
    fair_pct = st.number_input("Your independent probability (%)", 0.0, 100.0, 50.0, 0.5)
    ask_cents = st.number_input(f"Executable {side} ask (cents)", 0.1, 99.9, 50.0, 0.1)
    contracts = st.number_input("Contracts", min_value=1, value=1, step=1)
    fee = st.number_input("Estimated total fees ($)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
    bankroll = st.number_input("Paper bankroll ($)", min_value=1.0, value=DEFAULT_BANKROLL, step=50.0)
    existing = st.number_input("Other open paper exposure ($)", min_value=0.0, value=0.0, step=1.0)
    if st.button("Evaluate trade"):
        result = evaluate(side, fair_pct / 100, ask_cents / 100, fee, int(contracts), bankroll, existing + st.session_state.paper_exposure)
        st.metric("Net edge (percentage points)", f"{result['edge_pp']:+.2f}")
        st.metric("Estimated cost", f"${result['cost']:.2f}")
        st.write(result["status"])
        for reason in result["reasons"]:
            st.error(reason)
        if result["status"] == "PAPER CANDIDATE" and ticker.strip():
            st.session_state.pending = {"ticker": ticker.strip(), "side": side, "contracts": int(contracts), "ask_cents": ask_cents, "cost": result["cost"], "net_edge_pp": result["edge_pp"], "status": "AWAITING PAPER APPROVAL"}
        else:
            st.session_state.pop("pending", None)
    if "pending" in st.session_state:
        st.write(st.session_state.pending)
        if st.button("Approve PAPER trade only"):
            item = dict(st.session_state.pop("pending"))
            item["status"] = "PAPER APPROVED (NOT EXECUTED)"
            st.session_state.queue.append(item)
            st.session_state.paper_exposure += item["cost"]
            st.success("Added to session-only paper queue. No order was sent.")

with queue_tab:
    st.write("Session-only approvals. Refreshing or restarting the app may erase them.")
    st.dataframe(pd.DataFrame(st.session_state.queue), hide_index=True, use_container_width=True)
    st.metric("Approved paper exposure", f"${st.session_state.paper_exposure:.2f}")
    if st.button("Clear paper queue"):
        st.session_state.queue = []
        st.session_state.paper_exposure = 0.0
        st.rerun()
