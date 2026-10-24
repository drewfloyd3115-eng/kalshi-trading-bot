"""Mobile UI for manual read-only Kalshi sell-bid depth checks.

Never fetches public data during ordinary page rendering. Only an explicit
button click requests Kalshi public market metadata and one order book.
No sportsbook API requests, automated sells or assumed fills.
"""
from html import escape
from urllib.parse import quote

import pandas as pd
import streamlit as st

from exit_liquidity import (
    MAX_REVIEW_SHARES, review_public_position, snapshot_integrity
)
from position_ledger import open_positions
from scanner import _get
from ui_timezone import format_central


def _usd(value):
    try:
        number = float(value)
        if not pd.notna(number):
            return "—"
        return "$" + f"{number:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _cents(value):
    try:
        number = float(value)
        if not pd.notna(number):
            return "—"
        return f"{number:.2f}¢"
    except (TypeError, ValueError):
        return "—"


def _review_card(snapshot, integrity_ok, integrity_reason):
    """Render untrusted market comments safely and never claim a verified exit."""
    title = escape(str(snapshot.get("ticker") or "UNKNOWN"))
    side = escape(str(snapshot.get("side") or "UNKNOWN"))
    covered = int(snapshot.get("covered_shares") or 0)
    requested = snapshot.get("requested_shares")
    requested_text = escape(str(requested if requested is not None else "?"))
    best_bid = _cents(snapshot.get("best_bid_cents"))
    gross = _usd(snapshot.get("gross_proceeds_usd"))
    fees = _usd(snapshot.get("estimated_exit_fee_usd"))
    net = _usd(snapshot.get("net_proceeds_usd"))
    basis = _usd(snapshot.get("allocated_entry_cost_usd"))
    pnl = _usd(snapshot.get("hypothetical_net_pnl_usd"))
    reason = escape(str(snapshot.get("reason") or "Verification unavailable"))
    validity = escape(str(integrity_reason))
    market_meta = escape(str(snapshot.get("market_metadata_status") or
                             "UNKNOWN — NO MARKET UPDATE TIMESTAMP"))
    market_age = snapshot.get("market_updated_age_minutes")
    updated_age = ("—" if market_age is None
                   else escape(str(market_age)) + " minutes")
    fee_type = escape(str(snapshot.get("series_fee_type") or "UNKNOWN"))
    fee_multiplier = snapshot.get("series_fee_multiplier")
    multiplier_display = ("—" if fee_multiplier is None
                          else escape(str(fee_multiplier)))
    fee_status = escape(str(snapshot.get("series_fee_metadata_status") or
                            "UNVERIFIED — NO SERIES FEE METADATA"))

    provenance = str(snapshot.get("lookup_status") or "SOURCE UNVERIFIED")
    if provenance == "REJECTED BEFORE LOOKUP":
        freshness = "NO PUBLIC LOOKUP"
    elif provenance == "PUBLIC LOOKUP FAILED":
        freshness = "LOOKUP FAILED"
    elif provenance == "MARKET METADATA ONLY — NO ORDERBOOK":
        freshness = "NO ORDERBOOK"
    elif provenance == "PUBLIC ORDERBOOK RETURNED" and integrity_ok:
        freshness = "RECENT RETRIEVAL"
    elif integrity_ok and provenance == "SOURCE UNVERIFIED":
        freshness = "SOURCE UNVERIFIED"
    else:
        freshness = "NOT CURRENT"
    return f"""
<div class="kl-port-panel">
  <div class="kl-port-title">Public order-book exit research</div>
  <div class="kl-port-muted">{title} · Selling held {side} contracts ·
    Snapshot checked (Central) {escape(format_central(snapshot.get("checked_utc"),missing="Unknown"))}</div>
  <div class="kl-port-chip pending">UNVERIFIED · NO EXIT SIGNAL</div>
  <div class="kl-port-grid">
    <div class="kl-port-stat"><small>Held-side best bid</small><strong>{best_bid}</strong>
      <span>Snapshot, not a guaranteed fill</span></div>
    <div class="kl-port-stat"><small>Bid depth inspected</small><strong>{covered} / {requested_text}</strong>
      <span>Observed shares / requested sale</span></div>
    <div class="kl-port-stat"><small>Gross hypothetical sale</small><strong>{gross}</strong>
      <span>For covered shares only</span></div>
    <div class="kl-port-stat"><small>Estimated sale fee</small><strong>{fees}</strong>
      <span>Generic fee formula · unverified</span></div>
    <div class="kl-port-stat"><small>Net hypothetical proceeds</small><strong>{net}</strong>
      <span>For covered shares; includes estimated exit fees</span></div>
    <div class="kl-port-stat"><small>Allocated entry cost</small><strong>{basis}</strong>
      <span>Includes proportion of manually entered entry fees</span></div>
    <div class="kl-port-stat"><small>Hypothetical net P&amp;L</small><strong>{pnl}</strong>
      <span>NOT actual realized profit or an exit recommendation</span></div>
    <div class="kl-port-stat"><small>Source freshness</small>
      <strong>{freshness}</strong>
      <span>Source bid age and execution remain unverified</span></div>
  </div>
  <div class="kl-port-muted"><b>Market metadata update:</b> {market_meta}
    (age: {updated_age}). The age of individual resting bids remains unknown.</div>
  <div class="kl-port-muted" style="margin-top:7px"><b>Series fee fields:</b>
    {fee_type} · multiplier {multiplier_display} · {fee_status}</div>
  <div class="kl-port-muted"><b>Lookup result:</b> {escape(provenance)}</div>
  <div class="kl-port-muted"><b>Depth / market:</b> {reason}</div>
  <div class="kl-port-muted" style="margin-top:7px"><b>Snapshot integrity:</b> {validity}</div>
  <div class="kl-port-muted" style="margin-top:9px">The source does not verify
    exchange-specific fees, counterparty availability, order fills, contract
    settlement rules, in-game probability or the value of holding.</div>
</div>
"""


def render_exit_review(ledger):
    """No network calls until Review button is manually clicked."""
    positions = open_positions(ledger)
    st.markdown("#### Review Open Positions — sell-side depth")
    st.caption("Independent of the new-buy scanner. Uses at most three Kalshi "
               "PUBLIC requests (market, order book and fee metadata) only when "
               "you tap Review. No sportsbook API credits, auto-trades, "
               "or background checks.")
    if positions.empty:
        st.info("No open manual paper positions to review. Record a hypothetical "
                "entry in Open paper fills first.")
        return

    st.caption(f"{len(positions)} open manual paper position(s); "
               "no scan is treated as a filled trade.")
    keys = positions["position_id"].tolist()
    if st.session_state.get("exit_review_position_id") not in keys:
        st.session_state["exit_review_position_id"] = keys[0]
    def position_label(pid):
        record = positions.loc[positions["position_id"] == pid].iloc[0]
        return (str(record["event"]) + " · " + str(record["side"]) +
                " · " + str(record["remaining_shares"]) + " shares")
    selected = st.selectbox("Open paper position", keys,
                            format_func=position_label,
                            key="exit_review_position_id")
    row = positions.loc[positions["position_id"] == selected].iloc[0]
    held = int(row["remaining_shares"])
    max_qty = min(held, MAX_REVIEW_SHARES)
    # Prevent old quantity state exceeding limits after switching positions.
    current_qty = st.session_state.get("exit_review_shares", max_qty)
    if (st.session_state.get("exit_review_position_last") != selected
            or not isinstance(current_qty, int)
            or not 1 <= current_qty <= max_qty):
        st.session_state["exit_review_position_last"] = selected
        st.session_state["exit_review_shares"] = max_qty
    qty = st.number_input("Number of held shares to inspect for a hypothetical sale",
                          min_value=1, max_value=max_qty,
                          value=max_qty, step=1, key="exit_review_shares")
    st.caption(f'Current recorded basis: {_usd(row["remaining_cost_usd"])} for '
               f'{held} held {row["side"]} shares. '
               "The order book may have less depth than your requested quantity.")

    if st.button("Review selected position — Kalshi public bids",
                 key="review_public_exit_bids",
                 use_container_width=True):
        # This is the ONLY path in this UI that performs public GET requests.
        # A synthetic test ticker fails closed before making network calls.
        result = review_public_position(
            row.to_dict(), requested_shares=int(qty),
            series_fetch=lambda ticker: _get(
                "/series/" + quote(ticker, safe="")).get("series", {}))
        cached = st.session_state.get("exit_review_cache", {})
        cached = {pid: value for pid, value in cached.items() if pid in keys}
        cached[selected] = result
        st.session_state["exit_review_cache"] = cached

    cached = st.session_state.get("exit_review_cache", {})
    snapshot = cached.get(selected) if isinstance(cached, dict) else None
    if snapshot is None:
        st.info("No order-book exit review requested for this position yet. "
                "Tapping Review fetches its public sell-side bid snapshot. "
                "There are no verified exit opportunities.")
        return

    recent, reason = snapshot_integrity(
        snapshot, row.to_dict(), requested_shares=int(qty))
    if not recent:
        st.warning(reason + ". Any displayed prices and potential proceeds are historical research only.")
    elif not snapshot.get("depth_complete"):
        st.warning("Incomplete or missing held-side sale depth. "
                   "No full-exit valuation can be verified.")
    else:
        st.info("Observed held-side bids cover the requested quantity, "
                "but individual bid age, actual execution, event fee overrides and "
                "settlement remain UNVERIFIED. No sell signal is generated.")

    st.markdown(_review_card(snapshot, recent, reason), unsafe_allow_html=True)
    levels = snapshot.get("levels_used")
    if isinstance(levels, list) and levels:
        with st.expander("Bid levels inspected (read-only)", expanded=False):
            st.caption("These are resting bids for the HELD side. Selling YES takes "
                       "YES bids; selling NO takes NO bids. Prices may change.")
            st.dataframe(pd.DataFrame(levels), hide_index=True, use_container_width=True)
    st.caption("Manual exit entries below are still separate hypothetical accounting "
               "records; this snapshot never creates or pre-populates a trade.")
