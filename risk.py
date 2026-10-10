"""Pure functions for candidate evaluation; never place an order."""
from config import MIN_EDGE_PP, MAX_TRADE_BANKROLL_PCT, MAX_TOTAL_EXPOSURE_PCT

def evaluate(side, fair_probability, ask_price, fee_dollars, contracts, bankroll, open_exposure):
    if side not in ("YES", "NO"):
        raise ValueError("side must be YES or NO")
    if not (0 <= fair_probability <= 1 and 0 < ask_price < 1):
        raise ValueError("probabilities and price must be valid fractions")
    if contracts < 1 or bankroll <= 0 or fee_dollars < 0:
        raise ValueError("invalid risk inputs")
    effective_price = ask_price + fee_dollars / contracts
    edge_pp = 100 * (fair_probability - effective_price)
    cost = contracts * ask_price + fee_dollars
    reasons = []
    if edge_pp < MIN_EDGE_PP:
        reasons.append("Edge below minimum 5 percentage points after entered fees")
    if cost > bankroll * MAX_TRADE_BANKROLL_PCT:
        reasons.append("Trade exceeds 1% bankroll cap")
    if open_exposure + cost > bankroll * MAX_TOTAL_EXPOSURE_PCT:
        reasons.append("Total exposure exceeds 3% bankroll cap")
    return {"edge_pp": round(edge_pp, 2), "cost": round(cost, 2), "status": "PAPER CANDIDATE" if not reasons else "REJECT", "reasons": reasons}
