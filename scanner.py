"""Read-only public Kalshi market snapshots. No credentials or order placement."""
import pandas as pd
import requests

API = "https://api.elections.kalshi.com/trade-api/v2/markets"

def fetch_markets():
    response = requests.get(API, params={"limit": 200, "status": "open"}, timeout=15)
    response.raise_for_status()
    records = []
    for market in response.json().get("markets", []):
        def price(field):
            value = market.get(field)
            return float(value) / 100 if value is not None else None
        records.append({
            "ticker": market.get("ticker", ""),
            "title": market.get("title", ""),
            "yes_bid": price("yes_bid"),
            "yes_ask": price("yes_ask"),
            "volume": market.get("volume"),
            "close_time": market.get("close_time"),
        })
    return pd.DataFrame(records, columns=["ticker", "title", "yes_bid", "yes_ask", "volume", "close_time"])
