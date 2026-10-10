"""Free-tier outside odds fetch. Requires Streamlit secret; never log the key."""
import requests
from datetime import datetime, timezone

SPORTS = {"CFB": "americanfootball_ncaaf", "NFL": "americanfootball_nfl"}
URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds/"

def fetch_odds(api_key, league):
    if not api_key:
        raise ValueError("Add ODDS_API_KEY to Streamlit secrets first")
    if league not in SPORTS:
        raise ValueError("Unsupported league")
    response = requests.get(URL.format(sport=SPORTS[league]),
        params={"apiKey": api_key, "regions": "us", "markets": "h2h",
                "oddsFormat": "american"}, timeout=20)
    if not response.ok:
        raise ValueError("Outside odds feed returned HTTP " + str(response.status_code))
    rows = []
    for event in response.json():
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                rows.append({"league": league, "home": event.get("home_team"),
                    "away": event.get("away_team"), "start": event.get("commence_time"),
                    "book": book.get("title"), "book_key": book.get("key"), "event_id": event.get("id"), "updated": market.get("last_update") or book.get("last_update"),
                    "team_a": outcomes[0].get("name"), "odds_a": outcomes[0].get("price"),
                    "team_b": outcomes[1].get("name"), "odds_b": outcomes[1].get("price")})
    return rows, response.headers.get("x-requests-remaining")
