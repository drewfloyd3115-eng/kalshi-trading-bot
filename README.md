# Kalshi Trade Lab

A phone-friendly Streamlit prototype for read-only Kalshi market snapshots, manual fair-probability evaluation, and session-only paper approvals.

**Version 0.1: NO LIVE TRADING.** No Kalshi credentials, trading keys, or order-placement code are included.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Connect this GitHub repository to Streamlit Community Cloud, choose `app.py` as the entry point, and deploy. No secrets are required for this prototype.

## How to use

1. Refresh the public market snapshot and find a ticker. Only the first 200 open markets are fetched; the scan is not a complete CFB/NFL inventory.
2. Independently estimate the probability of the **specific YES or NO outcome**.
3. Enter the executable ask for that side, contracts, estimated total fees, paper bankroll and other open exposure.
4. Evaluate. Candidates require at least 5 percentage points of edge after entered fees, a maximum 1% paper-bankroll cost per trade, and 3% total exposure.
5. Approve a candidate to the session-only **paper** queue. This does not place an order.

### Known limitations

- Market snapshots may be delayed, incomplete, or stale. Validate market rules, actual executable price, liquidity, fees, and game state independently.
- No independent probability model, sports-specific discovery, persistent storage, automatic alerts, or real order execution yet.
- Fee estimates are entered manually; zero is **not** an assertion that Kalshi charges no fee.
- The queue resets when the app session ends.
- The 1% cap can make even a single contract ineligible for small bankrolls.
