"""Phone-first, on-demand near-certainty PAPER research page.

All market data is public and requested by a human button click only. No paid
feeds, wallet credentials, orders, automatic approvals, or simulated fills.
"""
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from config import DEFAULT_BANKROLL, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT, MIN_EDGE_PP
from near_certainty import watchlist, inspect_one_share
from position_ledger import ledger_summary
from scanner import fetch_sports_markets, fetch_orderbook
from ui_timezone import format_central


def render_near_certainty():
    st.subheader("Near-Certainty · Paper Lab")
    st.caption("90–99¢ outcome scanner | Read-only public Kalshi data | Manual scans only")
    st.warning("WATCH ONLY — no proven +EV, verified fills, or automatic orders. A near-100% market price is not an independently established probability.")

    bank = float(DEFAULT_BANKROLL)
    # Existing manual paper holdings and queue share the same exposure budget.
    held = float(ledger_summary(st.session_state["position_ledger"])["open_cost_usd"])
    queue = float(st.session_state.get("paper_exposure", 0))
    external = float(st.session_state.get("quick_exposure", 0))
    exposure = held + queue + external
    c1, c2, c3 = st.columns(3)
    c1.metric("Paper bankroll", f"${bank:.0f}")
    c2.metric("1% per position", f"${bank * MAX_TRADE_BANKROLL_PCT:.2f}")
    c3.metric("3% total open", f"${bank * MAX_TOTAL_EXPOSURE_PCT:.2f}")
    st.caption(f"Current registered paper exposure: ${exposure:.2f} (held ${held:.2f}, queue ${queue:.2f}, other ${external:.2f}). These are risk ceilings, not spending targets.")
    st.info(f"Existing entry threshold: +{MIN_EDGE_PP:.0f} percentage points AFTER assumed fees. At 95¢ with a one-share 1¢ taker fee, even a 100% win chance yields only +4pp: REJECT under current rules.")

    st.markdown("**Discover potential high-price contracts**")
    st.caption("Initial coverage: public NFL / CFB single-game winner markets. More market categories require separately verified ticker filters, settlement rules and probability sources.")
    leagues = st.multiselect("Games to watch", ["NFL", "CFB"], default=["NFL", "CFB"], key="nc_leagues")
    a, b = st.columns(2)
    with a:
        lower = st.number_input("Lowest price (¢)", min_value=80, max_value=99, value=90, step=1, key="nc_lower")
    with b:
        upper = st.number_input("Highest price (¢)", min_value=80, max_value=99, value=99, step=1, key="nc_upper")

    if st.button("Scan public markets — read only", key="nc_scan", type="primary", use_container_width=True):
        # Invalidate prior selection even if the new feed fails, so old depth can
        # never be presented as belonging to a newly requested scan.
        st.session_state.pop("nc_watchlist", None)
        st.session_state.pop("nc_depth_result", None)
        st.session_state.pop("nc_candidate", None)
        if not leagues or lower > upper:
            st.error("Choose a league and valid price range.")
        else:
            try:
                with st.spinner("Checking public market listings..."):
                    market_rows = fetch_sports_markets(tuple(leagues), max_pages=2)
                    frame = watchlist(market_rows, lower, upper, limit=75)
                scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                st.session_state["nc_watchlist"] = frame
                st.session_state["nc_scanned_utc"] = scanned_at
                st.session_state["nc_scan_count"] = len(market_rows)
                if frame.empty:
                    st.info("No matching open contracts were found in this bounded scan. This is not a claim that none exist elsewhere.")
            except Exception as exc:
                st.error("Read-only public market lookup failed: " + str(exc)[:180])

    frame = st.session_state.get("nc_watchlist")
    if frame is None:
        st.info("Run a manual market scan to begin. No external request runs when opening this page.")
        return

    age_utc = st.session_state.get("nc_scanned_utc")
    st.caption(f"Market snapshot (Central): {format_central(age_utc)}. Examined {st.session_state.get('nc_scan_count', 0)} market rows. Limited coverage; prices may already have changed.")
    st.metric("Price-range matches", len(frame))
    if frame.empty:
        return
    visible_cols = ["league", "event", "side", "indicative_ask_cents", "volume"]
    st.dataframe(frame[visible_cols], hide_index=True, use_container_width=True)
    st.download_button("Download watchlist CSV", frame.to_csv(index=False).encode("utf-8"),
                       file_name="kalshi_near_certainty_watchlist.csv", mime="text/csv", key="nc_export")
    st.markdown("**Inspect one candidate**")
    selection = st.selectbox("Market / side", list(range(len(frame))),
         format_func=lambda idx: (
             f"{str(frame.iloc[idx]['league'])} · {str(frame.iloc[idx]['event'])[:55]} "
             f"· {str(frame.iloc[idx]['side'])} · {float(frame.iloc[idx]['indicative_ask_cents']):.1f}¢"
         ), key="nc_selection")
    row = frame.iloc[selection]
    st.caption("Ticker: " + str(row["ticker"]))
    probability = st.number_input(
        "Independent probability (%) — optional, MANUAL and unverified",
        min_value=0.0, max_value=100.0, value=0.0, step=0.5, key="nc_fair_pct",
        help="0 means no probability supplied. A manually entered percentage is not a calibrated model.")
    if st.button("Inspect public bid depth + risk", key="nc_inspect", use_container_width=True):
        st.session_state.pop("nc_depth_result", None)
        st.session_state.pop("nc_candidate", None)
        try:
            with st.spinner("Checking one public order book..."):
                book = fetch_orderbook(str(row["ticker"]))
                result = inspect_one_share(
                    book, str(row["side"]), bankroll=bank,
                    open_exposure=exposure,
                    fair_probability=None if probability == 0 else probability / 100,
                )
            st.session_state["nc_depth_result"] = result
            st.session_state["nc_candidate"] = {
                "ticker": str(row["ticker"]), "side": str(row["side"]),
                "selection": int(selection), "scanned_utc": age_utc,
            }
        except Exception as exc:
            st.error("Depth check failed; no trade: " + str(exc)[:180])

    result = st.session_state.get("nc_depth_result")
    inspected = st.session_state.get("nc_candidate")
    # A changed selection, independent input, or new scan must not reuse old
    # calculated risk or masquerade as a currently inspected candidate.
    if not result or not inspected or inspected != {
        "ticker": str(row["ticker"]), "side": str(row["side"]),
        "selection": int(selection), "scanned_utc": age_utc,
    }:
        return
    if result.get("manual_probability_pct") != (None if probability == 0 else float(probability)):
        st.info("Probability input changed. Inspect again to recalculate; previous assessment hidden.")
        return

    st.markdown("**One-contract feasibility**")
    st.warning(result["status"])
    if "cost_usd" not in result:
        st.caption("; ".join(result["blockers"]))
        return
    x, y, z = st.columns(3)
    x.metric("Observed implied ask", f"{result['indicative_ask_cents']:.2f}¢")
    y.metric("Cost incl. est. fee", f"${result['cost_usd']:.2f}")
    z.metric("Required fair chance", f"{result['required_probability_for_5pp_pct']:.1f}%")
    x, y = st.columns(2)
    x.metric("If settles right", f"+${result['profit_if_wins_usd']:.2f}")
    y.metric("If settles wrong", f"-${result['loss_if_loses_usd']:.2f}")
    if result["manual_probability_pct"] is not None:
        st.caption(f"MANUAL, UNVERIFIED modeled probability: {result['manual_probability_pct']:.2f}% | fee-adjusted EV: ${result['expected_value_usd']:+.3f} per share | net edge: {result['net_edge_pp']:+.2f}pp.")
    else:
        st.caption("No independent model probability exists for this contract, so expected value is intentionally unavailable.")
    for reason in result["blockers"]:
        st.caption("• " + reason)
    st.caption("Snapshot ≠ executable order. Fee estimate is generic and rounded for one share. Quote age, final outcome rules, fee overrides and model calibration have NOT been verified. Scan results never become paper fills.")
