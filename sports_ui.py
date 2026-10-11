"""Mobile-first, read-only sports interface. Never places orders or fetches remote data."""
import pandas as pd
import streamlit as st

from config import MIN_EDGE_PP
from edge_engine import taker_fee
from pregame_dashboard import eligibility_dashboard
from price_discovery import price_discovery
from paper_history import summary as paper_summary, HISTORY_COLUMNS


PAGES = ["Home", "Opportunities", "Market Detail", "Portfolio", "Research"]
CARD_COLUMNS = ["league", "event", "outcome_team", "ticker", "side", "fair_pct",
                "ask_cents", "net_edge_pp_1share", "books", "book_spread_pp",
                "oldest_quote_minutes", "quote_quality", "depth_status",
                "research_status", "reason"]


def opportunity_view(matches, odds=None, scan_time=None, depth=None, now=None):
    """Return one best priced route per winning outcome, with current safety status.

    This view is observational; an edge value never constitutes permission to trade.
    No API requests are made.
    """
    if not isinstance(matches, pd.DataFrame) or matches.empty:
        return pd.DataFrame(columns=CARD_COLUMNS)
    prices = price_discovery(matches, depth)
    if prices.empty:
        return pd.DataFrame(columns=CARD_COLUMNS)
    safety = eligibility_dashboard(matches, odds, scan_time, now=now)
    base = matches.drop_duplicates(["ticker", "side"])
    keys = ["ticker", "side"]
    if "league" in base.columns:
        prices = prices.merge(base[keys + ["league"]], on=keys, how="left", validate="many_to_one")
    else:
        prices["league"] = "Unverified"
    if not safety.empty:
        selected = safety[keys + ["research_status", "reason"]].drop_duplicates(keys)
        prices = prices.merge(selected, on=keys, how="left", validate="many_to_one")
    else:
        prices["research_status"] = "BLOCKED"
        prices["reason"] = "Independent pregame verification unavailable"
    prices["research_status"] = prices["research_status"].fillna("BLOCKED")
    prices["reason"] = prices["reason"].fillna("Safety evidence unavailable")
    result = prices[prices["best_route_for_outcome"]].copy()
    for col in CARD_COLUMNS:
        if col not in result.columns:
            result[col] = None
    return result[CARD_COLUMNS].sort_values(
        "net_edge_pp_1share", ascending=False, na_position="last").reset_index(drop=True)


def research_label(row):
    """Conservative user-facing status independent of nominal +EV estimates."""
    if str(row.get("research_status")) != "REVIEW ONLY — NOT APPROVED":
        return "BLOCKED — no trade"
    edge = pd.to_numeric(row.get("net_edge_pp_1share"), errors="coerce")
    if pd.notna(edge) and edge >= MIN_EDGE_PP:
        return "PRELIMINARY +5pp — verify"
    return "BELOW +5pp — no trade"


def add_styles():
    st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 85% 0%, #12325c 0%, transparent 27%),
                linear-gradient(180deg, #061322 0%, #07101d 43%, #040d17 100%);
    color: #e7f2ff;
}
.block-container {max-width: 920px; padding-top: 1.5rem; padding-bottom: 5rem;}
h1, h2, h3 {letter-spacing: -0.025em;}
div[data-testid="stMetric"] {
    border: 1px solid #244665; border-radius: 12px; padding: 12px;
    background: linear-gradient(135deg,#09233a 0%,#061827 100%);
    min-height: 94px;
}
div[data-testid="stMetricValue"] {color:#f1f8ff; font-weight:750;}
div[data-testid="stMetricLabel"] {color:#a6c8e8;}
div.stButton > button[kind="primary"] {
    background: linear-gradient(100deg,#0874e6,#248fff);
    color: white; border: 1px solid #2e9aff; border-radius: 12px; font-weight:700;
}
div.stButton > button[kind="primary"]:hover {background:#086bd2; color:white;}
[data-testid="stForm"], [data-testid="stExpander"] {
    border-color: #1b3b58; border-radius: 12px;
}
[data-testid="stDataFrame"] {border:1px solid #1b3b58; border-radius:12px;}
div[role="radiogroup"] {display:flex; overflow-x:auto; flex-wrap:nowrap; gap:7px;}
div[role="radiogroup"] label {
    white-space:nowrap; border-radius:11px; border:1px solid #234665;
    background:#0a2034; padding:7px 10px; font-size:0.88rem;
}
.kl-hero {
    background: radial-gradient(ellipse at 85% -12%,#1963a7 0%,transparent 48%),
                repeating-linear-gradient(116deg,transparent 0px,transparent 58px,#176e9e19 59px,#176e9e19 61px),
                linear-gradient(110deg,#071b30,#0b3051 58%,#03121e);
    padding:19px 18px 17px; border:1px solid #315b80; border-radius:18px; margin-bottom:14px;
    box-shadow:0 9px 25px #00101d77;
}
.kl-eyebrow {letter-spacing:.17em;font-size:0.70rem;color:#87caff;font-weight:750;}
.kl-title {font-size:1.9rem;line-height:1.12;font-weight:850;margin:7px 0;color:white;}
.kl-title span {color:#30a0ff;}
.kl-subtitle {color:#c2d7eb;font-size:0.88rem;line-height:1.5;}
.kl-pill {display:inline-block;border:1px solid #008d79;background:#053e3a;
    padding:5px 10px;border-radius:10px;font-size:.75rem;color:#51f2c9;font-weight:700;}
.kl-panel {background:linear-gradient(135deg,#092136,#071827); border:1px solid #254763;
    padding:14px;border-radius:13px;margin:8px 0 14px;}
.kl-safe {color:#b5d0e5;font-size:.80rem;line-height:1.55;margin-top:5px;}
.kl-small {color:#8fabc7;font-size:0.78rem;}
</style>
""", unsafe_allow_html=True)


def header():
    st.markdown("""
<div class="kl-hero">
  <div class="kl-eyebrow">FOOTBALL MARKET RESEARCH · CFB / NFL</div>
  <div class="kl-title">Kalshi <span>Trade Lab</span></div>
  <div class="kl-subtitle">Scan markets · Compare estimated probabilities · Track paper results</div>
  <div style="margin-top:11px"><span class="kl-pill">● PAPER MODE · LIVE TRADING DISABLED</span></div>
</div>
""", unsafe_allow_html=True)


def go_to_detail(ticker, side):
    st.session_state["sports_selected_route"] = str(ticker) + "|" + str(side)
    st.session_state["sports_nav"] = "Market Detail"


def _cached_data():
    meta = st.session_state.get("quick_results", {})
    matches = st.session_state.get("quick_comparisons")
    odds = st.session_state.get("quick_odds_cache")
    depth = st.session_state.get("quick_route_depth")
    return meta, opportunity_view(matches, odds, meta.get("time"), depth)


def home_overview(bankroll, extra_exposure):
    meta, opportunities = _cached_data()
    st.markdown("### Game-day research dashboard")
    exposure = float(st.session_state.get("paper_exposure", 0)) + float(extra_exposure)
    a, b, c = st.columns(3)
    a.metric("Paper bankroll", f"${bankroll:,.2f}")
    b.metric("Open paper exposure", f"${exposure:,.2f}")
    c.metric("Distinct outcomes", len(opportunities))
    if not meta:
        st.info("No scan in this session. Select CFB or NFL and use Scan Now. Only that action requests sportsbook odds.")
        return
    st.caption("Last successful scan: " + str(meta.get("time", "Unknown")) +
               " UTC · Quotes may have expired. Viewing this page uses no Odds API credits.")
    st.markdown("#### Top research observations")
    if opportunities.empty:
        st.info("No exact matched outcomes in this scan. NO VERIFIED TRADE.")
        return
    for i, row in opportunities.head(3).iterrows():
        edge = pd.to_numeric(row.get("net_edge_pp_1share"), errors="coerce")
        label = f"{edge:+.2f}pp est." if pd.notna(edge) else "N/A"
        with st.container(border=True):
            st.markdown("**" + str(row.get("event","")) + " · " +
                        str(row.get("outcome_team","")).title() + "**")
            left, right = st.columns([3, 2])
            left.caption("Ask: " + str(row.get("ask_cents","?")) +
                         "¢ · Fair estimate: " + str(row.get("fair_pct","?")) + "%")
            right.markdown("**" + label + "**")
            st.caption(research_label(row))
            st.button("View market details", key=f"home_detail_{i}", use_container_width=True,
                      on_click=go_to_detail, args=(row["ticker"], row["side"]))
    st.caption("Displayed odds, edges, and eligibility are snapshots. No observations are approved trades.")


def opportunities_page():
    meta, data = _cached_data()
    st.markdown("## Opportunities")
    st.caption("Ranked by estimated net edge. One best YES/NO route per distinct winning outcome. Paper research only.")
    if data.empty:
        st.info("No cached market comparisons. Run a CFB or NFL paper scan from Home.")
        return
    league_options = ["All"] + sorted(str(x) for x in data["league"].dropna().unique())
    left, right = st.columns(2)
    league = left.selectbox("League", league_options, key="sports_filter_league")
    status = right.selectbox("Status", ["All", "Pregame review", "Blocked"], key="sports_filter_status")
    if league != "All":
        data = data[data["league"] == league]
    if status == "Pregame review":
        data = data[data["research_status"] == "REVIEW ONLY — NOT APPROVED"]
    elif status == "Blocked":
        data = data[data["research_status"] != "REVIEW ONLY — NOT APPROVED"]
    if data.empty:
        st.info("No outcomes meet these display filters.")
        return
    st.caption(f"{len(data)} outcomes shown · Last scan {meta.get('time', 'Unknown')} UTC")
    for i, row in data.head(25).iterrows():
        edge = pd.to_numeric(row["net_edge_pp_1share"], errors="coerce")
        with st.container(border=True):
            st.markdown(f"**{row['event']}**")
            st.caption(f"{str(row['outcome_team']).title()} to win · {row['league']} · {row['side']} route")
            c1, c2, c3 = st.columns(3)
            c1.metric("Ask", f"{float(row['ask_cents']):.1f}¢")
            c2.metric("Fair estimate", f"{float(row['fair_pct']):.1f}%")
            c3.metric("Net edge est.", f"{edge:+.2f}pp" if pd.notna(edge) else "N/A")
            st.caption(research_label(row) + " · " + str(row.get("reason","")))
            st.button("Inspect market", key=f"opportunity_detail_{i}", use_container_width=True,
                      on_click=go_to_detail, args=(row["ticker"], row["side"]))
    st.warning("NO VERIFIED TRADE. A nominal +5pp edge is not an executable offer or a validated probability.")


def detail_page():
    _, data = _cached_data()
    st.markdown("## Market Detail")
    st.caption("Research explanation drawn from the latest cached scan; no additional sportsbook API calls.")
    if data.empty:
        st.info("No cached market details available. Run a paper scan from Home.")
        return
    routes = {str(r["ticker"]) + "|" + str(r["side"]): r for _, r in data.iterrows()}
    keys = list(routes)
    selected = st.session_state.get("sports_selected_route")
    if selected not in keys:
        selected = keys[0]
    route = st.selectbox("Winning outcome / route", keys, index=keys.index(selected),
                         format_func=lambda x: str(routes[x]["event"]) + " — " +
                             str(routes[x]["outcome_team"]).title() + " (" + str(routes[x]["side"]) + ")")
    row = routes[route]
    edge = pd.to_numeric(row["net_edge_pp_1share"], errors="coerce")
    st.markdown("### " + str(row["event"]))
    st.caption(str(row["outcome_team"]).title() + " to win · " + str(row["ticker"]) + " / " + str(row["side"]))
    a,b,c = st.columns(3)
    a.metric("Kalshi ask (indicative)", f"{float(row['ask_cents']):.1f}¢")
    b.metric("Fair chance (estimate)", f"{float(row['fair_pct']):.2f}%")
    c.metric("Net edge (1 share)", f"{edge:+.2f}pp" if pd.notna(edge) else "N/A")
    st.markdown("#### Verification")
    if row["research_status"] == "REVIEW ONLY — NOT APPROVED":
        st.info("PREGAME RESEARCH ONLY — NOT APPROVED. Exact settlement, executable price, and fees still require validation.")
    else:
        st.error("BLOCKED — NO VERIFIED TRADE")
    st.write(str(row["reason"]))
    st.markdown("#### Source and price quality")
    c1, c2 = st.columns(2)
    c1.metric("Independent books", str(row.get("books") or "N/A"))
    c2.metric("Book disagreement", str(row.get("book_spread_pp") or "N/A") + "pp")
    st.caption("Quote quality: " + str(row.get("quote_quality") or "Unverified"))
    st.caption("Oldest quoted age at scan: " + str(row.get("oldest_quote_minutes") or "Unknown") + " minutes")
    st.caption("Order-book depth: " + str(row.get("depth_status") or "Not inspected"))
    fee = taker_fee(float(row["ask_cents"]), 1)
    st.caption(f"Estimated one-share taker fee: ${fee:.2f}; final fee schedule not certified.")
    st.warning("Paper research only. No real-money order placement. Price, kickoff, injury context, and settlement rules must be independently verified.")


def portfolio_page(bankroll, other_exposure):
    st.markdown("## Paper Portfolio")
    st.caption("Session-only practice records. No real orders or presumed fills.")
    queue = st.session_state.get("queue", [])
    exposure = float(st.session_state.get("paper_exposure", 0.0)) + float(other_exposure)
    history = st.session_state.get("paper_history")
    if not isinstance(history, pd.DataFrame):
        history = pd.DataFrame(columns=HISTORY_COLUMNS)
    stats = paper_summary(history)
    c1, c2, c3 = st.columns(3)
    c1.metric("Paper bankroll", f"${bankroll:,.2f}")
    c2.metric("Open exposure", f"${exposure:,.2f}")
    c3.metric("Closed paper positions", stats["closed"])
    if stats["closed"]:
        st.metric("Gross hypothetical P&L (fees excluded)", f"${stats['gross_pnl']:,.2f}")
    else:
        st.info("No settled paper positions yet. ROI, win rate, and profit cannot be inferred from scans.")
    st.markdown("#### Paper approval queue")
    if queue:
        st.dataframe(pd.DataFrame(queue), hide_index=True, use_container_width=True)
    else:
        st.caption("No paper-approved positions.")
    st.markdown("#### Recorded observations and results")
    if not history.empty:
        st.dataframe(history, hide_index=True, use_container_width=True)
        st.download_button("Download paper history CSV", history.to_csv(index=False).encode("utf-8"),
                           file_name="kalshi_paper_history.csv", mime="text/csv", key="sports_portfolio_download")
    else:
        st.caption("No saved history in this session. Use Research to import or export a paper journal.")
    st.caption("History is not stored persistently until you export it. Evaluating a market is not a trade.")
