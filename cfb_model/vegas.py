"""One manual The Odds API CFB spreads request, exact-source team identity matching.

No fuzzy matching and no bookmaker lines generated from ESPN point projections.
The API credits are used only when the user presses the evening Refresh control.
The response is kept for this session; never expose credentials in exceptions.
"""
from __future__ import annotations

import re
import requests
import pandas as pd

ODDS_URL="https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds/"
MAX_QUOTE_AGE_MINUTES=15


def _utc(value):
    try:
        result=pd.Timestamp(value)
    except (ValueError,TypeError,OverflowError):
        return pd.NaT
    if pd.isna(result) or result.tzinfo is None:
        return pd.NaT
    return result.tz_convert("UTC")


def fetch_vegas_spreads(api_key: str, session=None) -> tuple[list, str | None]:
    """Fetch a single, explicitly user-initiated CFB *spreads* market request."""
    if not api_key or not api_key.strip():
        raise ValueError("ODDS_API_KEY is not configured")
    client=session or requests
    try:
        response=client.get(ODDS_URL,params={
            "apiKey":api_key,"regions":"us","markets":"spreads",
            "oddsFormat":"american"},timeout=20)
        if not response.ok:
            raise ValueError(f"Vegas odds endpoint HTTP {response.status_code}")
        data=response.json()
        if not isinstance(data,list):
            raise ValueError("Vegas odds response was not an event list")
        return data,response.headers.get("x-requests-remaining")
    except requests.RequestException as exc:
        # Never return exception URL/headers, which might expose API credentials.
        raise ValueError("Vegas odds endpoint unavailable or connection failed") from None


def _alias_set(values):
    """Only source-confirmed ESPN aliases, no guesses or mascot stripping."""
    return {re.sub(r"\s+"," ",str(v).strip()).casefold()
            for v in values if isinstance(v,str) and v.strip()}


def match_fresh_spreads(schedule: pd.DataFrame, odds_events: list,
                        now=None, max_age_minutes: int=MAX_QUOTE_AGE_MINUTES) -> pd.DataFrame:
    """Exact team alias+kickoff match, robust price sign and chronological checks.

    The output uses model data game IDs and signed HOME handicap. A median is
    calculated across fresh independent bookmakers only. Provider prices stay
    available separately for audit. Ambiguous outcomes/duplicate matches block.
    """
    now=_utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(now):
        raise ValueError("Reference time must be timezone-aware")
    if not (1<=max_age_minutes<=60):
        raise ValueError("Invalid quote-age threshold")
    if not isinstance(schedule,pd.DataFrame) or schedule.empty:
        return pd.DataFrame()
    if not isinstance(odds_events,list):
        raise ValueError("Vegas odds payload must be an event list")
    alias_meta=schedule.attrs.get("espn_event_aliases",{})
    rows=[]
    seen_event_ids=set()
    for _,game in schedule.iterrows():
        game_id=str(game.game_id)
        aliases=alias_meta.get(game_id,{})
        home_set=_alias_set(aliases.get("home",[]))
        away_set=_alias_set(aliases.get("away",[]))
        # Add exact historically verified FBS names (not shortened guesses).
        home_set |= _alias_set([str(game.home_team)])
        away_set |= _alias_set([str(game.away_team)])
        if not home_set or not away_set or home_set.intersection(away_set):
            continue
        kickoff=_utc(game.kickoff_utc)
        if pd.isna(kickoff) or kickoff<=now:
            continue
        matches=[]
        for event in odds_events:
            if not isinstance(event,dict):continue
            if not (str(event.get("home_team","")).strip().casefold() in home_set and
                    str(event.get("away_team","")).strip().casefold() in away_set):
                continue
            start=_utc(event.get("commence_time"))
            if pd.isna(start) or abs((start-kickoff).total_seconds())>90*60:
                continue
            matches.append(event)
        # Single unambiguous market event. Two duplicates aren't safely resolvable.
        if len(matches)!=1:
            continue
        event=matches[0]
        event_id=str(event.get("id",""))
        if not event_id or event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        book_rows=[]
        for book in event.get("bookmakers") or []:
            if not isinstance(book,dict):continue
            book_key=str(book.get("key") or "").strip()
            if not book_key:continue
            for market in book.get("markets") or []:
                if not isinstance(market,dict) or market.get("key")!="spreads":
                    continue
                updated=_utc(market.get("last_update") or book.get("last_update"))
                if pd.isna(updated):continue
                age=(now-updated).total_seconds()/60
                if age < -2 or age>max_age_minutes:continue
                quotes=market.get("outcomes") or []
                if len(quotes)!=2:continue
                h=[x for x in quotes if isinstance(x,dict) and
                   str(x.get("name","")).strip().casefold() in home_set]
                a=[x for x in quotes if isinstance(x,dict) and
                   str(x.get("name","")).strip().casefold() in away_set]
                if len(h)!=1 or len(a)!=1:continue
                try:
                    hline=float(h[0]["point"])
                    aline=float(a[0]["point"])
                except (TypeError,ValueError,KeyError,OverflowError):
                    continue
                if not all(pd.notna(v) and abs(v)<80 for v in (hline,aline)):
                    continue
                if abs(hline+aline)>.01:
                    continue
                book_rows.append({"key":book_key,"name":str(book.get("title") or book_key),
                                  "home_handicap":hline,"updated_utc":updated.isoformat(),
                                  "age_minutes":round(age,1)})
        # A bookmaker can have repeated spread markets; retain newest unique key.
        book_rows.sort(key=lambda b:b["updated_utc"],reverse=True)
        unique={}
        for q in book_rows:unique.setdefault(q["key"],q)
        good=list(unique.values())
        if not good:continue
        line=float(pd.Series([x["home_handicap"] for x in good]).median())
        rows.append({
            "game_id":game_id,"market_home_handicap":round(line,2),
            "market_provider":("Median of "+str(len(good))+" US books" if len(good)>1
                               else good[0]["name"]),
            "market_observed_utc":now.isoformat(),
            "market_oldest_quote_minutes":round(max(q["age_minutes"] for q in good),1),
            "market_book_count":len(good),
            "market_verification":"ODDS_API_FRESH",
            "book_details":good
        })
    return pd.DataFrame(rows)
