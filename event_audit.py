"""Audit possible event/outcome matches without authorizing trades."""
import re
import pandas as pd
from datetime import datetime, timezone
from team_names import normalized, contains_team
from matcher import parse_time

def audit(markets, odds):
    cols=["game","kickoff_utc","kalshi_event","ticker","market_title","yes_outcome",
          "event_match","outcome_match","reason"]
    if markets is None or odds is None or markets.empty or odds.empty:
        return pd.DataFrame(columns=cols)
    now=datetime.now(timezone.utc)
    records=[]
    for (league,home,away), group in odds.groupby(["league","home","away"]):
        kickoff=parse_time(group.iloc[0].get("start"))
        if kickoff is None or kickoff<=now:
            continue
        home_key,away_key=normalized(home),normalized(away)
        if not home_key or not away_key or home_key==away_key:
            continue
        for _,m in markets[markets["league"]==league].iterrows():
            event=str(m.get("event",""))
            if not (contains_team(event,home_key) and contains_team(event,away_key)):
                continue
            title=str(m.get("title",""))
            yes=str(m.get("yes_sub_title","") or "")
            # Only identify a team if precisely one appears in outcome metadata.
            outcome_text=yes or title
            hit_home=contains_team(outcome_text,home_key)
            hit_away=contains_team(outcome_text,away_key)
            unique=hit_home!=hit_away
            # Do not treat substring matches as verified opponents.
            records.append({"game":str(away)+" @ "+str(home),
                "kickoff_utc":kickoff.isoformat(),"kalshi_event":event,
                "ticker":m.get("ticker"),"market_title":title,
                "yes_outcome":yes,"event_match":"POSSIBLE",
                "outcome_match":"UNVERIFIED" if not unique else "SINGLE TEAM LABEL",
                "reason":"Requires event date, settlement rule and exact outcome verification"})
    return pd.DataFrame(records,columns=cols)
