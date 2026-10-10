"""CFB/NFL market discovery with explicit event-series filters and read-only quotes."""
import requests
import pandas as pd

BASE = "https://api.elections.kalshi.com/trade-api/v2"
# Kalshi sports series may change; add/adjust series after verifying actual event tickers.
SPORT_PREFIXES = {"CFB": ("KXNCAAF", "KXNCAAFGAME"), "NFL": ("KXNFL", "KXNFLGAME")}
COLUMNS = ["league", "ticker", "title", "yes_bid_cents", "yes_ask_cents",
           "no_bid_cents", "no_ask_cents", "spread_cents", "volume", "close_time"]

def _get(path, params=None):
    response = requests.get(BASE + path, params=params, timeout=18)
    response.raise_for_status()
    return response.json()

def _cents(m, key):
    # Prefer decimal-dollar string fields when provided; otherwise legacy integer cents.
    dollars = m.get(key + "_dollars")
    if dollars is not None:
        try:
            return round(float(dollars) * 100, 2)
        except (ValueError, TypeError):
            return None
    value = m.get(key)
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None

def _single_leg(m):
    # Exclude parlays / multi-outcome markets, while retaining individual game markets.
    t = (m.get("ticker") or "").upper()
    title = (m.get("title") or "").lower()
    if "MULTIGAME" in t or "PARLAY" in t or "combo" in title:
        return False
    if title.count(",yes ") + title.count(",no ") >= 1:
        return False
    return True

def fetch_sports_markets(leagues=("CFB", "NFL"), max_pages=12):
    """Paginate public open markets, filter by league ticker; not guaranteed exhaustive."""
    found = []
    cursor = None
    for _ in range(max_pages):
        params = {"limit": 1000, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/markets", params)
        for m in payload.get("markets", []):
            ticker = (m.get("ticker") or "").upper()
            league = next((name for name in leagues if ticker.startswith(SPORT_PREFIXES[name])), None)
            if not league or not _single_leg(m):
                continue
            yb, ya = _cents(m, "yes_bid"), _cents(m, "yes_ask")
            nb, na = _cents(m, "no_bid"), _cents(m, "no_ask")
            found.append({"league": league, "ticker": m.get("ticker", ""),
                          "title": m.get("title", ""), "yes_bid_cents": yb,
                          "yes_ask_cents": ya, "no_bid_cents": nb,
                          "no_ask_cents": na,
                          "spread_cents": round(ya-yb, 2) if ya is not None and yb is not None else None,
                          "volume": m.get("volume"), "close_time": m.get("close_time")})
        cursor = payload.get("cursor")
        if not cursor:
            break
    return pd.DataFrame(found, columns=COLUMNS)

def fetch_orderbook(ticker):
    """Public depth snapshot for a specific market; bids are not asks."""
    data = _get("/markets/" + requests.utils.quote(ticker, safe="") + "/orderbook")
    book = data.get("orderbook", {})
    return {"yes_bids": book.get("yes") or book.get("yes_dollars") or [],
            "no_bids": book.get("no") or book.get("no_dollars") or []}
