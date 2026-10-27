# Multi-Venue Autopilot — build and release gates

State: PAPER-ONLY scaffolding. No 24/7 cloud worker, trading API credentials,
orders, automated paper fills, portfolio reconciliation, or independently
validated live probabilities have been deployed. Live trading is locked.

## User's goal

One bot that continuously watches all eligible Kalshi, Polymarket US, and
Novig markets; computes independently calibrated win probabilities; considers
fees and real executable depth; enforces combined risk limits; chooses entries
and exits; monitors open and partial orders; and logs results without
requiring routine per-trade approval *after a separately authorized launch*.

Never bypass venue account eligibility or regional restrictions.

## Implemented in this phase

- autopilot_core.py — normalized $1 binary candidates, independently verified
  model/quote/settlement/fee gates, kill switch, data age limits, net edge,
  one-share affordability, per-venue and cross-venue capital risk checks.
- autopilot_cycle.py — one in-memory paper-decision pass with risk reservation,
  duplicate identity checks and same-event protection across three venues.
- autopilot_ui.py — paused, locked phone control room, on-demand Kalshi public
  NFL/CFB listing and explicit reasons observations are rejected.
- test_autopilot.py — pure risk and no-network-on-load regression tests.

The starting bankroll is $100 with existing 1% ($1) per-position and 3%
($3) overall open paper exposure limits, and a minimum +5pp net
probability edge. New starter guards: $2 realized daily loss stop,
$5 max equity drawdown from $100, 3 positions, 20 proposals per day.
These limits do not guarantee safety, profitability or a liquid exit.
The UI does not automatically derive model probabilities from market prices.

A passed PAPER_READY outcome means hypothetical inputs passed the
code constraints. It is not a verified trade signal, paper fill, actual
order or established trading edge. A public market row MUST remain
BLOCKED until its independent probability, executable depth, timestamp,
fees and settlement are verified.

## Release steps before ANY live automation

1. Confirm each platform's trading/API availability for the user's Alabama
   account, and exact eligible product set. Polymarket US is not the same as
   the international Polymarket exchange. Novig integration needs documented
   supported trading endpoints and authorization.
2. Add exchange-specific connectors, initially READ-ONLY, with normalized
   market tickers, account balances, positions and outstanding orders.
3. Add a source-verified cross-venue event ID matcher. Similar team names or
   titles are not enough to establish correlation.
4. Create sport-by-sport independently calibrated models and out-of-sample
   testing. Use current live state only where the model supports it.
5. Add a privately deployed always-on service and transactional database;
   Streamlit UI is NOT a dependable background trading worker.
6. Implement idempotent client order identifiers, exactly tracked open orders,
   cancellation state, partial fill reconciliation and worst-case exposure
   reservations across every venue. Use durable audit records and health alerts.
7. Introduce shared across-venue stop controls and orderbook depth checks;
   stop losses in illiquid markets are not guaranteed.
8. Test demo order placement on the platforms that explicitly support a demo
   API, then shadow-mode live quote collection and robust prospective paper
   trading. Validate fill rates and net P&L, model calibration and drawdowns.
9. Conduct a separate code and credentials security review. Store private API
   tokens with least privilege in private secrets, never in GitHub, chat or
   public deployment code. Do not ask the user for wallet seed phrases.
10. Require a fresh, explicit authorization for live trading mode, exact
    account, bankroll, maximum losses, approved products and auto-execution
    permissions. Do not silently migrate paper/approval mode into live mode.

## Run tests

python -m unittest discover -v -p 'test_*.py'

Start the Streamlit app and select Auto Bot. No external request occurs
when that page loads; manual public Kalshi scan fetches listings only.
