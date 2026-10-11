# Kalshi Trade Lab — Technical To-Do

Personal-use CFB/NFL research and **paper-trading** roadmap. This is a technical backlog, not a guarantee of profitability or a launch schedule. All new features must fail closed when evidence is missing. Live order placement remains disabled.

## Current technical priorities

- [ ] **Stabilize current paper app:** verify real iPhone UI flows and scan-to-scan comparisons; verify CSV snapshot restore and cross-session state where supported.
- [ ] **Validate research calculations:** contract identity, live kickoff eligibility, source freshness, consensus disagreement, executable order-book prices, contract-specific fees, and position/exposure limits.
- [x] **Phase 1 — Manual hypothetical position ledger:** explicit paper entry/exit transactions, proportionally allocated entry fees, partial exits, independent exposure accounting, and strict CSV backup/restore. These are *manual assumptions*, not verified prices or fills.
- [ ] **Verify full end-to-end paper lifecycle:** distinguish observed quotes from real executed fills; verify market-specific fees, settlement rules, probability calibration and actual net P&L. Manual ledger math alone is not sufficient.
- [ ] **NEW — Active-position monitoring and exit / profit-taking decision support** (details below).
- [ ] Continue sports-focused mobile UI refinement, including the Portfolio display, without changing trading/risk rules.

## NEW: Active-position monitoring and profit-taking decisions

**Goal:** Do not limit the scanner to finding new YES/NO buys. Independently review **already-open paper positions** for potential profit-taking, risk reduction, or holds, even when **zero new buy candidates** meet the +5 percentage-point entry threshold.

### Technical work

- [x] **Manual paper positions ledger (Phase 1):** separate record of exact ticker/event, YES/NO side, hypothetical entry price, manually entered fees, timestamp, shares remaining, position cost, and manual partial/full exits. Scans and queue items never automatically become fills. Real fill imports and verified fee sources are still pending.
- [ ] **Separate manual action: “Review Open Positions”:** inspect positions without requiring or triggering a new-buy scan. No hidden sportsbook API requests; refresh only when requested. Use cached information wherever possible and show the last refresh time.
- [ ] **Executable exit-price validation:** evaluate the correct **bid available to sell the held side**, not its purchase ask or last trade; include available depth at each price, quantity, spread, partial-fill exposure, and quote age. Mark stale, absent or thin bids as **UNVERIFIED — NO EXIT SIGNAL**.
- [ ] **Net realizable P&L:** for full and partial paper exits estimate proceeds less entry and exit fees, net dollars, net ROI on cost basis, break-even bid, and impact on remaining exposure. Do not show a profitable exit based only on a midpoint or indicative quote.
- [ ] **Hold versus exit analysis:** compare estimated net proceeds from selling now with a *separately validated* probability-based value of holding to settlement, time remaining, injury/game-state changes, price movement, uncertainty, and concentration/risk limits. Pregame probabilities must not be blindly reused in live games.
- [ ] **Decision labels with reasons:** `REVIEW PROFIT TAKE`, `REVIEW PARTIAL EXIT`, `HOLD FOR REVIEW`, and `INSUFFICIENT DATA`. Each explanation should specify expected net proceeds, what has changed, why the candidate is being surfaced, and which market facts remain unverified. Labels are **paper research prompts**, not executed orders or guaranteed +EV recommendations.
- [ ] **Independent position monitoring panel:** show open positions, entry vs current validated bid, unrealized/realizable P&L, profit-target and stop-loss *review* thresholds (user configurable), elapsed time, quote quality, and risk concentration; show exits even if the new-buy list is empty.
- [ ] **Verified exit research & journal:** manual hypothetical exits and fee-adjusted ledger arithmetic are implemented, but verified sell-bid snapshots, true executable depth, position-to-market matching, and deterministic paper fill rules are still required. Never count an indicative price as an actual execution.
- [ ] **Safety limits:** no real-money orders, no automatic sell/stop order submission, no background scans, no speculative live win probabilities, no excessive paid Odds API usage. Continue conservative fail-closed checks and keep exit review distinct from opening a new position.

### Acceptance tests before marking complete

- [ ] Open paper position can show an actionable *research review* while new-buy opportunities = **0**.
- [ ] Wrong-side ask, stale quotes, no executable bid or insufficient depth **never** trigger a verified profit-taking opportunity.
- [x] Manual hypothetical P&L correctly accounts for entered entry/exit fees, quantity, partial exits, and remaining cost exposure (offline ledger regression tests). Actual market-specific fees remain unverified.
- [ ] Live/in-play scenarios block hold-value calculations when an independently updated probability estimate is unavailable.
- [x] Manual paper exit transactions survive CSV export/import with stable transaction IDs; duplicate transactions and over-selling are rejected.
- [ ] Phone UI makes **Positions / Exit Review** visible from the Portfolio without obscuring the main Scan Now workflow.
- [ ] All offline regression tests pass; manually verify one end-to-end paper position and exit before relying on the feature.

**Release gate:** Design and implement this as a **paper-only** capability first. Real trading, automated trading, and background notifications require separate security, data and risk review.
