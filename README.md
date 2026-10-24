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
