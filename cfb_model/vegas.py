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
                        now=None, max_age_minutes: int=180) -> pd.DataFrame:
    """Exact team alias+kickoff match, robust price sign and chronological checks.

    The output uses model data game IDs and signed HOME handicap. A median is
    calculated across fresh independent bookmakers only. Provider prices stay
    available separately for audit. Ambiguous outcomes/duplicate matches block.
    """
    now=_utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(now):
        raise ValueError("Reference time must be timezone-aware")
    if not (1<=max_age_minutes<=180):
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
        # Prefer only fresh quotes; if ALL are older, show them as a visibly
        # aged research reference rather than quietly dropping all prices.
        fresh=[q for q in good if q["age_minutes"]<=MAX_QUOTE_AGE_MINUTES]
        selected=fresh if fresh else good
        verified=bool(fresh)
        line=float(pd.Series([x["home_handicap"] for x in selected]).median())
        rows.append({
            "game_id":game_id,"market_home_handicap":round(line,2),
            "market_provider":("Median of "+str(len(selected))+" US books" if len(selected)>1
                               else selected[0]["name"]),
            "market_observed_utc":now.isoformat(),
            "market_oldest_quote_minutes":round(max(q["age_minutes"] for q in selected),1),
            "market_book_count":len(selected),
            "market_verification":("ODDS_API_FRESH" if verified
                                   else "ODDS_API_OLDER_REFERENCE"),
            "book_details":selected
        })
    return pd.DataFrame(rows)


def explain_unmatched_vegas(schedule: pd.DataFrame, odds_events: list,
                           now=None) -> dict:
    """Explain absent bookmaker lines without extra API calls or key exposure.

    Categories describe source-data conditions; they do not claim that
    sportsbooks have no real line. Never log full odds payloads or credentials.
    """
    clock=_utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(clock) or not isinstance(odds_events,list):
        raise ValueError("Unable to diagnose missing sportsbook data")
    aliases=schedule.attrs.get("espn_event_aliases",{})
    reasons={}
    for _,game in schedule.iterrows():
        gid=str(game.game_id)
        meta=aliases.get(gid,{})
        home=_alias_set(meta.get("home",[]))|_alias_set([str(game.home_team)])
        away=_alias_set(meta.get("away",[]))|_alias_set([str(game.away_team)])
        named=[e for e in odds_events if isinstance(e,dict) and
               str(e.get("home_team","")).strip().casefold() in home and
               str(e.get("away_team","")).strip().casefold() in away]
        if not named:
            reasons[gid]="NOT_IN_FEED_OR_TEAM_NAME_MISMATCH"
            continue
        start=_utc(game.kickoff_utc)
        aligned=[e for e in named if pd.notna(_utc(e.get("commence_time"))) and
                 abs((_utc(e.get("commence_time"))-start).total_seconds())<=90*60]
        if not aligned:
            reasons[gid]="KICKOFF_MISMATCH"
            continue
        if len(aligned)!=1:
            reasons[gid]="AMBIGUOUS_DUPLICATE_EVENTS"
            continue
        markets=[m for b in (aligned[0].get("bookmakers") or [])
                 if isinstance(b,dict) for m in (b.get("markets") or [])
                 if isinstance(m,dict) and m.get("key")=="spreads"]
        if not markets:
            reasons[gid]="NO_SPREAD_MARKET_IN_API_RESPONSE"
            continue
        # This initial reason tracks quote timestamps; actual outcome/sign validation
        # happens in match_fresh_spreads, with a separate terminal reason.
        ages=[(clock-t).total_seconds()/60 for m in markets
              for t in [_utc(m.get("last_update"))] if pd.notna(t)]
        if not ages:
            reasons[gid]="NO_USABLE_QUOTE_TIMESTAMP"
        elif not any(-2<=age<=180 for age in ages):
            reasons[gid]="QUOTES_OVER_180_MIN_OLD_OR_FUTURE_DATED"
        elif not any(-2<=age<=15 for age in ages):
            reasons[gid]="QUOTES_OLDER_THAN_15_MIN"
        else:
            reasons[gid]="SPREAD_OUTCOME_OR_SIGN_UNMATCHED"
    return {"events_returned":len(odds_events),"per_game":reasons}
