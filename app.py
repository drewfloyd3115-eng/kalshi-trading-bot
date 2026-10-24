"""Phone-friendly paper-only Kalshi scanner and approval queue."""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from config import DEFAULT_BANKROLL
from risk import evaluate
from edge_engine import no_vig, assess, taker_fee
from outside_odds import fetch_odds
from matcher import compare, parse_time
from team_names import normalized
from diagnostics import diagnostics
from coverage_funnel import coverage_funnel
from discovery_report import discovery_report
from price_discovery import price_discovery
from scan_monitor import scan_changes
from snapshot_backup import export_snapshot, import_snapshot
from event_audit import audit
from equivalent_routes import equivalent_routes
from route_depth import review_routes
from fee_analysis import fee_analysis
from liquidity import inspect
from integrated_scan import scan_candidates
from paper_journal import journal_rows
from paper_history import import_history, summary as paper_summary, HISTORY_COLUMNS
from contract_validation import validate_contract
from inspection_diagnostics import explain
from pregame_dashboard import eligibility_dashboard
from scanner import fetch_sports_markets, fetch_orderbook
from position_ledger import empty_ledger, validate_ledger, ledger_summary
# Streamlit reruns app.py but can retain previously-imported helper modules
# in the same Python worker after a GitHub deployment. Refresh presentation
# functions explicitly so UI version labels and screens cannot diverge.
import importlib
import sports_ui
importlib.reload(sports_ui)
import market_audit
importlib.reload(market_audit)
import exit_liquidity
importlib.reload(exit_liquidity)
import exit_review_ui
importlib.reload(exit_review_ui)
import portfolio_ui
importlib.reload(portfolio_ui)
from sports_ui import (PAGES, add_styles, header, home_overview, opportunities_page,
                       detail_page)
from portfolio_ui import portfolio_page

def sportsbook_api_key():
    """Offline research pages must load without a configured sportsbook secret."""
    try:
        return st.secrets.get("ODDS_API_KEY", "")
    except FileNotFoundError:
        return ""


st.set_page_config(page_title="Kalshi Trade Lab", page_icon="📈", layout="centered")
add_styles()
header()
st.caption("Sports UI preview 2.2 · NO-side bid validation and fee metadata · PAPER ONLY · Live trading disabled.")

# Streamlit's native pills wrap on mobile; st.columns always stack at phone width.
# One single-select widget controls every view without CSS-dependent navigation.
# This never fetches odds or places orders.
if st.session_state.get("sports_nav") not in PAGES:
    st.session_state["sports_nav"] = "Home"
page = st.pills("Navigate", PAGES, selection_mode="single", default="Home",
                key="sports_nav", label_visibility="collapsed") or "Home"

if "queue" not in st.session_state:
    st.session_state.queue = []
if "paper_exposure" not in st.session_state:
    st.session_state.paper_exposure = 0.0

# A manual paper fill is a position, unlike an approval queue item.
# Count both against all existing entry/scanner risk limits.
if "position_ledger" not in st.session_state:
    st.session_state.position_ledger = empty_ledger()
try:
    st.session_state.position_ledger = validate_ledger(st.session_state.position_ledger)
except ValueError:
    st.error("Invalid paper position ledger. Import a valid backup before evaluating trades.")
    st.stop()


def manual_position_exposure():
    return ledger_summary(st.session_state.position_ledger)["open_cost_usd"]


def total_research_exposure(other=0.0):
    return float(other) + float(st.session_state.paper_exposure) + manual_position_exposure()


if page == "Home":
    st.subheader("One-tap CFB / NFL paper scan")
    st.caption("Manual sportsbook comparison · One Odds API request per scan · Paper research only.")
    quick_league = st.selectbox("Scan league", ["CFB", "NFL"], key="quick_league")
    with st.expander("Paper bankroll & exposure settings", expanded=False):
        quick_bankroll = st.number_input("Paper bankroll for one-tap scan ($)", min_value=1.0, value=DEFAULT_BANKROLL, key="quick_bankroll")
        quick_exposure = st.number_input("Other open exposure ($)", min_value=0.0, value=0.0, key="quick_exposure")
        st.caption("Position limit: 1% of bankroll; total exposure limit: 3%. Settings do not make any API requests.")
    if st.button("Scan Now — paper only", type="primary", key="quick_scan", use_container_width=True):
        api_key = sportsbook_api_key()
        if not api_key:
            st.error("Add ODDS_API_KEY to Streamlit Secrets.")
        else:
            try:
                with st.spinner("Fetching fresh markets and sportsbook prices..."):
                    quick_markets = fetch_sports_markets((quick_league,), 8)
                    quick_rows, quick_remaining = fetch_odds(api_key, quick_league)
                    quick_odds = pd.DataFrame(quick_rows)
                    quick_matches = compare(quick_markets, quick_odds)
                scan_finished_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
                scan_result = {
                    "league": quick_league,
                    "markets": len(quick_markets),
                    "sportsbook_rows": len(quick_odds),
                    "matched": len(quick_matches),
                    "remaining": quick_remaining,
                    "time": scan_finished_at
                }
                st.session_state.quick_results = scan_result
                st.session_state.quick_diagnostics = diagnostics(quick_markets, quick_odds)
                st.session_state.quick_funnel = coverage_funnel(quick_odds, st.session_state.quick_diagnostics, quick_matches, quick_markets)
                st.session_state.quick_event_audit = audit(quick_markets, quick_odds)
                st.session_state.quick_comparisons = quick_matches
                st.session_state.quick_eligibility = eligibility_dashboard(quick_matches, quick_odds, st.session_state.quick_results["time"])
                st.session_state.quick_odds_cache = quick_odds
                st.session_state.quick_markets_cache = quick_markets
                st.session_state.paper_scan_journal = journal_rows(quick_matches, quick_league, st.session_state.quick_results["time"])
                st.session_state.quick_routes = equivalent_routes(quick_matches)
                st.session_state.quick_fee_analysis = fee_analysis(quick_matches)
                st.session_state.quick_route_depth = review_routes(quick_matches, quick_bankroll, total_research_exposure(quick_exposure))
                st.session_state.quick_depth = scan_candidates(
                    quick_matches, quick_bankroll,
                    total_research_exposure(quick_exposure))
                # Commit history only after the complete scan succeeds, separately per league.
                snapshots = st.session_state.setdefault("completed_scan_snapshots", {})
                old = snapshots.get(quick_league)
                if not old:
                    old = st.session_state.get("manual_previous_snapshots", {}).get(quick_league)
                st.session_state.previous_comparisons = old["matches"].copy() if old else pd.DataFrame()
                st.session_state.previous_scan_time = old["time"] if old else None
                snapshots[quick_league] = {"time": scan_finished_at, "matches": quick_matches.copy()}

            except Exception as exc:
                st.session_state.pop("previous_comparisons", None)
                st.session_state.pop("previous_scan_time", None)
                st.session_state.pop("quick_results", None)
                st.session_state.pop("quick_odds_cache", None)
                st.session_state.pop("quick_markets_cache", None)
                st.session_state.pop("quick_comparisons", None)
                st.session_state.pop("quick_eligibility", None)
                st.session_state.pop("paper_scan_journal", None)
                st.session_state.pop("quick_routes", None)
                st.session_state.pop("quick_fee_analysis", None)
                st.session_state.pop("quick_route_depth", None)
                st.session_state.pop("quick_diagnostics", None)
                st.session_state.pop("quick_funnel", None)
                st.session_state.pop("quick_event_audit", None)
                st.session_state.pop("quick_depth", None)
                st.error(f"Scan failed (no trade): {exc}")
    with st.expander("Scan history backup — no API credits", expanded=False):
        st.caption("Save each successful scan as a CSV. If this browser session resets, import the earlier snapshot to compare it with the next completed scan. Import never approves trades.")
        saved = st.session_state.get("completed_scan_snapshots", {}).get(quick_league)
        if saved:
            st.download_button("Download latest scan snapshot CSV",
                export_snapshot(saved["matches"], quick_league, saved["time"]),
                file_name=f"kalshi_{quick_league.lower()}_snapshot.csv", mime="text/csv")
        else:
            st.info("No completed scan stored for this league in this session.")
        uploaded = st.file_uploader("Import previous snapshot CSV", type=["csv"], key="snapshot_import")
        if uploaded is not None and st.button("Use imported snapshot as previous scan", key="use_snapshot"):
            try:
                current_time = st.session_state.get("quick_results", {}).get("time") if st.session_state.get("quick_results", {}).get("league") == quick_league else None
                restored = import_snapshot(uploaded.getvalue(), quick_league, current_time)
                st.session_state.setdefault("manual_previous_snapshots", {})[quick_league] = restored
                st.success("Previous snapshot restored for research comparison only. No sportsbook request used.")
            except (ValueError, pd.errors.ParserError, UnicodeError) as exc:
                st.error(f"Snapshot rejected: {exc}")


    home_overview(quick_bankroll, quick_exposure)
elif page == "Opportunities":
    opportunities_page()
elif page == "Market Detail":
    detail_page()
elif page == "Portfolio":
    portfolio_page(float(st.session_state.get("quick_bankroll", DEFAULT_BANKROLL)),
                   float(st.session_state.get("quick_exposure", 0.0)))
elif page == "CFB Model":
    from cfb_model.ui import render_model_ui
    render_model_ui()
else:
    if "quick_results" in st.session_state:
        summary = st.session_state.quick_results
        st.caption(f"Last one-tap scan UTC: {summary['time']}; free API requests remaining: {summary['remaining'] or 'unknown'}")
        a,b,c = st.columns(3)
        a.metric("Kalshi markets", summary["markets"])
        b.metric("Sportsbook rows", summary["sportsbook_rows"])
        c.metric("Matched sides", summary["matched"])
        # Single mobile-first research decision panel. Re-evaluate on every rerun.
        st.subheader("Scan decision — paper research only")
        latest_eligibility = eligibility_dashboard(
            st.session_state.get("quick_comparisons"),
            st.session_state.get("quick_odds_cache"), summary.get("time"))
        latest_prices = price_discovery(st.session_state.get("quick_comparisons"),
                                        st.session_state.get("quick_route_depth"))
        unique_outcomes = (latest_prices[latest_prices["best_route_for_outcome"]]
                           if not latest_prices.empty else pd.DataFrame())
        review_count = (int((latest_eligibility["research_status"] != "BLOCKED").sum())
                        if not latest_eligibility.empty else 0)
        passing_count = (int((latest_eligibility["edge_status"] == "PASSES PRELIMINARY FILTER").sum())
                         if not latest_eligibility.empty else 0)
        st.warning("NO VERIFIED TRADE — research estimates are not executable orders.")
        summary_a, summary_b, summary_c = st.columns(3)
        summary_a.metric("Distinct outcomes", len(unique_outcomes))
        summary_b.metric("Preliminary +5pp sides", passing_count)
        summary_c.metric("Pregame review sides", review_count)
        if latest_eligibility.empty:
            st.caption("No exact matched pregame contracts with sufficient sportsbook evidence.")
        else:
            reasons = latest_eligibility["reason"].fillna("").astype(str)
            kickoff_blocked = int(reasons.str.contains("kickoff", case=False).sum())
            quote_blocked = int(reasons.str.contains("scan|quote|book", case=False).sum())
            st.caption(f"Safety checks: {kickoff_blocked} sides lack a verified future kickoff; "
                       f"{quote_blocked} have quote or scan-quality concerns. "
                       "Settlement terms, live executable depth, and complete fees remain unverified.")
            with st.expander("Why each contract is blocked or under review"):
                st.dataframe(latest_eligibility, hide_index=True, use_container_width=True)
        st.caption("The dashboard recalculates eligibility from cached data whenever the page reruns. "
                   "Viewing it does not use Odds API credits.")
        st.subheader("Opportunity discovery — coverage audit")
        st.caption("Uses this scan's cached Kalshi markets and sportsbook quotes. No additional Odds API requests.")
        coverage_metrics, coverage_table = discovery_report(
            st.session_state.get("quick_markets_cache"),
            st.session_state.get("quick_odds_cache"),
            st.session_state.get("quick_funnel"),
            st.session_state.get("quick_comparisons"))
        d1, d2, d3 = st.columns(3)
        d1.metric("Matched games", coverage_metrics["matched_games"])
        d2.metric("Unmatched candidates", coverage_metrics["candidate_games"])
        d3.metric("No exact event", coverage_metrics["excluded_games"])
        with st.expander("Why games were missed — download coverage CSV"):
            st.caption("Candidates are diagnostic only. Never assume a similar team name or listed market is a valid match.")
            if coverage_table.empty:
                st.info("No coverage data for this scan.")
            else:
                st.dataframe(coverage_table, hide_index=True, use_container_width=True)
                st.download_button("Download coverage audit CSV",
                    coverage_table.to_csv(index=False).encode("utf-8"),
                    file_name="kalshi_coverage_audit.csv", mime="text/csv")
        st.subheader("Price discovery 3.9 — best outcome routes and quote quality")
        st.caption("Cached quotes only. One-share fee estimate; max entry is theoretical, not an available order-book price. No extra sportsbook requests.")
        price_table = price_discovery(st.session_state.get("quick_comparisons"), st.session_state.get("quick_route_depth"))
        if price_table.empty:
            st.info("No eligible exact matched sides to price.")
        else:
            closest = price_table.iloc[0]
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("Compared sides", len(price_table))
            pc2.metric("Closest net edge", f"{closest['net_edge_pp_1share']:+.2f}pp")
            pc3.metric("Gap to +5pp", f"{closest['gap_to_threshold_pp']:.2f}pp")
            best_prices = price_table[price_table["best_route_for_outcome"]].copy()
            st.caption(f"{len(best_prices)} distinct winning outcomes from {len(price_table)} contract-side routes. Order-book snapshots cover only selected outcomes; all others remain uninspected.")
            st.dataframe(best_prices, hide_index=True, use_container_width=True)
            with st.expander("All YES/NO routes — threshold distance, book quality, depth, CSV", expanded=False):
                st.caption("A smaller gap is not approval. Wide sportsbook disagreement and old quotes weaken confidence; verify contract fees, depth, kickoff and settlement separately.")
                st.dataframe(price_table, hide_index=True, use_container_width=True)
                st.download_button("Download price discovery CSV",
                    price_table.to_csv(index=False).encode("utf-8"),
                    file_name="kalshi_price_discovery.csv", mime="text/csv")
        # Imported backups can restore comparison even after a session reset.
        restored = st.session_state.get("manual_previous_snapshots", {}).get(summary.get("league"))
        if restored and parse_time(restored["time"]) and parse_time(summary.get("time")) and parse_time(restored["time"]) < parse_time(summary.get("time")):
            if not st.session_state.get("previous_scan_time"):
                st.session_state.previous_comparisons = restored["matches"].copy()
                st.session_state.previous_scan_time = restored["time"]
        st.subheader("Manual opportunity monitor 4.3 — scan integrity and backup")
        st.caption("Compares the latest two successful scans in this browser session. No background checks or extra API calls. Scan Now consumes the usual sportsbook request.")
        changes = scan_changes(st.session_state.get("previous_comparisons"), st.session_state.get("quick_comparisons"), eligibility_dashboard(st.session_state.get("quick_comparisons"), st.session_state.get("quick_odds_cache"), summary.get("time")), st.session_state.get("previous_scan_time"), summary.get("time"))
        if changes.empty:
            st.info("No comparison data. No verified trade.")
        else:
            st.caption(f"Previous completed scan: {st.session_state.get('previous_scan_time') or 'not recorded'} | Current completed scan: {summary.get('time') or 'not recorded'}")
            if not bool(changes["independent_scans"].iloc[0]):
                st.warning("Two independently timestamped successful scans not confirmed. No new opportunity flags permitted.")
            if not bool(changes["scan_fresh_now"].iloc[0]):
                st.warning("Current scan is stale. Refreshing this page does not refresh sportsbook quotes.")
            known = changes["previous_edge_pp"].notna()
            crossings = int((changes["threshold_crossing"] == "NEW +5pp — REVIEW ONLY").sum())
            m1, m2, m3 = st.columns(3)
            m1.metric("Compared with prior", int(known.sum()))
            m2.metric("New +5pp research flags", crossings)
            m3.metric("Kickoff/quote blocked", int(changes["research_status"].str.startswith("BLOCKED").sum()))
            if not known.any():
                st.caption("First successful scan in this session. Run Scan Now again later to compare price movement.")
            st.dataframe(changes, hide_index=True, use_container_width=True)
            st.download_button("Download scan changes CSV", changes.to_csv(index=False).encode("utf-8"),
                               file_name="kalshi_scan_changes.csv", mime="text/csv")
        st.warning("No automatic alerts or real orders. A +5pp flag is not a verified opportunity; kickoff, quote freshness, depth, fees and rules must all be rechecked.")
        st.subheader("Opportunity dashboard — research only")
        st.caption("Top five preliminary matches. Cached data only; no extra sportsbook requests.")
        eligibility = eligibility_dashboard(st.session_state.get("quick_comparisons"), st.session_state.get("quick_odds_cache"), summary.get("time"))
        st.session_state.quick_eligibility = eligibility
        if eligibility.empty:
            st.info("No exact matched sides. NO VERIFIED TRADE.")
        else:
            ranked = eligibility.sort_values("net_edge_pp_1share", ascending=False, na_position="last").reset_index(drop=True)
            edges = pd.to_numeric(ranked["net_edge_pp_1share"], errors="coerce")
            passing = int((edges >= 5).sum())
            blocked = int((ranked["research_status"] == "BLOCKED").sum())
            x, y, z = st.columns(3)
            x.metric("Matched", len(ranked))
            y.metric("+5pp", passing)
            z.metric("Blocked", blocked)
            prices = st.session_state.get("quick_comparisons", pd.DataFrame())
            # YES on one team and NO on its opponent can represent the same winner.
            # Group by normalized winning team within the event, not by displayed side.
            ranked["_outcome_key"] = ranked["outcome_team"].astype(str).str.strip().str.lower()
            ranked["_event_key"] = ranked["event"].astype(str).str.strip().str.lower()
            unique_routes = ranked.sort_values("net_edge_pp_1share", ascending=False, na_position="last").drop_duplicates(["_event_key", "_outcome_key"]).head(5)
            st.caption("Showing up to five distinct winning outcomes; alternate YES/NO routes remain in the full table.")
            for i, (_, row) in enumerate(unique_routes.iterrows()):
                edge = pd.to_numeric(row["net_edge_pp_1share"], errors="coerce")
                label = "{:+.2f}pp".format(edge) if pd.notna(edge) else "N/A"
                matched_price = prices[(prices["ticker"] == row["ticker"]) & (prices["side"] == row["side"])] if isinstance(prices, pd.DataFrame) and not prices.empty else pd.DataFrame()
                ask_value = pd.to_numeric(matched_price.iloc[0]["ask_cents"], errors="coerce") if not matched_price.empty else float("nan")
                fair_value = pd.to_numeric(matched_price.iloc[0]["fair_pct"], errors="coerce") if not matched_price.empty and "fair_pct" in matched_price.columns else float("nan")
                ask = "{:.1f}¢".format(ask_value) if pd.notna(ask_value) else "unavailable"
                fair = "{:.2f}%".format(fair_value) if pd.notna(fair_value) else "unavailable"
                group = ranked[(ranked["_event_key"] == row["_event_key"]) & (ranked["_outcome_key"] == row["_outcome_key"])]
                with st.expander("{} — {} to win | {}".format(row["event"], str(row["outcome_team"]).title(), label), expanded=(i == 0)):
                    st.caption("Best preliminary route: {} | Side: {}".format(str(row["outcome_team"]).title(), row["side"]))
                    # One-share maximum entry price, including the same estimated taker fee
                    # used in the preliminary edge calculation. NOT an executable quote.
                    max_ask = None
                    if pd.notna(fair_value):
                        for candidate_cents in range(99, 0, -1):
                            estimated_fee_cents = round(taker_fee(candidate_cents, 1) * 100)
                            if fair_value - candidate_cents - estimated_fee_cents >= 5 - 1e-9:
                                max_ask = candidate_cents
                                break
                    # A two-column grid stays compact in narrow iPhone Safari viewports.
                    # Escape dynamic labels before inserting into the read-only HTML card.
                    from html import escape
                    max_entry_label = "{}¢".format(max_ask) if max_ask is not None else "None"
                    tiles = [("Fair chance", fair), ("Ask", ask), ("Net edge", label), ("Max entry for +5pp", max_entry_label)]
                    tile_html = "".join(
                        '<div style="min-width:0;padding:10px 12px;border:1px solid #7775;border-radius:10px;">'
                        '<div style="font-size:0.78rem;opacity:.75;margin-bottom:5px;">{}</div>'
                        '<div style="font-size:clamp(1.15rem,5vw,1.7rem);font-weight:650;line-height:1.2;overflow-wrap:anywhere;">{}</div>'
                        '</div>'.format(escape(k), escape(str(v))) for k, v in tiles
                    )
                    st.markdown('<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:10px 0 14px;">' + tile_html + '</div>', unsafe_allow_html=True)
                    st.caption("Maximum entry is a calculated one-share threshold, not an available quote.")
                    st.caption("General fee estimate only. Market-specific fees, depth and execution are unverified.")
                    st.write("**Status:** {} — {}".format(row["research_status"], row["reason"]))
                    with st.expander("Contract details and data quality"):
                        st.write("Ticker: {} | Side: {}".format(row["ticker"], row["side"]))
                        st.write("Kickoff: {} | Books: {} | Quotes: {}".format(row["kickoff_status"], row["books"], row["quote_status"]))
                    if len(group) > 1:
                        with st.expander("Other routes to the same outcome"):
                            st.dataframe(group.drop(columns=["_event_key", "_outcome_key"]), hide_index=True, use_container_width=True)
            ranked = ranked.drop(columns=["_event_key", "_outcome_key"])
            with st.expander("All matches and CSV export"):
                st.dataframe(ranked, hide_index=True, use_container_width=True)
                st.download_button("Export pregame eligibility CSV", ranked.to_csv(index=False).encode("utf-8"), file_name="kalshi_pregame_eligibility.csv", mime="text/csv")
        st.subheader("Paper scan decision")
        st.caption("Risk limits: 1% per position, 3% total exposure. Fee schedules, settlement and execution remain unverified.")
        if summary["matched"] == 0:
            st.info("NO TRADE: no exact matches.")
        elif st.session_state.quick_depth.empty:
            st.info("NO TRADE: no candidate clears the preliminary +5pp filter.")
        else:
            st.dataframe(st.session_state.quick_depth, hide_index=True, use_container_width=True)
        with st.expander("Additional preliminary edge comparisons"):
            st.dataframe(st.session_state.get("quick_comparisons", pd.DataFrame()), hide_index=True, use_container_width=True)
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
    scan, odds_tab, edge_tab, evaluate_tab, queue_tab = st.tabs(["Market scan", "Outside odds", "Edge lab", "Evaluate", "Paper queue"])

    st.subheader("Contract validation lab — read-only")
    st.caption("Uses Kalshi public market and order-book data only. Does not spend sportsbook API credits or place orders. Fee metadata and rules are displayed for manual verification, not certified.")
    # Use cached discovery data only; never fetch sportsbook odds during inspection.
    cached_frames=[st.session_state.get("markets"),st.session_state.get("quick_markets_cache")]
    market_rows={}
    for frame in cached_frames:
        if isinstance(frame,pd.DataFrame) and not frame.empty and "ticker" in frame.columns:
            for _,row in frame.iterrows():
                market_rows[str(row["ticker"])]=row
    ticker_options=sorted(market_rows)
    def contract_label(ticker):
        row=market_rows.get(ticker)
        if row is None:
            return ticker
        event=str(row.get("event") or row.get("title") or "Unknown game")
        outcome=str(row.get("yes_sub_title") or "Unknown YES outcome")
        return f"{event} — {outcome} YES ({ticker})"
    if ticker_options:
        validation_selected=st.selectbox("Choose a scanned contract (no API request)",["Enter ticker manually"]+ticker_options,
            format_func=lambda x:"Enter ticker manually" if x=="Enter ticker manually" else contract_label(x),key="validation_selected")
    else:
        validation_selected="Enter ticker manually"
    validation_ticker=(st.text_input("Exact Kalshi market ticker",key="validation_ticker") if validation_selected=="Enter ticker manually" else validation_selected)
    validation_side=st.selectbox("Contract side",["YES","NO"],key="validation_side")
    validation_shares=st.number_input("Shares to inspect",min_value=1,max_value=100,value=1,step=1,key="validation_shares")
    # Kickoff is accepted only from a recent, exact matched sportsbook event in this session.
    kickoff_utc=None
    kickoff_note="No independently matched, fresh sportsbook kickoff cached for this contract."
    matches=st.session_state.get("quick_comparisons")
    odds_cache=st.session_state.get("quick_odds_cache")
    scan_metadata=st.session_state.get("quick_results",{})
    scan_time=parse_time(scan_metadata.get("time")) if isinstance(scan_metadata,dict) else None
    now=datetime.now(timezone.utc)
    if (isinstance(matches,pd.DataFrame) and not matches.empty
        and isinstance(odds_cache,pd.DataFrame) and not odds_cache.empty
        and scan_time is not None and -120 <= (now-scan_time).total_seconds() <= 300
        and validation_ticker in set(matches["ticker"].astype(str))):
        candidate=matches[matches["ticker"].astype(str)==validation_ticker].iloc[0]
        market=market_rows.get(validation_ticker)
        if market is not None:
            import re
            parts=re.split(r"\s+(?:vs\.?|versus|at|@)\s+",str(market.get("event","")),flags=re.I)
            if len(parts)==2:
                team_pair={normalized(x) for x in parts}
                possible=odds_cache[odds_cache.apply(
                    lambda x: {normalized(x.get("home")),normalized(x.get("away"))}==team_pair,axis=1)]
                times={str(x) for x in possible["start"].dropna() if parse_time(x)}
                if len(times)==1 and len(possible["book_key"].dropna().unique())>=2:
                    start=parse_time(next(iter(times)))
                    if start and start>now:
                        kickoff_utc=start.isoformat()
                        kickoff_note="Pregame kickoff from recent, exact matched sportsbook event (cached). Not a live game-status check."
                    elif start:
                        kickoff_note="Cached sportsbook kickoff has passed; pregame approval blocked."
    st.caption(kickoff_note)
    if st.button("Inspect contract — no orders",disabled=not validation_ticker.strip()):
        st.session_state.validation_result=validate_contract(validation_ticker.strip(),validation_side,int(validation_shares),kickoff_utc=kickoff_utc)
    if "validation_result" in st.session_state:
        v=st.session_state.validation_result
        comparison=None
        comparison_rows=st.session_state.get("quick_comparisons")
        scan_details=st.session_state.get("quick_results",{})
        latest=parse_time(scan_details.get("time")) if isinstance(scan_details,dict) else None
        if (isinstance(comparison_rows,pd.DataFrame) and not comparison_rows.empty
            and latest and -120 <= (datetime.now(timezone.utc)-latest).total_seconds() <= 300):
            selected=comparison_rows[(comparison_rows["ticker"].astype(str)==str(v.get("ticker",""))) &
                                     (comparison_rows["side"].astype(str)==str(v.get("side","")))]
            if not selected.empty:
                comparison=selected.iloc[0].to_dict()
        diagnosis=explain(v,comparison)
        st.error("NO VERIFIED TRADE")
        st.markdown("**Why this contract is blocked**")
        for reason in diagnosis["reasons"]:
            st.write("• "+reason)
        st.metric("Preliminary net edge (1 share)",f'{diagnosis["edge_pp"]:+.2f} pp' if diagnosis["edge_pp"] is not None else "Unavailable")
        st.caption("Edge filter: "+diagnosis["edge_filter"]+". The +5pp requirement is not a trade approval. No extra sportsbook requests were made.")
        st.markdown("**Contract inspection summary**")
        st.write(contract_label(str(v.get("ticker",""))))
        st.caption("Side: "+str(v.get("side",""))+" | Kickoff: "+str(v.get("kickoff_utc") or "Unverified")+" | Timing: "+str(v.get("pregame_timing","UNKNOWN")))
        a,b=st.columns(2)
        a.metric("Best depth ask",str(v.get("best_ask_cents"))+"¢" if v.get("best_ask_cents") is not None else "N/A")
        b.metric("Available shares",v.get("shares_available",0))
        gross=v.get("gross_cost_usd")
        fee=v.get("general_fee_estimate_usd")
        a,b=st.columns(2)
        a.metric("Gross depth cost",f"${gross:.2f}" if isinstance(gross,(float,int)) else "N/A")
        b.metric("Estimated total incl. fee",f"${gross+fee:.2f}" if isinstance(gross,(float,int)) and isinstance(fee,(float,int)) else "N/A")
        st.caption("Fee status: "+str(v.get("fee_status","UNVERIFIED"))+"; depth is indicative, not executable.")
        with st.expander("Market rules, fee metadata and inspection details"):
            st.json(v)
    st.divider()
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
        key = sportsbook_api_key()
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
                                                  total_research_exposure(scan_exposure))
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
                                 total_research_exposure(edge_exposure),
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
            result = evaluate(side, fair_pct / 100, ask_cents / 100, fee, int(contracts), bankroll, total_research_exposure(existing))
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
