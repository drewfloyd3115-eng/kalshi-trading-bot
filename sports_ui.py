"""Mobile-first, read-only sports interface. Never places orders or fetches remote data."""
import pandas as pd
import streamlit as st
from html import escape
from datetime import datetime, timezone
from matcher import parse_time

from config import MIN_EDGE_PP
from edge_engine import taker_fee
from pregame_dashboard import eligibility_dashboard
from price_discovery import price_discovery
from paper_history import summary as paper_summary, HISTORY_COLUMNS
from position_ledger import ledger_summary, empty_ledger


PAGES = ["Home", "Opportunities", "Market Detail", "Portfolio", "CFB Model", "Research"]
CARD_COLUMNS = ["league", "event", "outcome_team", "ticker", "side", "fair_pct",
                "ask_cents", "net_edge_pp_1share", "books", "book_spread_pp",
                "oldest_quote_minutes", "quote_quality", "depth_status",
                "research_status", "reason", "kickoff_utc", "kickoff_status",
                "quote_status", "max_entry_cents_1share", "price_drop_needed_cents",
                "depth_best_ask_cents", "depth_edge_pp"]


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
    # price_discovery carries a generic status; audited pregame status must replace it.
    prices = prices.drop(columns=["research_status"], errors="ignore")
    safety = eligibility_dashboard(matches, odds, scan_time, now=now)
    base = matches.drop_duplicates(["ticker", "side"])
    keys = ["ticker", "side"]
    if "league" in base.columns:
        prices = prices.merge(base[keys + ["league"]], on=keys, how="left", validate="many_to_one")
    else:
        prices["league"] = "Unverified"
    if not safety.empty:
        selected = safety[keys + ["research_status", "reason", "kickoff_utc",
                                  "kickoff_status", "quote_status"]].drop_duplicates(keys)
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
    if str(row.get("research_status")) == "DESIGN PREVIEW":
        return "DESIGN PREVIEW — no market data"
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
/* Streamlit normally stacks st.columns vertically on narrow phones.
   Override only the navigation container, never the data or scanner UI. */
.st-key-sports_navigation_grid [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: stretch !important;
    gap: 6px !important;
    width: 100% !important;
}
.st-key-sports_navigation_grid [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 0% !important;
    width: 0 !important;
    min-width: 0 !important;
    max-width: none !important;
}
.st-key-sports_navigation_grid [data-testid="stButton"] {
    width: 100% !important;
}
.st-key-sports_navigation_grid button {
    width: 100%; min-width: 0; min-height: 43px;
    border: 1px solid #254763; border-radius: 11px;
    font-weight: 650; white-space: normal; overflow-wrap: anywhere;
    line-height: 1.15; font-size: .84rem; padding: .35rem .2rem;
}
@media (max-width: 650px) {
    .block-container {padding-top: .85rem; padding-left: 1rem; padding-right: 1rem;}
    .st-key-sports_navigation_grid button {
        font-size: .73rem; min-height: 45px; padding: .32rem .1rem;
    }
    .kl-hero {padding: 12px 14px; margin-bottom: 7px; border-radius: 14px;}
    .kl-title {font-size: 1.65rem; margin: 5px 0;}
    .kl-subtitle {font-size: .82rem; line-height: 1.32;}
    .kl-eyebrow {font-size: .62rem;}
    .kl-pill {padding: 4px 8px; font-size: .68rem;}
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

/* Football-themed opportunity cards are CSS-only and use verified values
   from cached scanner data. No clickable HTML or client-side data fetching. */
.kl-opp-head {
    background: linear-gradient(112deg,#092943,#0a2038);
    border:1px solid #285576; border-radius:15px;
    padding:17px 15px; margin:6px 0 15px;
}
.kl-opp-eyebrow {
    font-size:.70rem; letter-spacing:.15em; color:#74beff;
    font-weight:750; text-transform:uppercase;
}
.kl-opp-headline {color:#f1f7ff; font-size:1.35rem; font-weight:850; margin:3px 0 5px;}
.kl-opp-descr {font-size:.82rem; color:#bed3e9; line-height:1.45;}
.kl-opp-card {
    border:1px solid #244a6b; border-radius:16px;
    background:radial-gradient(ellipse at 100% 0%,#103455 0%,transparent 64%),
               linear-gradient(130deg,#09243d 0%,#071725 100%);
    padding:14px; margin-top:10px; margin-bottom:6px;
    box-shadow:0 5px 12px #030a164d;
}
.kl-opp-titleline {display:flex; align-items:flex-start; gap:12px; justify-content:space-between;}
.kl-opp-name {font-size:1.02rem; font-weight:800; color:#eaf5ff; line-height:1.28;}
.kl-opp-outcome {color:#a9c9e8;font-size:.79rem;margin-top:5px;}
.kl-opp-edge {
    font-size:1.13rem;font-weight:850; white-space:nowrap; text-align:right;
    color:#eaf4ff; border:1px solid #416382; border-radius:9px;
    background:#10304a; padding:5px 8px; line-height:1.15;
}
.kl-opp-edge span {display:block;font-size:.62rem;font-weight:650;color:#a5c3df;margin-top:3px;}
.kl-opp-flag {
    display:inline-block; border:1px solid #4b647c; background:#182b40;
    border-radius:7px;color:#d2e7fa;padding:3px 8px;
    font-size:.70rem;font-weight:750;margin:9px 0;
}
.kl-opp-flag.review {border-color:#b3832f;background:#37290d;color:#ffd58d;}
.kl-opp-flag.blocked {border-color:#805361;background:#321d29;color:#ffb3bd;}
.kl-opp-flag.preview {border-color:#386f99;background:#0d3049;color:#9ddaff;}

/* Cached market detail; two-column cards remain side by side on iPhone. */
.kl-detail-hero {background:linear-gradient(125deg,#0d3455,#071b2d);
 border:1px solid #2e5b80;border-radius:15px;padding:14px;margin:10px 0;}
.kl-detail-eyebrow {font-size:.70rem;letter-spacing:.13em;color:#8bcfff;font-weight:800;}
.kl-detail-name {font-size:1.28rem;font-weight:850;color:#fff;margin:5px 0;}
.kl-detail-outcome {font-size:.83rem;color:#afd0ec;margin:5px 0 10px;}
.kl-detail-pill {display:inline-block;border:1px solid #9b6670;background:#3d212e;
 border-radius:8px;padding:5px 9px;color:#ffbecb;font-weight:800;font-size:.73rem;}
.kl-detail-pill.preview {border-color:#397ab2;background:#123751;color:#9bd9ff;}
.kl-detail-pill.review {border-color:#ae8739;background:#3c2d13;color:#ffe0a2;}
.kl-detail-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:12px 0;}
.kl-detail-stat {background:#082033;border:1px solid #295171;border-radius:12px;padding:12px;min-width:0;}
.kl-detail-stat small {color:#abc9e3;font-size:.70rem;display:block;}
.kl-detail-stat strong {color:#fff;font-weight:850;font-size:1.35rem;display:block;margin:6px 0;}
.kl-detail-stat em {color:#94b7d2;font-size:.66rem;font-style:normal;display:block;}
.kl-detail-panel {background:#081f33;border:1px solid #2c516f;border-radius:13px;
 padding:14px;margin:12px 0;}
.kl-detail-panel b {color:#eff9ff;}
.kl-detail-bar-title {display:flex;justify-content:space-between;color:#bed8eb;font-size:.77rem;margin:9px 0 5px;}
.kl-detail-track {background:#102d46;border-radius:12px;height:10px;overflow:hidden;}
.kl-detail-fill {height:100%;background:linear-gradient(90deg,#1272de,#66bcff);border-radius:12px;}
.kl-detail-fill.ask {background:linear-gradient(90deg,#887542,#ffcd70);}
.kl-detail-checks {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:11px 0;}
.kl-detail-check {border:1px solid #2b4964;border-radius:9px;padding:9px;background:#071a2b;min-width:0;}
.kl-detail-check small {display:block;font-size:.69rem;color:#96b8d3;}
.kl-detail-check strong {font-size:.78rem;color:#eaf7ff;overflow-wrap:anywhere;}
.kl-detail-note {font-size:.76rem;line-height:1.52;color:#bdd6eb;margin-top:10px;}
@media(max-width:650px){.kl-detail-stat{padding:10px}.kl-detail-stat strong{font-size:1.16rem}
.kl-detail-hero{padding:12px}.kl-detail-name{font-size:1.10rem}}

.kl-opp-figures {
    display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
    gap:7px; margin:3px 0 10px;
}
.kl-opp-figure {background:#071b2d;border:1px solid #24435e;border-radius:9px;padding:9px 7px;min-width:0;}
.kl-opp-figure small {display:block;color:#9ab8d6;font-size:.66rem;line-height:1.25;}
.kl-opp-figure strong {display:block;color:#f1f7ff;font-size:1.0rem;margin-top:5px;}
.kl-opp-meta {display:flex;gap:7px;flex-wrap:wrap;margin:8px 0;color:#a8c9e7;font-size:.72rem;}
.kl-opp-meta span {border:1px solid #284561;border-radius:7px;padding:3px 7px;background:#092137;}
.kl-opp-reason {color:#d1deec;font-size:.74rem;line-height:1.5;border-top:1px solid #27415a;padding-top:10px;}
.kl-opp-empty {padding:14px;border:1px dashed #426486;border-radius:12px;
    background:#0b2338;margin-top:12px;color:#acc8e2;font-size:.85rem;}
@media (max-width:650px) {
    .kl-opp-card {padding:12px;border-radius:13px;margin-top:8px;}
    .kl-opp-head {padding:13px;}
    .kl-opp-name {font-size:.92rem;}
    .kl-opp-edge {font-size:1.03rem;}
    .kl-opp-figure {padding:8px 6px;}
    .kl-opp-figure strong {font-size:.96rem;}
}
</style>
""", unsafe_allow_html=True)


def _navigate_to(page):
    """Switch local presentation only. No scanner calls or trading actions."""
    st.session_state["sports_nav"] = page


def navigation():
    """Every destination is visible on phones using native Streamlit buttons."""
    if st.session_state.get("sports_nav") not in PAGES:
        st.session_state["sports_nav"] = "Home"
    for items in (
        [("Home", "Home", "nav_home"),
         ("Opportunities", "Opportunities", "nav_opportunities"),
         ("Market Detail", "Market Detail", "nav_market_detail")],
        [("Portfolio", "Portfolio", "nav_portfolio"),
         ("Research", "Research", "nav_research")],
    ):
        columns = st.columns(len(items), gap="small")
        for col, (label, page, widget_key) in zip(columns, items):
            with col:
                st.button(label, key=widget_key, use_container_width=True,
                          type="primary" if st.session_state["sports_nav"] == page else "secondary",
                          on_click=_navigate_to, args=(page,))
    return st.session_state["sports_nav"]


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
    route = str(ticker) + "|" + str(side)
    st.session_state["sports_selected_route"] = route
    st.session_state["sports_detail_route"] = route
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
    manual_cost = ledger_summary(
        st.session_state.get("position_ledger", empty_ledger()))["open_cost_usd"]
    exposure = (float(st.session_state.get("paper_exposure", 0))
                + float(extra_exposure) + manual_cost)
    a, b, c = st.columns(3)
    a.metric("Paper bankroll", f"${bankroll:,.2f}")
    b.metric("Paper exposure incl. ledger", f"${exposure:,.2f}")
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
    st.warning("NO VERIFIED TRADE. These are ranked estimates, not buy signals or verified executable quotes.")
    st.caption("Displayed odds, edges, and eligibility are snapshots. No observations are approved trades.")



def _display_number(value, digits=1, suffix=""):
    """Printable finite number or a conspicuous missing-value marker."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or not (-1000000 < float(number) < 1000000):
        return "—"
    return f"{float(number):.{digits}f}{suffix}"


def scan_age_label(scan_time, now=None):
    """Show currentness without converting stale prices into approval signals."""
    at = parse_time(scan_time)
    now = now or datetime.now(timezone.utc)
    if not at:
        return "Scan time unknown — not current", False
    seconds = (now - at).total_seconds()
    if seconds < -120:
        return "Scan time inconsistent — not current", False
    if seconds < 0:
        return "Just scanned (clock difference)", True
    if seconds > 300:
        return f"STALE — scanned {int(seconds // 60)}m ago", False
    return f"Scanned {max(0, int(seconds // 60))}m ago", True


def opportunity_card_html(row):
    """HTML view only. Escapes all feed values; never authorizes paper fills."""
    title = escape(str(row.get("event", "Unknown matchup")))
    winning = escape(str(row.get("outcome_team", "Unknown outcome")).title())
    league = escape(str(row.get("league", "Unknown league")))
    side = escape(str(row.get("side", "Unknown side")))
    estimated_edge = pd.to_numeric(row.get("net_edge_pp_1share"), errors="coerce")
    edge_text = f"{float(estimated_edge):+.2f}pp" if pd.notna(estimated_edge) else "—"
    status = research_label(row)
    flagged = "preview" if status.startswith("DESIGN PREVIEW") else ("review" if status.startswith("PRELIMINARY") else "blocked")
    ask = _display_number(row.get("ask_cents"), 1, "¢")
    fair = _display_number(row.get("fair_pct"), 1, "%")
    books = _display_number(row.get("books"), 0)
    disagreement = _display_number(row.get("book_spread_pp"), 2, "pp")
    age = _display_number(row.get("oldest_quote_minutes"), 1, "m")
    depth = escape(str(row.get("depth_status") or "NOT INSPECTED"))
    reason = escape(str(row.get("reason") or "Independent checks required"))
    return f'''
<div class="kl-opp-card">
  <div class="kl-opp-titleline">
    <div>
      <div class="kl-opp-name">{title}</div>
      <div class="kl-opp-outcome">{winning} to win · {league} · {side} route</div>
    </div>
    <div class="kl-opp-edge">{edge_text}<span>Estimated net edge</span></div>
  </div>
  <div class="kl-opp-flag {flagged}">{escape(status)}</div>
  <div class="kl-opp-figures">
    <div class="kl-opp-figure"><small>Indicative ask</small><strong>{ask}</strong></div>
    <div class="kl-opp-figure"><small>Fair estimate</small><strong>{fair}</strong></div>
    <div class="kl-opp-figure"><small>Independent books</small><strong>{books}</strong></div>
  </div>
  <div class="kl-opp-meta"><span>Book spread: {disagreement}</span><span>Oldest quote: {age}</span><span>Depth: {depth}</span></div>
  <div class="kl-opp-reason">Why: {reason}</div>
</div>
'''


def opportunities_page():
    meta, data = _cached_data()
    st.markdown("""
<div class="kl-opp-head">
  <div class="kl-opp-eyebrow">Market research / CFB + NFL</div>
  <div class="kl-opp-headline">Opportunities</div>
  <div class="kl-opp-descr">Ranked winning outcomes, estimated edges and safety checks.
  No recommendations or executable orders.</div>
</div>""", unsafe_allow_html=True)
    if meta:
        age, fresh = scan_age_label(meta.get("time"))
        if fresh:
            st.caption("◷ " + age + " · Cached sportsbook comparisons — no API request")
        else:
            st.warning(age + ". Cached prices cannot be used as current trade quotes.")
    if data.empty:
        if meta:
            st.info("No exact matched winning outcomes in this scan. The card below is a layout preview only.")
        else:
            st.info("No scan saved in this session. This is a design preview, not a market opportunity.")
        st.caption("Card preview · placeholders only · no API credits used")
        preview = {
            "event": "Upcoming matchup placeholder",
            "outcome_team": "No outcome loaded",
            "league": "CFB / NFL", "side": "—",
            "ask_cents": None, "fair_pct": None,
            "net_edge_pp_1share": None, "books": None,
            "book_spread_pp": None, "oldest_quote_minutes": None,
            "depth_status": "NOT INSPECTED", "research_status": "DESIGN PREVIEW",
            "reason": "DESIGN PREVIEW ONLY — no odds, no verified trade"
        }
        st.markdown(opportunity_card_html(preview), unsafe_allow_html=True)
        return

    total = len(data)
    ready = int((data["research_status"] == "REVIEW ONLY — NOT APPROVED").sum())
    blocked = total - ready
    a, b, c = st.columns(3)
    a.metric("Outcomes", total)
    b.metric("Pregame review", ready)
    c.metric("Blocked", blocked)
    st.caption("Pregame review means more verification is required — not an approved trade.")
    league_options = ["All"] + sorted(str(x) for x in data["league"].dropna().unique())
    league = st.selectbox("League", league_options, key="sports_filter_league")
    status = st.selectbox("Verification", ["All", "Pregame review", "Blocked"],
                          key="sports_filter_status")
    order = st.selectbox("Rank by", ["Highest estimated edge", "Closest to +5pp",
                                     "Smallest book disagreement"], key="sports_filter_rank")
    search = st.text_input("Find a game or team", key="sports_filter_search",
                           placeholder="Search cached games")
    if league != "All":
        data = data[data["league"] == league]
    if status == "Pregame review":
        data = data[data["research_status"] == "REVIEW ONLY — NOT APPROVED"]
    elif status == "Blocked":
        data = data[data["research_status"] != "REVIEW ONLY — NOT APPROVED"]
    if search.strip():
        query = search.strip()
        data = data[data["event"].astype(str).str.contains(query, case=False, regex=False, na=False) |
                    data["outcome_team"].astype(str).str.contains(query, case=False, regex=False, na=False)]
    if data.empty:
        st.info("No cached outcomes match your filters.")
        return
    if order == "Smallest book disagreement":
        data = data.sort_values("book_spread_pp", ascending=True, na_position="last")
    elif order == "Closest to +5pp":
        data = data.assign(_gap=(MIN_EDGE_PP - pd.to_numeric(
            data["net_edge_pp_1share"], errors="coerce")).abs()).sort_values(
                "_gap", ascending=True, na_position="last")
    else:
        data = data.sort_values("net_edge_pp_1share", ascending=False, na_position="last")
    st.caption(f"{len(data)} outcomes shown · Best available route per outcome · No live orders")
    for _, row in data.head(25).iterrows():
        st.markdown(opportunity_card_html(row), unsafe_allow_html=True)
        key = str(row["ticker"]) + "|" + str(row["side"])
        # Native button triggers Streamlit navigation only, not API fetching.
        st.button("View contract research →", key="opportunity_detail_" + key,
                  use_container_width=True, on_click=go_to_detail,
                  args=(row["ticker"], row["side"]))
    st.caption("Shown estimates include an indicative one-share taker fee; "
               "actual fills, market rules and settlement are unverified. No trade is approved.")


def detail_panel_html(row, scan_time=None, now=None):
    """No-network, HTML-escaped illustration of cached market research."""
    age, fresh = scan_age_label(scan_time, now=now)
    preview = str(row.get("research_status", "")) == "DESIGN PREVIEW"
    research = research_label(row)
    if preview:
        status, flag = "DESIGN PREVIEW — no live prices", "preview"
    elif not fresh:
        status, flag = "BLOCKED — stale or missing scan", ""
    elif research.startswith("PRELIMINARY"):
        status, flag = "PRELIMINARY — not approved", "review"
    else:
        status, flag = "BLOCKED — no verified trade", ""

    def field(name, fallback="—"):
        value = row.get(name)
        if value is None:
            return fallback
        try:
            if pd.isna(value):
                return fallback
        except (TypeError, ValueError):
            return fallback
        return escape(str(value)) if str(value).strip() else fallback

    fair = pd.to_numeric(row.get("fair_pct"), errors="coerce")
    ask = pd.to_numeric(row.get("ask_cents"), errors="coerce")
    fair_valid = pd.notna(fair) and 0 < float(fair) < 100 and not preview
    ask_valid = pd.notna(ask) and 0 < float(ask) < 100 and not preview
    fair_pct = float(fair) if fair_valid else 0.0
    ask_pct = float(ask) if ask_valid else 0.0
    fair_label = f"{fair_pct:.2f}%" if fair_valid else "—"
    ask_label = f"{ask_pct:.1f}¢" if ask_valid else "—"
    fee = taker_fee(ask_pct, 1) if ask_valid else None
    fee_label = f"{fee:.2f} USD" if fee is not None else "—"
    cost_label = f"{(ask_pct / 100 + fee):.2f} USD" if fee is not None else "—"
    edge = pd.to_numeric(row.get("net_edge_pp_1share"), errors="coerce")
    edge_label = f"{float(edge):+.2f}pp" if pd.notna(edge) and not preview else "—"
    quality = field("quote_quality", "UNVERIFIED")
    reason = field("reason", "Independent verification unavailable")
    return f'''
<div class="kl-detail-hero">
  <div class="kl-detail-eyebrow">{field("league", "CFB / NFL")} · CONTRACT INTELLIGENCE</div>
  <div class="kl-detail-name">{field("event", "Matchup not loaded")}</div>
  <div class="kl-detail-outcome">{field("outcome_team", "No outcome selected")} to win · {field("side")} route</div>
  <div class="kl-detail-outcome">{field("ticker", "No contract selected")}</div>
  <span class="kl-detail-pill {flag}">{escape(status)}</span>
  <div class="kl-detail-note">{escape(age)} · indicative cached market research only</div>
</div>
<div class="kl-detail-grid">
  <div class="kl-detail-stat"><small>Estimated fair chance</small><strong>{fair_label}</strong><em>Sportsbook consensus</em></div>
  <div class="kl-detail-stat"><small>Kalshi ask snapshot</small><strong>{ask_label}</strong><em>Not an executable quote</em></div>
  <div class="kl-detail-stat"><small>Net edge estimate</small><strong>{edge_label}</strong><em>One share, after estimated fee</em></div>
  <div class="kl-detail-stat"><small>Est. cost for 1 share</small><strong>{cost_label}</strong><em>Includes fee estimate: {fee_label}</em></div>
</div>
<div class="kl-detail-panel">
  <b>Estimated probability comparison</b>
  <div class="kl-detail-bar-title"><span>Fair probability estimate</span><span>{fair_label}</span></div>
  <div class="kl-detail-track"><div class="kl-detail-fill" style="width:{fair_pct:.2f}%"></div></div>
  <div class="kl-detail-bar-title"><span>Kalshi ask, as % of payout</span><span>{ask_label}</span></div>
  <div class="kl-detail-track"><div class="kl-detail-fill ask" style="width:{ask_pct:.2f}%"></div></div>
  <div class="kl-detail-note">The difference between these bars does not verify positive EV.
    The fee-adjusted edge depends on an unvalidated probability estimate and hypothetical prices.</div>
</div>
<div class="kl-detail-panel">
  <b>Pregame and quote-quality checks</b>
  <div class="kl-detail-checks">
    <div class="kl-detail-check"><small>Kickoff eligibility</small><strong>{field("kickoff_status","NOT VERIFIED")}</strong></div>
    <div class="kl-detail-check"><small>Quote status</small><strong>{field("quote_status","NOT VERIFIED")}</strong></div>
    <div class="kl-detail-check"><small>Independent books</small><strong>{_display_number(row.get("books"),0)}</strong></div>
    <div class="kl-detail-check"><small>Book disagreement</small><strong>{_display_number(row.get("book_spread_pp"),2,"pp")}</strong></div>
    <div class="kl-detail-check"><small>Oldest quote at scan</small><strong>{_display_number(row.get("oldest_quote_minutes"),1,"m")}</strong></div>
    <div class="kl-detail-check"><small>Depth check</small><strong>{field("depth_status","NOT INSPECTED")}</strong></div>
  </div>
  <div class="kl-detail-note">Kickoff UTC: {field("kickoff_utc","NOT VERIFIED")}<br>Quote quality: {quality}</div>
  <div class="kl-detail-note"><b>Reason:</b> {reason}</div>
</div>
'''


def detail_page():
    meta, data = _cached_data()
    st.markdown("""
<div class="kl-opp-head">
  <div class="kl-opp-eyebrow">Market intelligence / CFB + NFL</div>
  <div class="kl-opp-headline">Market Detail</div>
  <div class="kl-opp-descr">Fair estimates, indicative entry prices, fee breakdowns,
    sportsbook evidence and reasons for rejection. Research only.</div>
</div>""", unsafe_allow_html=True)
    if data.empty:
        st.info("No contract selected. Below is a layout preview, not a real market.")
        preview = {
            "league": "CFB / NFL", "event": "Matchup not loaded",
            "outcome_team": "No outcome selected",
            "ticker": None, "side": None,
            "fair_pct": None, "ask_cents": None, "net_edge_pp_1share": None,
            "books": None, "book_spread_pp": None,
            "oldest_quote_minutes": None, "depth_status": "NOT INSPECTED",
            "kickoff_status": "NOT VERIFIED", "quote_status": "NOT VERIFIED",
            "kickoff_utc": None, "reason": "DESIGN PREVIEW ONLY — no price or contract loaded",
            "research_status": "DESIGN PREVIEW"
        }
        st.markdown(detail_panel_html(preview), unsafe_allow_html=True)
        st.caption("Placeholder values only · no API requests · live trading disabled")
        return

    routes = {str(r["ticker"]) + "|" + str(r["side"]): r for _, r in data.iterrows()}
    keys = list(routes)
    selected = st.session_state.get("sports_selected_route")
    if selected not in keys:
        selected = keys[0]
    if st.session_state.get("sports_detail_route") not in keys:
        st.session_state["sports_detail_route"] = selected
    route = st.selectbox(
        "Select winning outcome / contract", keys, key="sports_detail_route",
        format_func=lambda x: str(routes[x]["event"]) + " — " +
            str(routes[x]["outcome_team"]).title() + " (" + str(routes[x]["side"]) + ")")
    row = routes[route]
    st.markdown(detail_panel_html(row, meta.get("time")), unsafe_allow_html=True)
    st.warning("NO VERIFIED TRADE — research estimates are not actual fills. Live trading disabled.")
    with st.expander("Explain the fee-adjusted estimate"):
        fair = pd.to_numeric(row.get("fair_pct"), errors="coerce")
        ask = pd.to_numeric(row.get("ask_cents"), errors="coerce")
        if pd.notna(fair) and pd.notna(ask) and 0 < float(ask) < 100:
            fee = taker_fee(float(ask), 1)
            net = float(fair) - float(ask) - 100 * fee
            st.write(
                f"Fair estimate {float(fair):.2f}% − ask {float(ask):.1f}pp"
                f" − fee {100*fee:.2f}pp = **{net:+.2f}pp** estimated net edge.")
            st.caption("Generic taker fee, rounded for one share; market-specific fees unverified.")
        else:
            st.caption("No valid estimate is available.")
    with st.expander("Contract research and verification limits"):
        st.write("**Ticker:**", str(row.get("ticker", "—")))
        st.write("**Winning outcome:**", str(row.get("outcome_team", "—")))
        st.write("**Maximum theoretical entry price for +5pp:**",
                 _display_number(row.get("max_entry_cents_1share"), 0, "¢"))
        st.write("**Indicative price drop required:**",
                 _display_number(row.get("price_drop_needed_cents"), 1, "¢"))
        st.write("**Depth status:**", str(row.get("depth_status") or "Not inspected"))
        st.caption("Cached depth was inspected for only selected outcomes. This does not verify an executable price.")
        st.caption("Settlement rules, live kickoff, liquidity, fees, and probability accuracy must be verified separately.")

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
