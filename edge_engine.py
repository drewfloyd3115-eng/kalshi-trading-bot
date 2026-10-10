"""Conservative, paper-only fair-value calculations. No external odds are invented."""
import math
from config import MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT

def no_vig(american_a, american_b):
    def implied(odds):
        if odds == 0:
            raise ValueError("American odds cannot be zero")
        return (-odds / (-odds + 100)) if odds < 0 else (100 / (odds + 100))
    a, b = implied(american_a), implied(american_b)
    return a / (a + b), b / (a + b)

def taker_fee(price_cents, shares, multiplier=1.0):
    p = price_cents / 100
    return math.ceil((0.07 * multiplier * shares * p * (1-p)) * 100 - 1e-9) / 100

def assess(yes_odds, no_odds, yes_ask, no_ask, bankroll, exposure=0,
           multiplier=1.0, available_yes=0, available_no=0):
    """Both sportsbook odds must represent exactly complementary outcomes."""
    fair_yes, fair_no = no_vig(yes_odds, no_odds)
    candidates = []
    for side, fair, ask, available in (("YES", fair_yes, yes_ask, available_yes),
                                        ("NO", fair_no, no_ask, available_no)):
        if ask is None or not (0 < ask < 100):
            continue
        budget = max(0, min(bankroll * MAX_TRADE_BANKROLL_PCT,
                            bankroll * MAX_TOTAL_EXPOSURE_PCT - exposure))
        shares = min(max(0, int(available)), int(budget / (ask/100))) 
        while shares > 0 and shares * ask / 100 + taker_fee(ask, shares, multiplier) > budget + 1e-9:
            shares -= 1
        if shares == 0:
            candidates.append({"side": side, "status": "NO TRADE", "reason": "No verified available depth or insufficient risk budget", "fair_pct": round(fair*100, 2), "ask_cents": ask, "shares": 0})
            continue
        fee = taker_fee(ask, shares, multiplier)
        edge = (fair - (ask/100 + fee/shares))*100
        candidates.append({"side": side, "status": "PAPER CANDIDATE" if edge >= MIN_EDGE_PP else "NO TRADE",
                           "reason": "Minimum 5pp net edge not met" if edge < MIN_EDGE_PP else "Requires fresh quote, fee and injury verification",
                           "fair_pct": round(fair*100, 2), "ask_cents": ask, "shares": shares,
                           "fee": fee, "cost": round(shares*ask/100 + fee, 2),
                           "net_edge_pp": round(edge, 2)})
    return sorted(candidates, key=lambda x: x.get("net_edge_pp", -999), reverse=True)
