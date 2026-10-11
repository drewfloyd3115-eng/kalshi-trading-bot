"""Mobile paper portfolio visualization. Read-only; no market requests or orders."""
from html import escape
import pandas as pd
import streamlit as st
from paper_history import HISTORY_COLUMNS, summary as paper_summary


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
    metrics = [
        ("Paper bankroll", "USD " + f'{model["bankroll"]:,.2f}', "Hypothetical balance setting"),
        ("Queued paper exposure", "USD " + f'{model["queue_exposure"]:,.2f}', "Not filled positions"),
        ("Open paper fills", str(model["open_paper_fills"]), "Hypothetical, unresolved"),
        ("Settled paper records", str(model["closed"]), "Gross P&L excludes fees")
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


def portfolio_page(bankroll, other_exposure):
    """Pure presentation over cached session research; never fetches odds."""
    st.markdown(_STYLES, unsafe_allow_html=True)
    model = portfolio_view_model(
        st.session_state.get("paper_history"),
        st.session_state.get("queue", []),
        bankroll, other_exposure,
        st.session_state.get("paper_exposure", 0.0)
    )
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

    elif area == "Open paper fills":
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
        st.markdown("### Paper journal")
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
