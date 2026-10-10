"""Transparent, fail-closed paper inspection diagnostics; no network calls."""
def explain(result, comparison=None):
    reasons=[]
    timing=str(result.get("pregame_timing") or "")
    if timing.startswith("UNKNOWN"):
        reasons.append("KICKOFF UNVERIFIED — no qualifying fresh, independently matched kickoff.")
    elif timing!="PREGAME":
        reasons.append("GAME STARTED OR KICKOFF PASSED — pregame check blocked.")
    if str(result.get("market_status","")).lower() not in ("active","open"):
        reasons.append("MARKET NOT OPEN — contract status is not active/open.")
    if not result.get("depth_complete",False):
        reasons.append("DEPTH INSUFFICIENT — requested quantity not fully covered by public order book.")
    if not result.get("fee_schedule_verified",False):
        reasons.append("FEES UNVERIFIED — displayed fee is a general estimate, not a certified market fee.")
    if not result.get("settlement_rules_verified",False):
        reasons.append("SETTLEMENT RULES UNVERIFIED — verify the exact contract terms.")
    if not result.get("executable_price_verified",False):
        reasons.append("EXECUTION UNVERIFIED — public order-book snapshots can change.")
    edge=None
    if comparison is None:
        reasons.append("NO QUALIFYING SPORTSBOOK MATCH — no fresh, exact, independent fair-probability comparison for this side.")
    else:
        try:
            edge=float(comparison.get("net_edge_pp_1share"))
            if edge < 5:
                reasons.append("EDGE BELOW +5pp — preliminary one-share edge does not meet the research threshold.")
            else:
                reasons.append("PRELIMINARY EDGE >= +5pp — NOT VERIFIED after live depth, exact fees and settlement checks.")
        except (TypeError,ValueError):
            reasons.append("EDGE UNAVAILABLE — comparison could not be evaluated.")
    return {"status":"NO VERIFIED TRADE","edge_pp":edge,"edge_threshold_pp":5.0,
            "edge_filter":"NO COMPARISON" if edge is None else ("PRELIMINARY PASS — NOT VERIFIED" if edge>=5 else "FAIL"),
            "reasons":reasons}
