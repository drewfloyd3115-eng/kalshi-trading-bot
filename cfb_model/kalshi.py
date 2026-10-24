"""No-auth, read-only Kalshi public market + orderbook access. No trading methods."""
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _get(path):
    response=requests.get(BASE+path,timeout=18)
    response.raise_for_status()
    return response.json()


def fetch_market_and_orderbook(ticker):
    ticker=ticker.strip().upper()
    if not ticker or len(ticker)>160 or not all(c.isalnum() or c in '-_' for c in ticker):
        raise ValueError("Invalid exact Kalshi ticker")
    from requests.utils import quote
    uri=quote(ticker,safe='')
    market=_get('/markets/'+uri).get('market')
    if not isinstance(market,dict) or market.get('ticker','').upper()!=ticker:
        raise ValueError("Public market metadata did not match exact ticker")
    payload=_get('/markets/'+uri+'/orderbook')
    if isinstance(payload.get('orderbook_fp'),dict):
        fp=payload['orderbook_fp']
        yes,no=fp.get('yes_dollars'),fp.get('no_dollars')
        multiple=100
    elif isinstance(payload.get('orderbook'),dict):
        legacy=payload['orderbook']
        yes,no=legacy.get('yes'),legacy.get('no')
        multiple=1
    else:
        raise ValueError("Unrecognized order-book response; fail closed")
    def levels(rows):
        if isinstance(rows,dict): rows=rows.get('bids')
        if rows is None:return []
        out=[]
        for row in rows:
            try:
                price,qty=float(row[0])*multiple,float(row[1])
                if 0<price<100 and qty>=1:
                    out.append([round(price,4),qty])
            except (IndexError,ValueError,TypeError):continue
        return out
    return market,{'yes_bids':levels(yes),'no_bids':levels(no)}
