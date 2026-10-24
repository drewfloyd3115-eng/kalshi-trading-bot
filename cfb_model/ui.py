"""CFB Model tab for existing Kalshi Trade Lab. Read-only, paper research only."""
from __future__ import annotations
import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from .core import walk_forward, Forecast
from .data import read_games_csv, fetch_years, fetch_public_years, COLUMNS
from .backtest import score_predictions
from .historical_market import (calibration_table, benchmark_predictions,
                                fetch_cfbd_closing_lines, normalize_closing_lines, LINE_COLUMNS)
from .value import evaluate, from_orderbook, taker_fee
from ui_timezone import format_central, display_central_columns


def _key():
    try:
        return st.secrets.get("CFBD_API_KEY","") or os.getenv("CFBD_API_KEY","")
    except (KeyError,FileNotFoundError):
        return os.getenv("CFBD_API_KEY","")


def render_model_ui():
    st.title("CFB Prediction Lab")
    st.caption("All times displayed in Central Time (CDT/CST). UTC is retained in downloaded research files.")
    st.caption("Historical-results baseline · independently tested forecasts · PAPER ONLY · no orders")
    st.warning("This baseline has NOT demonstrated a profitable edge. Incomplete data, a kickoff already passed, unverified contract rules, or stale quotes must result in PASS.")
    source=st.radio("Real-game data source",["Public FBS scores (no key)","Upload existing CFBD CSV","Fetch from CollegeFootballData"],horizontal=False)
    if source.startswith("Public"):
        st.caption("Free public scoreboard: jackwarfield/cfb_rankings on GitHub (2020–2026). Third-party; excludes FCS matchups and scores from games less than 8 hours old.")
        if st.button("Load 2020–2026 public FBS scores",key="cfb_public_fetch"):
            try:
                with st.spinner("Downloading real historical results from public GitHub CSVs..."):
                    st.session_state.cfb_games=fetch_public_years(2020,2026)
                    st.session_state.pop("cfb_schedule",None)
                st.success(f"Loaded {len(st.session_state.cfb_games):,} real FBS matchups")
                gaps=st.session_state.cfb_games.attrs.get("missing_seasons",[])
                if gaps:
                    st.warning("Incomplete historical source: no FBS records available for "
                               + ", ".join(map(str,gaps))
                               + ". These seasons are excluded, NOT filled with estimated games. "
                               + "Treat accuracy as preliminary. Use an official CFBD import for complete history.")
            except Exception as exc:st.error(f"Public data fetch failed: {exc}")
    elif source.startswith("Upload"):
        upload=st.file_uploader("CFBD games CSV (real data, unique game IDs)",type=["csv"],key="cfb_data_file")
        if upload is not None:
            try:
                st.session_state.cfb_games=read_games_csv(upload)
                st.session_state.pop("cfb_schedule",None)
                st.success(f"Loaded {len(st.session_state.cfb_games):,} real-game rows")
            except Exception as exc:
                st.error(f"CSV rejected: {exc}")
    else:
        start,end=st.columns(2)
        start_year=start.number_input("Start season",2010,2030,2018)
        end_year=end.number_input("End season",2010,2030,2026)
        if not _key():
            st.info("Add CFBD_API_KEY in Streamlit Secrets first. Do not publish or paste the key into code.")
        if st.button("Fetch actual games (manual)",disabled=not bool(_key())):
            try:
                with st.spinner("Loading historical FBS games from CFBD..."):
                    st.session_state.cfb_games=fetch_years(int(start_year),int(end_year),_key())
                    st.session_state.pop("cfb_schedule",None)
                st.success(f"Fetched {len(st.session_state.cfb_games):,} games (API calls used).")
            except Exception as exc:st.error(f"Data fetch failed: {exc}")
    if "cfb_games" not in st.session_state:
        st.info("No games loaded. Load public FBS scores, import a real games CSV or connect a CFBD API key. No fabricated predictions will be shown.")
        st.download_button("Download CSV column template",pd.DataFrame(columns=COLUMNS).to_csv(index=False),file_name="cfbd_games_template.csv")
        return
    games=st.session_state.cfb_games
    gaps=games.attrs.get("missing_seasons",[])
    if gaps:
        st.warning("HISTORICAL COVERAGE GAP — missing season(s): "
                   + ", ".join(map(str,gaps))
                   + ". This data is incomplete; validation estimates may be biased.")
    if games.empty:
        st.error("No real games in the dataset")
        return
    # A historical scoreboard is not an authoritative forward schedule.
    # Fetch scheduled events separately and require exact historical ESPN IDs.
    team_ids=games.attrs.get("espn_team_ids",{})
    if team_ids:
        st.subheader("Load upcoming schedule")
        st.caption("Read-only ESPN FBS scoreboard (unofficial API). Matchups must have exact ESPN team IDs in the historical source. No betting API, odds credits or automated orders.")
        if st.button("Load upcoming 8 days of FBS games",key="cfb_load_schedule"):
            st.session_state.pop("cfb_schedule",None)
            try:
                from .schedule import fetch_upcoming_schedule
                with st.spinner("Fetching next 8 days of scheduled FBS games..."):
                    schedule=fetch_upcoming_schedule(team_ids,days=8)
                st.session_state.cfb_schedule=schedule
                stats=schedule.attrs.get("stats",{})
                st.success(f"Verified {len(schedule)} future FBS matchups from {stats.get('received','?')} scoreboard events.")
                if stats.get("unmapped",0):
                    st.caption(f"Excluded {stats['unmapped']} events with unknown FBS team IDs; no fuzzy team guessing.")
            except Exception as exc:
                st.warning(f"Upcoming schedule unavailable: {exc}. Historical evaluation is still available.")
    else:
        st.caption("No verified ESPN team-ID mapping in this dataset. To load upcoming games without guessing names, load the public FBS score source.")
    schedule=st.session_state.get("cfb_schedule")
    model_games=games
    if isinstance(schedule,pd.DataFrame) and not schedule.empty:
        known_ids=set(games.game_id.astype(str))
        unseen=schedule.loc[~schedule.game_id.astype(str).str.replace(r"^espn-","",regex=True).isin(known_ids)].copy()
        if not unseen.empty:
            from .data import normalize_games
            model_games=normalize_games(pd.concat([games,unseen],ignore_index=True))
            st.caption(f"Added {len(unseen)} verified future schedule events to the model. Historical game outcomes remain unchanged.")
        else:
            st.info("The known historical dataset already includes these upcoming event IDs.")
    try:
        predictions,_=walk_forward(model_games)
    except Exception as exc:
        st.error(f"Model could not run: {exc}")
        return
    st.caption(f"Loaded {len(games):,} games; {int(games.completed.sum()):,} completed. Available seasons: {', '.join(map(str,sorted(set(games.season.astype(int)))))}. Every forecast was generated before that game's result was used for rating updates.")
    st.download_button("Download pregame projections CSV",predictions.to_csv(index=False).encode("utf-8"),file_name="cfb_pregame_predictions.csv",mime="text/csv")
    st.subheader("Walk-forward holdout validation")
    valid_seasons=sorted(set(predictions.loc[predictions.completed,"season"].astype(int)))
    if valid_seasons:
        test_year=st.selectbox("Holdout season",valid_seasons,index=(valid_seasons.index(2025) if 2025 in valid_seasons else len(valid_seasons)-1))
        st.json(score_predictions(predictions,test_year))
    st.caption("The model uses only final results, not EPA, injuries or independently verified sportsbook closing lines yet. Predictive accuracy is not proof of betting profitability.")
    if valid_seasons:
        with st.expander("Probability calibration — model vs actual outcomes",expanded=False):
            st.caption("Historical frequency by predicted confidence band. This is not an ROI calculation or proof of a profitable edge.")
            calibrated=calibration_table(predictions,int(test_year))
            if calibrated.empty:
                st.info("Insufficient eligible holdout games for calibration.")
            else:
                st.dataframe(calibrated,hide_index=True,use_container_width=True)
                st.download_button("Download calibration CSV",calibrated.to_csv(index=False).encode("utf-8"),
                                   file_name=f"cfb_calibration_{test_year}.csv",mime="text/csv")
        st.subheader("Historical sportsbook benchmark")
        st.caption("Paired spread and total MAE against actual closing lines. Only matching game IDs and exact home/away teams are accepted. No quote timestamps or executable prices = NO historical EV or P&L evidence.")
        market_source=st.radio("Historical sportsbook data",["Upload closing-lines CSV (no key)",
            "Fetch CFBD historical lines (requires API key)"],key="cfb_line_source")
        selected_provider=st.selectbox("Provider",["consensus","DraftKings","Caesars","Bovada","teamrankings"],key="cfb_line_provider")
        if market_source.startswith("Upload"):
            template=pd.DataFrame(columns=LINE_COLUMNS).to_csv(index=False)
            st.download_button("Download historical-lines CSV template",template,
                               file_name="cfb_historical_closing_lines_template.csv",mime="text/csv")
            lines_file=st.file_uploader("Historical closing lines CSV (one selected provider per game)",
                                        type=["csv"],key="cfb_line_upload")
            if lines_file is not None and st.button("Validate uploaded closing lines",key="cfb_lines_upload_go"):
                try:
                    loaded=normalize_closing_lines(pd.read_csv(lines_file))
                    st.session_state.cfb_closing_lines=loaded
                    st.session_state.cfb_line_year=int(test_year)
                    st.success(f"Validated {len(loaded)} closing-line records for comparison; game years checked during exact-ID match.")
                except Exception as exc:
                    st.session_state.pop("cfb_closing_lines",None)
                    st.error(f"Closing-lines CSV rejected: {exc}")
        else:
            if not _key():
                st.info("Add CFBD_API_KEY privately in Streamlit Secrets to import official historical closing lines. Do not publish the key in code or screenshots.")
            if st.button(f"Fetch {int(test_year)} {selected_provider} closing lines (manual)",
                         key="cfb_market_fetch",disabled=not bool(_key())):
                try:
                    with st.spinner("Fetching historical bookmaker lines from CollegeFootballData..."):
                        loaded=fetch_cfbd_closing_lines(int(test_year),_key(),selected_provider)
                    st.session_state.cfb_closing_lines=loaded
                    st.session_state.cfb_line_year=int(test_year)
                    st.success(f"Loaded {len(loaded)} {selected_provider} historical game-line records.")
                except Exception as exc:
                    st.session_state.pop("cfb_closing_lines",None)
                    st.error(f"Historical lines fetch failed: {exc}")
        cached_lines=st.session_state.get("cfb_closing_lines")
        cached_year=st.session_state.get("cfb_line_year")
        if isinstance(cached_lines,pd.DataFrame) and not cached_lines.empty:
            if int(cached_year)!=int(test_year):
                st.warning("Select the matching holdout season and reload its closing lines. Previous season lines are not reused.")
            else:
                try:
                    market_report,paired=benchmark_predictions(predictions,cached_lines,int(test_year))
                    st.json(market_report)
                    st.caption("Positive 'market_advantage_points' means MODEL has lower average absolute error on MATCHED games. Negative means sportsbook line predicts better. This is NOT expected value.")
                    st.dataframe(display_central_columns(paired.head(150)),
                                 hide_index=True,use_container_width=True)
                    st.download_button("Download paired market benchmark CSV (UTC)",
                                       paired.to_csv(index=False).encode("utf-8"),
                                       file_name=f"cfb_market_benchmark_{test_year}.csv",mime="text/csv")
                except Exception as exc:
                    st.warning(f"Historical market comparison not available: {exc}")
        else:
            st.info("No real historical sportsbook lines loaded. Holdout scoring remains available, but we cannot claim to beat the market.")
    st.subheader("Upcoming matchups")
    now=pd.Timestamp.now(tz="UTC")
    upcoming=predictions.loc[(~predictions.completed)&(predictions.kickoff_utc>now)&(predictions.eligible_history)].copy()
    if upcoming.empty:
        st.info("No eligible future games found. If you haven't yet loaded the upcoming ESPN schedule, use the button above. Started games, unknown team IDs and insufficient history are excluded.")
        return
    shown=upcoming[["kickoff_utc","away_team","home_team","projected_home_margin","projected_total","home_win_prob","training_games"]].copy()
    shown.home_win_prob=(shown.home_win_prob*100).round(1)
    st.dataframe(display_central_columns(shown),hide_index=True,use_container_width=True)
    st.download_button("Download upcoming projections CSV",upcoming.to_csv(index=False).encode("utf-8"),file_name="cfb_upcoming_projections.csv",mime="text/csv")
    st.subheader("Model versus market — indicative research")
    st.caption("ESPN's public scoreboard sometimes includes sportsbook lines. These are optional, unverified and not executable Kalshi quotes. Discrepancy is a point difference, NOT betting expected value.")
    if isinstance(schedule,pd.DataFrame):
        raw_market=schedule.attrs.get("indicative_market")
        if isinstance(raw_market,pd.DataFrame) and not raw_market.empty:
            from .market_comparison import discrepancy_table
            try:
                comparisons=discrepancy_table(upcoming,raw_market)
            except (ValueError,TypeError,KeyError) as exc:
                st.warning(f"Market comparison blocked: {exc}")
                comparisons=pd.DataFrame()
            if not comparisons.empty:
                spread_count=int(comparisons.market_home_handicap.notna().sum())
                total_count=int(comparisons.market_total.notna().sum())
                st.caption(f"{spread_count} market spreads and {total_count} totals with verified matchup IDs. Quotes have NOT been checked for executable price, injury changes, sportsbook fees or official settlement rules.")
                st.dataframe(display_central_columns(comparisons),hide_index=True,use_container_width=True)
                st.download_button("Download indicative market comparison CSV",
                    comparisons.to_csv(index=False).encode("utf-8"),
                    file_name="cfb_market_discrepancies.csv",mime="text/csv")
                st.info("The 2025 backtest did not establish a betting edge. Large model-market gaps can reflect weaknesses in our simple score-only ratings. PASS without independent verification.")
            else:
                st.info("No usable, recent model-to-market comparisons available. This does not imply the games have no betting lines.")
        else:
            st.info("ESPN did not provide a usable sportsbook line snapshot. No market comparisons or bets can be inferred.")
    else:
        st.info("Load an upcoming schedule to check whether any indicative market lines are available.")
    choices={f"{r.away_team} @ {r.home_team} — {format_central(r.kickoff_utc)} [{r.game_id}]":r.game_id for _,r in upcoming.iterrows()}
    selected=st.selectbox("Evaluate one game",list(choices))
    r=upcoming[upcoming.game_id==choices[selected]].iloc[0]
    fc=Forecast(float(r.projected_home_margin),float(r.projected_total),float(r.home_win_prob),float(r.margin_sigma),float(r.total_sigma),int(r.training_games),int(r.home_sample),int(r.away_sample))
    if fc.home_sample<2 or fc.away_sample<2:
        st.warning("One or both teams have too few current-season games. Do not treat this as a reliable edge.")
    a,b,c=st.columns(3)
    a.metric("Projected home margin",f"{fc.home_margin:+.1f}")
    b.metric("Projected game total",f"{fc.total:.1f}")
    c.metric("Home win estimate",f"{fc.home_win_prob:.1%}")
    outcome=st.selectbox("Outcome the model prices",["HOME_WIN","AWAY_WIN","HOME_COVER","AWAY_COVER","OVER","UNDER"],format_func=lambda x: x.replace("_"," "))
    line=None
    if outcome in ("HOME_COVER","AWAY_COVER"):
        line=st.number_input("HOME team's point handicap (e.g. home -7.5 = -7.5)",value=-3.5,step=.5)
    elif outcome in ("OVER","UNDER"):
        line=st.number_input("Game total threshold (e.g. 52.5)",value=52.5,step=.5)
    fair=fc.probability(outcome,line)
    st.metric("Model-estimated event probability",f"{fair:.1%}")
    st.subheader("Check a Kalshi quote (manual research)")
    ticker=st.text_input("Exact Kalshi binary market ticker",key="cfb_ticker").strip()
    st.caption("The market's YES event must exactly match the chosen outcome and numeric line. A team name match alone is NOT sufficient.")
    side=st.selectbox("Contract to buy",["YES","NO"],key="cfb_side")
    shares=st.number_input("Hypothetical shares",min_value=1,max_value=1000,value=10,key="cfb_shares")
    paper_bankroll=st.number_input("Research bankroll ($)",min_value=1.0,value=float(st.session_state.get("quick_bankroll",50.0)),key="cfb_bankroll")
    external_exposure=st.number_input("Other existing open exposure ($)",min_value=0.0,value=float(st.session_state.get("quick_exposure",0.0)),key="cfb_external_exposure")
    fee_multiplier=st.number_input("Manually VERIFIED Kalshi fee multiplier",min_value=0.0,max_value=10.0,value=1.0,step=0.25,key="cfb_fee_multiplier")
    st.caption("Verify fee type/multiplier in the relevant Kalshi series; maker/taker rules can differ. No prices are inferred from YES bids.")
    if st.button("Fetch read-only market + public bids",disabled=not bool(ticker)):
        try:
            from .kalshi import fetch_market_and_orderbook
            meta,book=fetch_market_and_orderbook(ticker)
            st.session_state.cfb_quote={"ticker":ticker,"metadata":meta,"book":book,
                                       "fetched":datetime.now(timezone.utc).isoformat()}
        except Exception as exc:
            st.session_state.pop("cfb_quote",None)
            st.error(f"Public quote lookup failed: {exc}")
    snapshot=st.session_state.get("cfb_quote")
    if not snapshot or snapshot["ticker"]!=ticker:
        st.info("Fetch a fresh quote or evaluate a MANUALLY checked paper price. No quote = no trade signal.")
        return
    metadata=snapshot["metadata"]
    st.write("Market title:",metadata.get("title","Missing"))
    st.write("YES means:",metadata.get("yes_sub_title","Review exact Kalshi rules"))
    st.write("Rules:",metadata.get("rules_primary","See Kalshi market details"))
    st.caption("Market status: {} · Retrieved (Central): {}".format(metadata.get("status","UNKNOWN"),format_central(snapshot["fetched"])))
    st.json({k:(format_central(metadata.get(k)) if k in ("updated_time","close_time") else metadata.get(k)) for k in ("fee_type","fee_multiplier","updated_time","close_time")})
    depth=from_orderbook(snapshot["book"],side,int(shares))
    st.write("Book analysis:",depth)
    seen_at=pd.to_datetime(snapshot["fetched"],utc=True)
    freshness=(pd.Timestamp.now(tz="UTC")-seen_at).total_seconds()
    reviewed=st.checkbox("I verified the event, exact outcome/line, contract settlement rules, trading fee, and correct YES/NO direction.",key="cfb_rules_verified")
    if freshness>120 or metadata.get("status") not in ("active","open") or depth["status"]!="OBSERVED BID DEPTH ONLY" or not reviewed:
        st.warning("PASS — stale/ineligible quote, insufficient observed depth, or settlement and fee rules not verified.")
        return
    per_contract_fair=fair if side=="YES" else 1-fair
    # Conservative estimate: rounding fee separately at each observed ask level.
    levels=depth["levels"]
    cost=sum(p*n/100 for p,n in levels)
    fee=sum(taker_fee(p,int(n),fee_multiplier) for p,n in levels)
    expected=shares*per_contract_fair
    edge=100*(per_contract_fair-(cost+fee)/shares)
    known_open=float(st.session_state.get("paper_exposure",0.0))
    if "position_ledger" in st.session_state:
        try:
            from position_ledger import ledger_summary
            known_open+=float(ledger_summary(st.session_state.position_ledger)["open_cost_usd"])
        except (ImportError,KeyError,TypeError,ValueError):
            st.warning("Could not verify existing ledger exposure; candidate is blocked")
            return
    within_risk=(cost+fee <= paper_bankroll*.01 and
                 cost+fee+known_open+external_exposure <= paper_bankroll*.03)
    st.metric("Model net edge after estimated fees",f"{edge:+.2f} percentage points")
    st.metric("Paper expected P&L (holding through settlement)",f"${expected-cost-fee:+.2f}")
    if not within_risk:
        st.warning("PASS — hypothetical cost exceeds the existing 1% per-position or 3% aggregate exposure cap")
    elif edge>=5:
        st.warning("PRELIMINARY PAPER CANDIDATE ONLY — baseline is unvalidated; public book is not guaranteed executable and event-specific fees/injuries still require independent checks.")
    else:
        st.info("PASS — below 5 percentage-point research threshold")
