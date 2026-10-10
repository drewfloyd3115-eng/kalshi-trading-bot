"""Phone-friendly paper-only Kalshi scanner and approval queue."""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from config import DEFAULT_BANKROLL
from risk import evaluate
from edge_engine import no_vig, assess, taker_fee
from outside_odds import fetch_odds
from matcher import compare
from diagnostics import diagnostics
from coverage_funnel import coverage_funnel
from event_audit import audit
from equivalent_routes import equivalent_routes
from route_depth import review_routes
from fee_analysis import fee_analysis
from liquidity import inspect
from integrated_scan import scan_candidates
from paper_journal import journal_rows
from paper_history import import_history, summary as paper_summary, HISTORY_COLUMNS
from scanner import fetch_sports_markets, fetch_orderbook

st.set_page_config(page_title="Kalshi Trade Lab", page_icon="📈", layout="centered")
st.title("Kalshi Trade Lab")
st.caption("Version 2.6 • CFB/NFL research + paper approvals only • LIVE TRADING DISABLED")
st.warning("Market prices are indicative snapshots. Verify executable quotes, fees, liquidity, event rules and live-game timing before any real trade. A quoted price alone does not establish positive EV.")
if "queue" not in st.session_state:
    st.session_state.queue = []
if "paper_exposure" not in st.session_state:
    st.session_state.paper_exposure = 0.0

scan, odds_tab, edge_tab, evaluate_tab, queue_tab = st.tabs(["Market scan", "Outside odds", "Edge lab", "Evaluate", "Paper queue"])
st.subheader("One-tap CFB / NFL paper scan")
st.caption("Fetches Kalshi and sportsbook moneylines, matches pregame contracts, and checks promising depth. One sportsbook API request per league selected; manual tap only.")
quick_league = st.selectbox("Scan league", ["CFB", "NFL"], key="quick_league")
quick_bankroll = st.number_input("Paper bankroll for one-tap scan ($)", min_value=1.0, value=DEFAULT_BANKROLL, key="quick_bankroll")
quick_exposure = st.number_input("Other open exposure ($)", min_value=0.0, value=0.0, key="quick_exposure")
if st.button("Scan Now — paper only", type="primary", key="quick_scan"):
    api_key = st.secrets.get("ODDS_API_KEY", "")
    if not api_key:
        st.error("Add ODDS_API_KEY to Streamlit Secrets.")
    else:
        try:
            with st.spinner("Fetching fresh markets and sportsbook prices..."):
                quick_markets = fetch_sports_markets((quick_league,), 8)
                quick_rows, quick_remaining = fetch_odds(api_key, quick_league)
                quick_odds = pd.DataFrame(quick_rows)
                quick_matches = compare(quick_markets, quick_odds)
            st.session_state.quick_results = {
                "league": quick_league,
                "markets": len(quick_markets),
                "sportsbook_rows": len(quick_odds),
                "matched": len(quick_matches),
                "remaining": quick_remaining,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds")
            }
            st.session_state.quick_diagnostics = diagnostics(quick_markets, quick_odds)
            st.session_state.quick_funnel = coverage_funnel(quick_odds, st.session_state.quick_diagnostics, quick_matches, quick_markets)
            st.session_state.quick_event_audit = audit(quick_markets, quick_odds)
            st.session_state.quick_comparisons = quick_matches
            st.session_state.paper_scan_journal = journal_rows(quick_matches, quick_league, st.session_state.quick_results["time"])
            st.session_state.quick_routes = equivalent_routes(quick_matches)
            st.session_state.quick_fee_analysis = fee_analysis(quick_matches)
            st.session_state.quick_route_depth = review_routes(quick_matches, quick_bankroll, quick_exposure + st.session_state.paper_exposure)
            st.session_state.quick_depth = scan_candidates(
                quick_matches, quick_bankroll,
                quick_exposure + st.session_state.paper_exposure)
        except Exception as exc:
            st.session_state.pop("quick_results", None)
            st.session_state.pop("quick_comparisons", None)
            st.session_state.pop("paper_scan_journal", None)
            st.session_state.pop("quick_routes", None)
            st.session_state.pop("quick_fee_analysis", None)
            st.session_state.pop("quick_route_depth", None)
            st.session_state.pop("quick_diagnostics", None)
            st.session_state.pop("quick_funnel", None)
            st.session_state.pop("quick_event_audit", None)
            st.session_state.pop("quick_depth", None)
            st.error(f"Scan failed (no trade): {exc}")
if "quick_results" in st.session_state:
    summary = st.session_state.quick_results
    st.caption(f"Last one-tap scan UTC: {summary['time']}; free API requests remaining: {summary['remaining'] or 'unknown'}")
    a,b,c = st.columns(3)
    a.metric("Kalshi markets", summary["markets"])
    b.metric("Sportsbook rows", summary["sportsbook_rows"])
    c.metric("Matched sides", summary["matched"])
    st.subheader("Paper scan decision")
    st.caption("Risk caps: 1% per position and 3% total open exposure; $5 and $15 respectively at a $500 bankroll.")
    st.caption("Fees and settlement rules are not independently verified per contract. No real-money recommendations.")
    if summary["matched"] == 0:
        st.warning("NO TRADE: no safe matches. Check league, game start times, name mappings and quote freshness.")
    elif st.session_state.quick_depth.empty:
        st.info("NO TRADE: no preliminary match clears the +5pp edge filter.")
    else:
        st.dataframe(st.session_state.quick_depth, hide_index=True, use_container_width=True)
    if not st.session_state.quick_comparisons.empty:
        best = st.session_state.quick_comparisons.iloc[0]
        st.metric("Best preliminary edge", "{:+.2f} pp".format(best["net_edge_pp_1share"]))
        st.caption("Leading outcome: {} | {} | ask {} cents. Not executable or fee-verified.".format(best["outcome_team"],best["side"],best["ask_cents"]))
        st.subheader("Best preliminary edges")
        compact=st.session_state.quick_comparisons.head(10)[["outcome_team","side","ask_cents","fair_pct","net_edge_pp_1share"]].copy()
        compact.columns=["Team","Side","Ask ¢","Fair %","Edge pp"]
        st.dataframe(compact, hide_index=True, use_container_width=True)
        with st.expander("Full comparison data — export"):
            st.dataframe(st.session_state.quick_comparisons, hide_index=True, use_container_width=True)
    with st.expander("Paper scan journal — export CSV"):
        st.caption("One indicative route per winning outcome. Session-only; download the CSV to preserve it. No trades are placed and no results are settled.")
        journal = st.session_state.get("paper_scan_journal", pd.DataFrame())
        st.dataframe(journal, hide_index=True, use_container_width=True)
        st.download_button("Download paper scan CSV", journal.to_csv(index=False).encode("utf-8"), file_name="kalshi_paper_scan.csv", mime="text/csv", disabled=journal.empty)
    with st.expander("Equivalent outcome routes — indicative prices only"):
        st.caption("Groups YES and NO contracts paying on the same team. Depth, settlement terms and fees are NOT verified.")
        st.dataframe(st.session_state.get("quick_routes", pd.DataFrame()), hide_index=True, use_container_width=True)
    with st.expander("Fee sensitivity and maximum entry price — estimates"):
        st.caption("Compares ten-share single-order fee with separately rounded fees and calculates the highest whole-cent ask satisfying +5pp. Assumes general taker schedule; special market fees may differ.")
        st.dataframe(st.session_state.get("quick_fee_analysis", pd.DataFrame()), hide_index=True, use_container_width=True)
    with st.expander("Order-book route comparison — paper only"):
        st.caption("Checks up to three winning outcomes, both contract routes, maximum ten shares each. Fees are estimates and no trades are verified.")
        st.dataframe(st.session_state.get("quick_route_depth", pd.DataFrame()), hide_index=True, use_container_width=True)
    st.caption("v1.7 sportsbook consensus: unique bookmaker IDs, same kickoff, fresh quotes and true median for even book counts.")
    st.caption("Coverage diagnostics use expanded aliases. Trade matching now requires exact opponents, event date and YES outcome label; uncertain games are excluded.")
    with st.expander("Full sportsbook coverage funnel — all games"):
        st.caption("Includes sportsbook games without matched contracts. Candidate events are not verified matches; see matched-sides metric separately.")
        st.dataframe(st.session_state.get("quick_funnel", pd.DataFrame()), hide_index=True, use_container_width=True)
    with st.expander("Coverage diagnostics — why games were excluded"):
        st.dataframe(st.session_state.get("quick_diagnostics", pd.DataFrame()), hide_index=True, use_container_width=True)
    with st.expander("Event and outcome audit — export for review"):
        st.caption("Possible game/event matches only. Outcome and settlement rules are not independently verified.")
        st.dataframe(st.session_state.get("quick_event_audit", pd.DataFrame()), hide_index=True, use_container_width=True)
    with st.expander("Quote rejection audit — matched games"):
        st.caption("Counts stale/future, kickoff mismatch, outcome mismatch, duplicate book and invalid odds for games with at least two valid books. Excluded games remain absent.")
        st.dataframe(st.session_state.quick_comparisons[[c for c in ["event","ticker","side","books","rejected_quotes","rejection_breakdown"] if c in st.session_state.quick_comparisons.columns]], hide_index=True, use_container_width=True)
    with st.expander("Sportsbook probability quality audit"):
        st.caption("Per-book no-vig estimates, consensus spread, and oldest quote age. A wide spread signals disagreement, not confirmed value.")
        st.dataframe(st.session_state.quick_comparisons, hide_index=True, use_container_width=True)
    with st.expander("Preliminary matched comparisons"):
        st.dataframe(st.session_state.quick_comparisons, hide_index=True, use_container_width=True)
    st.warning("NO VERIFIED TRADE. Quotes and fees are estimates; injury/news, settlement rules and final synchronization are not validated. No orders placed.")
st.subheader("Paper history — import and export")
st.caption("Import saved paper journal CSVs without making sportsbook API calls. Observations are not paper fills. No settlement or profit is inferred from an observed quote.")
if "paper_history" not in st.session_state:
    st.session_state.paper_history = pd.DataFrame(columns=HISTORY_COLUMNS)
imports=st.file_uploader("Import prior paper scan or history CSVs",type=["csv"],accept_multiple_files=True,key="history_imports")
if st.button("Import selected CSVs — offline",disabled=not imports):
    try:
        incoming=[import_history(f.getvalue()) for f in imports]
        merged=pd.concat([st.session_state.paper_history]+incoming,ignore_index=True)
        st.session_state.paper_history=import_history(merged.to_csv(index=False).encode("utf-8"))
        st.success("Imported saved paper observations. No fills or settlements assumed.")
    except Exception as exc:
        st.error("Import rejected: {}".format(exc))
if "paper_scan_journal" in st.session_state and not st.session_state.paper_scan_journal.empty:
    if st.button("Add current scan to paper history — offline"):
        merged=pd.concat([st.session_state.paper_history,import_history(st.session_state.paper_scan_journal.to_csv(index=False).encode("utf-8"))],ignore_index=True)
        st.session_state.paper_history=import_history(merged.to_csv(index=False).encode("utf-8"))
        st.success("Current scan saved to this session. Download the history CSV to keep it.")
history=st.session_state.paper_history
stats=paper_summary(history)
a,b,c=st.columns(3)
a.metric("Observed outcomes",stats["observations"])
b.metric("Paper fills",stats["paper_fills"])
c.metric("Closed paper positions",stats["closed"])
if stats["closed"]:
    st.metric("Gross hypothetical P&L (fees excluded)", "${:.2f}".format(stats["gross_pnl"]))
else:
    st.info("No closed paper positions. Win rate and hypothetical P&L are not available.")
with st.expander("Paper history records — offline"):
    st.dataframe(history,hide_index=True,use_container_width=True)
st.download_button("Download combined paper history CSV",history.to_csv(index=False).encode("utf-8"),file_name="kalshi_paper_history.csv",mime="text/csv",disabled=history.empty)
st.caption("CSV history is session-only until downloaded. Paper fills require independent price/depth verification; settled results require external confirmation. No real orders.")
st.divider()

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

with odds_tab:
    st.subheader("Free-tier sportsbook odds")
    st.caption("The Odds API: independent US sportsbook moneylines. Fetch only when requested to conserve free credits.")
    key = st.secrets.get("ODDS_API_KEY", "")
    if not key:
        st.warning("Outside odds are not connected. Add ODDS_API_KEY in Streamlit app settings → Secrets. Never put the key in GitHub or chat.")
    odds_league = st.selectbox("League", ["CFB", "NFL"], key="odds_league")
    if st.button("Fetch outside moneylines", disabled=not bool(key)):
        try:
            rows, remaining = fetch_odds(key, odds_league)
            st.session_state.outside_odds = pd.DataFrame(rows)
            st.session_state.odds_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            st.session_state.odds_remaining = remaining
        except Exception as exc:
            st.error(str(exc))
    if "outside_odds" in st.session_state:
        st.caption(f"Retrieved UTC: {st.session_state.odds_at}; free API requests remaining: {st.session_state.odds_remaining or 'unknown'}")
        st.dataframe(st.session_state.outside_odds, hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("Match sportsbook lines to Kalshi")
    st.caption("Pregame moneylines only. Requires at least two independent, recently updated sportsbooks and an unambiguous team match.")
    if st.button("Compare cached market and odds snapshots"):
        if "markets" not in st.session_state or "outside_odds" not in st.session_state:
            st.warning("First run Market scan, then fetch Outside odds for the same league.")
        else:
            try:
                matched = compare(st.session_state.markets, st.session_state.outside_odds)
                st.session_state.matched = matched
                if matched.empty:
                    st.warning("NO VERIFIED EDGE: no safe matches. This may reflect missing team-name mappings, started games or stale odds.")
                else:
                    st.metric("Preliminary comparisons", len(matched))
                    st.dataframe(matched, hide_index=True, use_container_width=True)
                    st.warning("These are preliminary one-share estimates only. Liquidity, precise fees, line movement, injuries and immediate rechecks are NOT validated. DO NOT EXECUTE.")
            except Exception as exc:
                st.error(f"Matching failed: {exc}")
    st.divider()
    st.subheader("Integrated paper scanner")
    st.caption("Checks only preliminary matches with at least +5pp estimated edge. Limited to five fresh order-book lookups; no automatic orders.")
    scan_bankroll = st.number_input("Scanner paper bankroll ($)", min_value=1.0, value=DEFAULT_BANKROLL, key="scan_bankroll")
    scan_exposure = st.number_input("Other open exposure for scanner ($)", min_value=0.0, value=0.0, key="scan_exposure")
    if st.button("Run integrated paper scan"):
        if "matched" not in st.session_state or st.session_state.matched.empty:
            st.warning("Run a fresh market scan, fetch sportsbook odds, and compare markets first.")
        else:
            try:
                from datetime import datetime, timezone
                def recent(key, minutes):
                    timestamp = datetime.fromisoformat(st.session_state.get(key, "2000-01-01T00:00:00+00:00").replace("Z","+00:00"))
                    return (datetime.now(timezone.utc)-timestamp).total_seconds() <= minutes*60
                if not recent("snapshot_at", 5) or not recent("odds_at", 5):
                    st.warning("NO TRADE: market or sportsbook snapshots are older than 5 minutes. Refresh both and rerun comparison.")
                else:
                    results = scan_candidates(st.session_state.matched, scan_bankroll,
                                              scan_exposure + st.session_state.paper_exposure)
                    if results.empty:
                        st.info("NO TRADE: no preliminary match clears +5pp to warrant liquidity lookup.")
                    else:
                        st.dataframe(results, hide_index=True, use_container_width=True)
                    st.warning("PAPER RESEARCH ONLY. Fees are estimated; injury status, market rules and fully synchronized sportsbook quotes remain unverified. No orders placed.")
            except Exception as exc:
                st.error(f"Integrated scan failed: {exc}")
    st.divider()
    st.subheader("Recheck executable liquidity")
    st.caption("Choose an exact matched ticker and side. This fetches a fresh public order book; it does not place an order.")
    depth_check_ticker = st.text_input("Ticker to recheck", key="depth_check_ticker")
    depth_check_side = st.selectbox("Side to buy", ["YES", "NO"], key="depth_check_side")
    depth_check_shares = st.number_input("Shares to inspect", min_value=1, max_value=1000, value=5, key="depth_check_shares")
    if st.button("Recheck depth and estimated cost"):
        try:
            result = inspect(depth_check_ticker.strip(), depth_check_side, int(depth_check_shares))
            st.json(result)
            st.warning("NO VERIFIED TRADE: this order-book snapshot is not an execution instruction. Independent odds, injuries, timing, exact fees and edge must be rechecked.")
        except Exception as exc:
            st.error(f"Liquidity recheck failed: {exc}")
    st.info("NO VERIFIED TRADE. This research comparison cannot issue BUY instructions.")

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
