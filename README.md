# Kalshi Trade Lab

Phone-friendly CFB/NFL Kalshi research scanner and **manual paper-trading ledger**, deployed as a Streamlit application.

**NO LIVE TRADING.** No Kalshi credentials, broker keys, order placement, automatic selling or background trading are included. Data and calculations are illustrative research until independently verified. The app does not prove a positive expected value or a profitable strategy.

## Current screens

- **Home:** Manual Scan Now button, paper bankroll and exposure summary, and cached research highlights. Only the user-triggered scan requests sportsbook odds.
- **Opportunities:** Cached best-route estimates with safety gates, quote-quality data, search, and ranking. No approved trades.
- **Market Detail:** Indicative price vs. fair-probability estimate, one-share fee calculation, source and kickoff checks.
- **Portfolio:** Four subviews — Overview, Open paper fills, History, Exit review. Now supports a **separate manual position ledger**.
- **Research:** Full existing research/scanning tools and legacy paper observation journal.

## Manual paper-position workflow (Phase 1)

You can record and review simulated entries/exits **without running Scan Now, using Odds API credits or placing any order**.

1. On **Portfolio → Open paper fills**, expand **Record a hypothetical paper entry**.
2. Enter the *exact* Kalshi market ticker, CFB/NFL league, game, winning outcome/team, YES/NO side, manually assumed entry price in cents, share quantity, and manually entered total entry fee.
3. Confirm the checkbox that this was a **hypothetical manual fill**. Click **Save hypothetical entry**. This does not validate any live order or contract.
4. Review remaining shares/cost basis under Open paper fills. New manual entries respect an indicative **1% bankroll cap per market** (including multiple entries in the same ticker) and **3% total open exposure cap** (including the prior paper queue and entered other exposure). Historical/imported records do not certify that past limits were met.
5. Under **Portfolio → Exit review**, you can **manually record** a partial or full hypothetical sale at a chosen illustrative price and manually entered fee. This is **not** an automated sell recommendation or a verified bid.
6. Go to **Portfolio → History** to download the separate `kalshi_position_ledger.csv` backup. Export it after every session.
7. To restore, use **Restore / replace ledger from CSV** in History. Import requires confirmation and **replaces** the existing manual ledger. Strict validation rejects duplicate IDs, over-selling, invalid contract sides, and malformed records.

The app calculates remaining shares, paper cost basis (including entered entry fees), manually simulated realized net P&L (subtracting proportionately allocated entry fees and entered exit fees), and partial exits. All fee amounts and fill prices are **user-entered assumptions**, not independently validated or actual proceeds. The legacy research observation journal is **not** the new position ledger; observations and queued approvals are never automatically counted as fills.

## Not built yet

- Reliable, independently verified executable exit bid and live order-book depth for a held position.
- Position-level hold-versus-sell / profit-taking signals, real-time or in-play probability estimates.
- Contract-specific fee certification, real-money position sync, actual fills/settlement audit.
- Automatic monitoring, notifications, orders, or guaranteed cloud persistence. The manual ledger lives in the Streamlit browser session until you export it; its CSV backup is the recovery path.
- Evidence of live profitability; research estimates must be tested against recorded outcomes before real-money use.

See [TECHNICAL_TODO.md](TECHNICAL_TODO.md) and [active-position monitoring issue](https://github.com/drewfloyd3115-eng/kalshi-trading-bot/issues/1).

## Local development and tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v -p 'test_*.py'
streamlit run app.py
```

GitHub Actions runs offline regression tests on push. The UI code and regression tests do not need an Odds API key. Use Streamlit Secrets to configure `ODDS_API_KEY` for an optional **user-initiated** sportsbook scan; never commit the key.

No Firecrawl integration is required.


## CFB Prediction Lab (new model tab)

An independent historical-results baseline and holdout-season audit are available under **CFB Model**. Supply CFBD_API_KEY in Streamlit Secrets or upload a real CFBD games CSV. NO validated profitability or automatic trading. See [CFB_PREDICTION_LAB.md](CFB_PREDICTION_LAB.md) and run offline regression tests before use.

## Upcoming CFB schedule (paper-only)

In the **CFB Model** tab load the free public FBS scores, then select **Load upcoming 8 days of FBS games**. This fetches pregame ESPN schedule events using verified historical ESPN team IDs, with no credentials or bets. The model excludes started games and unidentified teams and shows an explicit error when ESPN data is unavailable. Predictions are **not validated profitable bets**. Details: [CFB_PREDICTION_LAB.md](CFB_PREDICTION_LAB.md).


## Display timezone

**All human-readable app dates/times default to Central Time (America/Chicago).** Daylight-saving changes are automatic: CDT (UTC−5) during daylight time and CST (UTC−6) during standard time. This applies to CFB kickoff selectors/tables, sportsbook kickoff fields, market snapshot captions and portfolio history. The raw downloaded CSV audit columns and internal kickoff/fee/quote-freshness validation remain timestamped in UTC; those source fields are never rewritten just to change the display timezone. Missing or timezone-naive timestamps are shown as unverified rather than assumed Central.


## Historical CFB model vs sportsbook (Phase 2)

The **CFB Model** tab now includes an optional **Probability calibration** view and a **Historical sportsbook benchmark** view. With real historical CFBD /lines data it compares model point-spread/total mean absolute errors against same-game sportsbook closing-line errors using exact game IDs and team names. It shows matching sample counts, coverage and uncertainty; does **not** calculate historical wager profits or treat untimestamped closing lines as executable entry prices.

Use the real **closing-lines CSV upload** route without a key or configure `CFBD_API_KEY` *privately* in Streamlit Cloud Secrets, then manually fetch the selected season's historical lines (2025 by default). The app never fetches historical bookmaker data automatically or uses it to train its model. See [CFB_PREDICTION_LAB.md](CFB_PREDICTION_LAB.md) for the schema and offline CLI. Missing or mismatched lines remain unavailable rather than fabricated.


### CFBD historical-line provider diagnostics

CFB Model → Historical sportsbook benchmark now uses a manual **Check provider availability** step for the selected year. CFBD does not guarantee every year has `consensus` lines. One unfiltered source request shows available provider coverage, then users choose an actual provider (or **Auto**, based only on record coverage) without more API calls. An empty response is honestly reported and never replaced with invented data. This screen remains paper-only and does not consume ODDS_API_KEY credits.


### CFB error diagnostics

After loading historical sportsbook benchmark lines, open **Why our model trails the sportsbook — diagnostic audit** in the CFB Model tab. The app breaks down matching-game spread/total errors by season phase, favorite size, sportsbook disagreement and total bands, and provides downloadable CSV evidence. This is **descriptive post-hoc analysis**, not parameter tuning or evidence of profitable trading. The live model is unchanged pending earlier-season training and fresh out-of-sample testing.


## Tonight CFB — fast Saturday research (Central Time)

Open **Tonight CFB** from the Streamlit navigation. Tap **Refresh tonight's remaining FBS games** once. The app reuses the public historical-score dataset already loaded in this session where possible, otherwise retrieves real FBS results, fetches just the next day's ESPN FBS schedule using **single-date** requests, and filters kickoff times to **the current Central calendar day after 5:00 PM** (excluding started games). No CFBD or paid Odds API query is used. A second refresh updates to a fresh schedule; snapshots more than 30 minutes old are flagged stale. Optional sportsbook snapshot lines from ESPN are labelled unverified; no prices are invented. The screen shows scores, win probabilities, model/book point discrepancies, and a conservative **PASS — NO VERIFIED POSITIVE EV** status. Download the research CSV for auditing, retaining UTC timestamps. Historical 2025 spread/total benchmark shows this model is not yet better than bookmakers, particularly for large favorites. This is a research interface, NOT a betting recommendation or trade executor.


## Tonight CFB v2 — Vegas / model / logos / simulations

The **Tonight CFB** tab now renders compact iPhone-friendly matchup cards: team names, source-verified ESPN team logos, kickoff in Chicago Central Time, a **fresh US sportsbook spread** alongside our own modeled spread, projected scores, and 20,000 reproducible Gaussian model draws per matchup. Each card includes approximate home/away winner frequencies and a margin/total simulation range. When there is a fresh exact-match spread, the card can also show an illustrative cover frequency.

Tap **Refresh tonight’s games + Vegas spreads**. This makes one *optional* real Odds API request for `americanfootball_ncaaf / us / spreads` with your existing `ODDS_API_KEY` (consumes provider quota; it is not an automatic background scan). Only supported ESPN source aliases and kickoffs within 90 minutes match market events; each selected book must have both opposite spread outcomes, a last-update time no older than 15 minutes, and a consistent handicap sign. Multiple independent US book spreads display as a **median of N books**, with provenance and quote-age checks; unmatched/stale data say **Unavailable**, never an invented Vegas line. ESPN-only indicative lines are not promoted to current sportsbook prices. Team logos are from https://a.espncdn.com/i/teamlogos/ncaa/500/{numeric-id}.png for exact verified ESPN IDs, otherwise a generic football icon.

Research-confidence badge colors: **gray Unverified** (missing fresh spreads), **red Low** (single book, limited team samples, huge disagreement or favorite at least 21 points), **amber Cautious** (multiple fresh books and stronger team-history coverage). There is deliberately **no green/high/profitable** badge because this historical score-only model underperformed the sportsbook on 2025 spreads and totals. Missing injuries, starting QBs, weather, EPA and pace are explicitly disclosed. Normal continuous simulations omit discrete scoring and push effects. Quote ages and app snapshot refresh determine whether a Vegas line is displayed as current. No trading or Kalshi order submission is added.


### October 24 Vegas spread display correction

The initial 15-minute quote-age gate made available sportsbook lines appear as `Unavailable` when games had not changed prices recently. **Tonight CFB** now distinguishes four cases after one user-triggered Odds API request:

1. **VEGAS SPREAD · CURRENT SNAPSHOT:** a validated exact-team and kickoff match with a valid updated spread no more than 15 minutes old at render time.
2. **BOOK REFERENCE · N MIN OLD:** an independently sourced sportsbook spread updated more than 15 minutes ago but at most 180 minutes ago. This is **not** a current quote or actionable betting price.
3. **ESPN REFERENCE · UNVERIFIED:** no independently matched sportsbook line, but the ESPN scoreboard supplied an unverified indicative handicap. It is **not** called Vegas.
4. **VEGAS SPREAD · UNAVAILABLE:** no validated source; a per-game diagnostic distinguishes unmatched team names, missing odds event, mismatched kickoff, absent spread market, absent timestamp, stale quote or invalid side/sign. A zero-event response shows zero, not a fictitious line.

The app does **not** make additional paid API calls for diagnostics. A cached quote becomes labeled an older reference once the 15-minute cutoff is exceeded. Preview simulated covers only use validated current lines; older/ESPN references are display-only. All betting statuses remain **PASS**, as historical evidence does not establish a profitable edge. `ODDS_API_KEY` remains in Streamlit Secrets.


### Independent market-source verification versus model evidence (Oct 24)

Matchup cards deliberately separate **market source** from **model evidence**:

- **Market source:** `INDEPENDENT BOOK` when an exact matching The Odds API quote exists (with current vs older age checks); `ESPN REFERENCE` when the ESPN scoreboard provides an indicative reference only; otherwise `NO MARKET DATA`. The data-source state does NOT set the model-evidence rating.
- **Model evidence:** `PRELIMINARY` amber (historical game samples and residual dispersions satisfy basic checks), `LOW` red (insufficient team sample, high historical margin dispersion, or 21+ point market favorite), and `INSUFFICIENT` neutral (invalid residual uncertainty). No high/green/profitable label is justified: on 2025 matched games the baseline trailed sportsbook spread and total MAE.
- **Per-game fallback:** Independent sportsbook lines replace ESPN references only for exact matched IDs. A successful match for one game must not cause unmatched games to lose their reference lines.
- **Simulations:** Illustrative 20,000 Gaussian residual draws, **not empirically calibrated betting confidence**. Every card continues to show **PASS** until a separately validated market price/fee/settlement and genuinely positive EV exist.
- **Known omitted factors:** verified quarterback injuries/status, weather, EPA, play-by-play efficiency, and late player news are not yet integrated.

The screen recording showing all cards as `UNVERIFIED` reflected a presentation coupling error, not proof that all historical model inputs or market events were invalid. Current quotes still require source confirmation, market-time validation and matching. This fix does not add paid API calls or authorize wagers.
