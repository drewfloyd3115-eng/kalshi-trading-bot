"""Mobile paper portfolio visualization. Read-only; no market requests or orders."""
from html import escape
import pandas as pd
import streamlit as st
from paper_history import HISTORY_COLUMNS, summary as paper_summary
from position_ledger import (
    empty_ledger, export_ledger, import_ledger, ledger_summary, open_positions,
    record_entry, record_exit, validate_ledger,
)


def portfolio_view_model(history, queue, bankroll, other_exposure, queue_exposure):
    """Queued research is never counted as a fill; net ROI is not available."""
    if not isinstance(history, pd.DataFrame) or not set(HISTORY_COLUMNS).issubset(history.columns):
        history = pd.DataFrame(columns=HISTORY_COLUMNS)
    if not isinstance(queue, list):
        queue = []
    open_rows = history[
        history["paper_status"].eq("PAPER_FILLED")
        & history["settlement_result"].eq("UNRESOLVED")
        & pd.to_numeric(history["paper_shares"], errors="coerce").fillna(0).gt(0)
    ].copy()
    stats = paper_summary(history)
    return {
        "bankroll": max(0.0, float(bankroll)),
        "queue_exposure": max(0.0, float(queue_exposure)),
        "other_exposure": max(0.0, float(other_exposure)),
        "queue_count": len(queue),
        "queue": queue,
        "observations": stats["observations"],
        "paper_fills": stats["paper_fills"],
        "open_paper_fills": len(open_rows),
        "closed": stats["closed"],
        "wins": stats["wins"],
        "gross_pnl": stats["gross_pnl"],
        "open_rows": open_rows,
        "history": history,
    }


def _portfolio_metric(label, value, description):
    return (
        '<div class="kl-port-stat"><small>' + escape(str(label)) +
        '</small><strong>' + escape(str(value)) +
        '</strong><span>' + escape(str(description)) + '</span></div>'
    )


def portfolio_overview_html(model):
    """HTML escapes visible values; includes no fabricated trades or returns."""
    ledger = model.get("manual_ledger", {})
    metrics = [
        ("Paper bankroll", "USD " + f'{model["bankroll"]:,.2f}', "Hypothetical balance setting"),
        ("Open manual positions", str(ledger.get("open_positions", 0)),
         "Explicitly recorded paper fills"),
        ("Open ledger cost basis", "USD " + f'{ledger.get("open_cost_usd",0):,.2f}',
         "Entered cost and fees; unverified"),
        ("Queued paper exposure", "USD " + f'{model["queue_exposure"]:,.2f}', "Not filled positions"),
    ]
    cards = "\n".join(_portfolio_metric(*row) for row in metrics)
    return """
<div class="kl-port-hero">
 <div class="kl-port-eyebrow">CFB / NFL · PERSONAL RESEARCH</div>
 <div class="kl-port-name">Paper Portfolio</div>
 <div class="kl-port-caption">Track hypothetical activity, recorded outcomes and
 exposure. No live balances, automatic fills or fabricated performance.</div>
 <span class="kl-port-paper">● PAPER ONLY · NO REAL POSITIONS</span>
</div>
<div class="kl-port-grid">""" + cards + "</div>"


def _open_paper_card(row):
    """Visualize a recorded unresolved paper fill, not an executable position."""
    event = escape(str(row.get("event", "Unknown event")))
    ticker = escape(str(row.get("ticker", "Unknown ticker")))
    side = escape(str(row.get("side", "Unknown side")))
    shares = pd.to_numeric(row.get("paper_shares"), errors="coerce")
    price = pd.to_numeric(row.get("paper_fill_price_cents"), errors="coerce")
    shares_label = str(int(shares)) if pd.notna(shares) and shares >= 0 else "—"
    price_label = f"{float(price):.1f}¢" if pd.notna(price) and 0 <= price <= 100 else "—"
    return (
        '<div class="kl-port-record"><b>' + event + '</b>' +
        '<small>' + ticker + ' · ' + side + ' · ' + shares_label + ' hypothetical shares</small>' +
        '<span class="kl-port-chip pending">PAPER FILL · UNRESOLVED</span>' +
        '<div class="kl-port-muted">Recorded paper entry: ' + price_label +
        ' · No current executable sell bid, verified fee-adjusted exit value, '
        'or validated mark-to-market profit.</div></div>'
    )


_STYLES = """
<style>
.kl-port-hero {
 background:radial-gradient(ellipse at 85% 0%,#175583 0%,transparent 60%),
            linear-gradient(125deg,#0c2c49,#08192d);
 border:1px solid #326080;border-radius:16px;padding:17px 15px;margin:8px 0 14px;
}
.kl-port-eyebrow {font-size:.69rem;letter-spacing:.15em;color:#84cbff;font-weight:800;}
.kl-port-name {font-size:1.5rem;font-weight:850;color:#f4faff;margin:5px 0;}
.kl-port-caption {font-size:.83rem;line-height:1.48;color:#b6d6eb;}
.kl-port-paper {display:inline-block;margin-top:11px;border-radius:8px;padding:5px 9px;
 background:#0b3935;color:#6af0cc;border:1px solid #237a6b;font-size:.73rem;font-weight:800;}
.kl-port-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:10px 0;}
.kl-port-stat {min-width:0;background:linear-gradient(140deg,#0b2942,#071a2e);
 border:1px solid #315674;border-radius:12px;padding:13px 11px;}
.kl-port-stat small {display:block;color:#aac6df;font-size:.72rem;}
.kl-port-stat strong {display:block;color:#f8fcff;font-size:1.33rem;margin:8px 0 4px;font-weight:850;overflow-wrap:anywhere;}
.kl-port-stat span {display:block;color:#87aeca;font-size:.68rem;line-height:1.35;}
.kl-port-panel {background:#081e32;border:1px solid #2c4c6c;border-radius:13px;
 padding:14px;margin:12px 0;color:#d9e9fa;}
.kl-port-title {font-weight:800;color:#ecf8ff;font-size:1rem;margin-bottom:7px;}
.kl-port-muted {font-size:.78rem;line-height:1.52;color:#9cbedb;}
.kl-port-record {background:#0c2a44;border:1px solid #355e7f;border-radius:11px;
 padding:12px;margin:9px 0;overflow-wrap:anywhere;}
.kl-port-record b {color:#f5faff;}
.kl-port-record small {display:block;color:#b1d2eb;margin:5px 0;font-size:.72rem;}
.kl-port-chip {display:inline-block;font-size:.68rem;font-weight:800;border-radius:8px;
 border:1px solid #50789a;background:#153651;color:#bfe6ff;padding:4px 8px;margin:8px 0 2px;}
.kl-port-chip.pending {border-color:#a07a36;background:#382d17;color:#f4d49a;}
@media (max-width:650px) {
 .kl-port-hero {padding:13px;}
 .kl-port-stat {padding:10px;}
 .kl-port-stat strong {font-size:1.17rem;}
 .kl-port-name {font-size:1.30rem;}
}
</style>
"""


def _position_card(row):
    """Paper ledger position card; never suggest current sale values."""
    event = escape(str(row["event"]))
    label = escape(str(row["ticker"]))
    outcome = escape(str(row["outcome_team"]))
    side = escape(str(row["side"]))
    return (
        '<div class="kl-port-record"><b>' + event + '</b>' +
        '<small>' + outcome + ' · ' + side + ' · ' + label + '</small>' +
        '<span class="kl-port-chip pending">MANUAL PAPER FILL · NO EXIT PRICE VERIFIED</span>' +
        '<div class="kl-port-muted">Remaining: ' + str(int(row["remaining_shares"])) +
        ' / ' + str(int(row["entry_shares"])) + ' shares · entry ' +
        str(int(row["entry_cents"])) + '¢ · remaining cost basis USD ' +
        f'{float(row["remaining_cost_usd"]):.2f}' +
        '. Amounts are manual hypotheticals, not live balances.</div></div>'
    )


def _manual_entry_form(bankroll, other_exposure):
    with st.expander("Record a hypothetical paper entry", expanded=False):
        st.caption("This requires manually entering a hypothetical fill. "
                   "It is not an actual market execution or a scanner recommendation. "
                   "The 1% per-market and 3% total paper bankroll limits apply.")
        with st.form("position_entry_form", clear_on_submit=True):
            league = st.selectbox("Football league", ["CFB", "NFL"],
                                  key="ledger_entry_league")
            ticker = st.text_input("Exact Kalshi market ticker", max_chars=128,
                                   placeholder="KXCFB-EXACT-TICKER", key="ledger_entry_ticker")
            event = st.text_input("Game / matchup", max_chars=200,
                                  placeholder="Team A vs Team B", key="ledger_entry_event")
            winner = st.text_input("Winning outcome / team", max_chars=120,
                                   placeholder="Team A", key="ledger_entry_winner")
            side = st.radio("Contract side", ["YES", "NO"], horizontal=True,
                            key="ledger_entry_side")
            shares = st.number_input("Hypothetical shares bought", min_value=1,
                                     max_value=100000, value=1, step=1, key="ledger_entry_shares")
            price = st.number_input("Entry price (cents / share)", min_value=1,
                                    max_value=99, value=50, step=1, key="ledger_entry_price")
            fee = st.number_input("Total entry fee entered ($)", min_value=0.0,
                                  max_value=100000.0, value=0.0, step=0.01, format="%.2f",
                                  key="ledger_entry_fee")
            st.caption("Fees are manually entered and NOT verified; entering $0 does "
                       "not mean the actual contract has no fees.")
            notes = st.text_input("Optional paper-entry note", max_chars=350,
                                  key="ledger_entry_notes")
            confirmed = st.checkbox(
                "I confirm this is a manually simulated fill, not a real trade or verified price.",
                key="ledger_entry_confirm")
            save = st.form_submit_button("Save hypothetical entry", type="primary",
                                         use_container_width=True)
        if save:
            if not confirmed:
                st.error("Confirm that this is only a simulated manual fill.")
            else:
                try:
                    new_ledger = record_entry(
                        st.session_state.position_ledger,
                        league=league, ticker=ticker.strip(), event=event,
                        outcome_team=winner, side=side, shares=int(shares),
                        price_cents=int(price), fee_usd=f"{fee:.2f}",
                        bankroll=f"{bankroll:.2f}",
                        other_exposure=f"{other_exposure:.2f}",
                        queued_exposure=f"{float(st.session_state.get('paper_exposure', 0)):.2f}",
                        notes="MANUAL HYPOTHETICAL ENTRY — UNVERIFIED. " + notes
                    )
                    st.session_state.position_ledger = new_ledger
                    st.session_state.ledger_notice = "Manual hypothetical entry recorded. Download a CSV backup in History."
                    st.rerun()
                except ValueError as exc:
                    st.error(f"Paper entry rejected: {exc}")


def _manual_exit_form(ledger):
    positions = open_positions(ledger)
    st.markdown("#### Manually record a hypothetical exit")
    st.caption("This is an accounting simulation, NOT an exit signal. "
               "The app has not verified a sellable bid, available depth, or fee schedule.")
    if positions.empty:
        st.info("No open manual paper positions exist. Record a hypothetical entry in Open paper fills first.")
        return
    with st.form("position_exit_form", clear_on_submit=True):
        keys = positions["position_id"].tolist()
        selected = st.selectbox("Manual position to partially or fully exit",
                                keys, key="ledger_exit_position",
                                format_func=lambda k: (
                                    str(positions.loc[positions["position_id"] == k, "event"].iloc[0])
                                    + " · " + str(positions.loc[positions["position_id"] == k, "side"].iloc[0])
                                    + " · " + str(positions.loc[positions["position_id"] == k, "remaining_shares"].iloc[0])
                                    + " remaining shares"
                                ))
        position = positions.loc[positions["position_id"] == selected].iloc[0]
        st.caption(f'Entry: {int(position["entry_cents"])}¢ per share · '
                   f'{int(position["remaining_shares"])} shares available')
        shares = st.number_input("Shares to hypothetically sell",
                                 min_value=1, max_value=int(position["remaining_shares"]),
                                 value=int(position["remaining_shares"]), step=1,
                                 key="ledger_exit_shares")
        price = st.number_input("Manually assumed exit price (cents / share)",
                                min_value=1, max_value=99, value=50, step=1,
                                key="ledger_exit_price")
        fee = st.number_input("Total exit fee entered ($)", min_value=0.0,
                              max_value=100000.0, value=0.0, step=0.01,
                              format="%.2f", key="ledger_exit_fee")
        notes = st.text_input("Optional exit note", max_chars=350,
                              key="ledger_exit_notes")
        confirmed = st.checkbox(
            "I confirm the exit price is hypothetical and does not represent a verified bid.",
            key="ledger_exit_confirm")
        submit = st.form_submit_button("Record hypothetical partial/full exit",
                                       type="primary", use_container_width=True)
    if submit:
        if not confirmed:
            st.error("Confirm that this is only a hypothetical manual exit.")
        else:
            try:
                updated = record_exit(
                    ledger, selected, shares=int(shares), price_cents=int(price),
                    fee_usd=f"{fee:.2f}",
                    notes="MANUAL HYPOTHETICAL EXIT — UNVERIFIED. " + notes)
                st.session_state.position_ledger = updated
                st.session_state.ledger_notice = (
                    "Manual hypothetical exit recorded. Net P&L uses entered fees only. "
                    "Download a CSV backup in History.")
                st.rerun()
            except ValueError as exc:
                st.error(f"Paper exit rejected: {exc}")


def _ledger_history(ledger):
    st.markdown("### Manual paper position ledger")
    st.caption("Export after every session: positions are stored in this browser session "
               "until you download and later restore the ledger.")
    st.download_button(
        "Download position ledger CSV",
        export_ledger(ledger),
        file_name="kalshi_position_ledger.csv", mime="text/csv",
        key="ledger_download", use_container_width=True)
    if not ledger.empty:
        visible = ["recorded_at_utc", "event", "ticker", "side", "action",
                   "shares", "price_cents", "fee_usd", "position_id"]
        st.dataframe(ledger[visible], hide_index=True, use_container_width=True)
    else:
        st.info("No manually recorded position transactions yet.")

    with st.expander("Restore / replace ledger from CSV", expanded=False):
        st.warning("Import REPLACES the current manual position ledger. Download your "
                   "existing CSV first. Legacy scan history is unaffected.")
        upload = st.file_uploader("Position ledger backup CSV",
                                  type=["csv"], key="ledger_import_file")
        confirm = st.checkbox("I understand this replaces my current manual position ledger.",
                              key="ledger_import_confirm")
        if st.button("Replace manual ledger from file", key="ledger_import_go"):
            if upload is None or not confirm:
                st.error("Select a valid ledger backup and confirm replacement.")
            else:
                try:
                    imported = import_ledger(upload.getvalue())
                    st.session_state.position_ledger = imported
                    st.session_state.ledger_notice = (
                        "Position ledger restored from CSV. Entries were not executed as live trades.")
                    st.rerun()
                except ValueError as exc:
                    st.error(f"CSV restore rejected; ledger unchanged: {exc}")


def portfolio_page(bankroll, other_exposure):
    """Pure presentation over cached paper entries; no network or orders."""
    st.markdown(_STYLES, unsafe_allow_html=True)
    if "position_ledger" not in st.session_state:
        st.session_state.position_ledger = empty_ledger()
    # Fail closed on invalid session state; imported CSV is always validated
    # before replacing this state.
    try:
        ledger = validate_ledger(st.session_state.position_ledger)
    except ValueError as exc:
        st.error(f"Position ledger validation failed. No entries or exits permitted: {exc}")
        return
    notice = st.session_state.pop("ledger_notice", None)
    if notice:
        st.success(notice)
    model = portfolio_view_model(
        st.session_state.get("paper_history"),
        st.session_state.get("queue", []),
        bankroll, other_exposure,
        st.session_state.get("paper_exposure", 0.0)
    )
    model["manual_ledger"] = ledger_summary(ledger)
    st.markdown(portfolio_overview_html(model), unsafe_allow_html=True)
    st.caption("Paper research only · no account connection or automatic settlement.")
    area = st.pills(
        "Portfolio area",
        ["Overview", "Open paper fills", "History", "Exit review"],
        selection_mode="single", default="Overview", key="sports_portfolio_area",
        label_visibility="collapsed"
    ) or "Overview"

    if area == "Overview":
        st.markdown('<div class="kl-port-panel"><div class="kl-port-title">Recorded performance</div>'
                    '<div class="kl-port-muted">Only explicitly recorded paper fills and settlements count. '
                    'Scans and paper queue entries never imply a trade was filled.</div></div>',
                    unsafe_allow_html=True)
        if model["closed"]:
            st.metric("Gross settled paper P&L — fees excluded",
                      "USD " + f'{model["gross_pnl"]:+,.2f}')
            st.caption(f'{model["wins"]} of {model["closed"]} settled paper records are marked WIN. '
                       "Gross figures exclude unverified entry/exit fees, so net ROI is not known.")
        else:
            st.info("No closed paper positions yet. Win rate, net ROI and profit aren't established.")
        st.markdown("#### Paper research queue")
        st.caption(f'{model["queue_count"]} queued decisions · USD ' +
                   f'{model["queue_exposure"]:,.2f}' + ' of pending research exposure, not fills')
        if model["queue"]:
            st.dataframe(pd.DataFrame(model["queue"]), hide_index=True, use_container_width=True)
        else:
            st.markdown('<div class="kl-port-panel"><div class="kl-port-title">'
                        'No queued paper decisions</div>'
                        '<div class="kl-port-muted">Paper research will appear here only after an '
                        'explicit approval in the Research section.</div></div>',
                        unsafe_allow_html=True)
        if model["other_exposure"]:
            st.caption("Additional manual exposure assumption (not verified): USD " +
                       f'{model["other_exposure"]:,.2f}')
        if model["manual_ledger"]["has_exits"]:
            st.metric("Manual hypothetical net P&L — entered fees only",
                      "USD " + f'{model["manual_ledger"]["realized_net_usd"]:+,.2f}')
            st.caption("Based solely on your manually recorded hypothetical prices and fees; "
                       "not verified market execution or actual gains.")
        if model["open_paper_fills"] or model["closed"]:
            st.caption(f'{model["open_paper_fills"]} legacy journal paper fills and '
                       f'{model["closed"]} legacy settled records are tracked separately '
                       "from the new manual position ledger.")

    elif area == "Open paper fills":
        st.markdown("### Manual position ledger")
        manual_positions = open_positions(ledger)
        if manual_positions.empty:
            st.info("No manually recorded open paper positions.")
        else:
            st.caption(str(len(manual_positions)) + " open manual paper positions; "
                       "there are no verified current sell bids or market valuations.")
            for _, record in manual_positions.head(30).iterrows():
                st.markdown(_position_card(record), unsafe_allow_html=True)
            if len(manual_positions) > 30:
                st.caption("Showing 30 positions; view all transactions in History.")
        _manual_entry_form(bankroll, other_exposure)

        st.markdown("#### Legacy imported paper journal fills")
        st.markdown("### Unresolved paper positions")
        st.caption("Only journal records explicitly marked PAPER_FILLED and UNRESOLVED appear here.")
        if model["open_rows"].empty:
            st.info("No open hypothetical fills recorded. A saved observation or queued paper "
                    "decision is not a position.")
        else:
            for _, record in model["open_rows"].head(25).iterrows():
                st.markdown(_open_paper_card(record), unsafe_allow_html=True)
            if len(model["open_rows"]) > 25:
                st.caption(f'Showing 25 of {len(model["open_rows"])} records; see History for all.')
        st.warning("Entry fees, current sell-side bids, executable depth and net exit values "
                   "are not verified by the existing journal.")

    elif area == "History":
        _ledger_history(ledger)
        st.markdown("### Legacy observation / settlement journal")
        if model["history"].empty:
            st.info("No stored paper records in this session. Use Research to import "
                    "a journal CSV or export a backup.")
        else:
            st.caption(f'{model["observations"]} recorded rows · not proof of market execution')
            cols = ["scan_utc", "event", "ticker", "side", "paper_status",
                    "paper_shares", "settlement_result", "paper_pnl_usd"]
            visible = [col for col in cols if col in model["history"].columns]
            st.dataframe(model["history"][visible], hide_index=True, use_container_width=True)
            st.download_button("Download paper history CSV",
                               model["history"].to_csv(index=False).encode("utf-8"),
                               file_name="kalshi_paper_history.csv",
                               mime="text/csv", key="sports_portfolio_download")
        st.caption("Existing settlement P&L is gross and omits unverified fees; "
                   "a validated net accounting ledger is planned.")

    elif area == "Exit review":
        st.markdown("### Active positions & profit-taking")
        st.markdown('<div class="kl-port-panel"><div class="kl-port-title">'
                    'IN DEVELOPMENT · NO EXIT SIGNALS</div>'
                    '<div class="kl-port-muted">The planned independent position scanner will '
                    'review whether to hold, partially sell or take profits, even if no new buys '
                    'qualify. It must verify the bid and depth for the side being sold, fees, '
                    'partial fills and updated win probabilities where applicable. '
                    'No sell opportunity is currently verified.</div></div>',
                    unsafe_allow_html=True)
        st.caption(f'{model["open_paper_fills"]} unresolved paper fills in this session. '
                   'The present scanner does not supply executable exit bids.')
        st.info("This is an upcoming paper-only tool—not an active trading signal, "
                "automatic sell order or background monitor.")
        st.link_button("Technical exit-review roadmap",
                       "https://github.com/drewfloyd3115-eng/kalshi-trading-bot/issues/1")
        st.divider()
        _manual_exit_form(ledger)
