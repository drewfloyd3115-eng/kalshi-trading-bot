"""Read-only coverage and price-quality summary using already cached scan data.

No network calls; never converts a candidate into an approved trade.
"""
import pandas as pd


def discovery_report(markets, odds, funnel, comparisons):
    market_count = len(markets) if markets is not None else 0
    odds_count = len(odds) if odds is not None else 0
    matched_count = len(comparisons) if comparisons is not None else 0
    if funnel is None or funnel.empty:
        return {"markets": market_count, "sportsbook_rows": odds_count,
                "sportsbook_games": 0, "matched_games": 0, "candidate_games": 0,
                "excluded_games": 0, "matched_sides": matched_count}, pd.DataFrame()
    data = funnel.copy()
    data["matched_contract_sides"] = pd.to_numeric(
        data.get("matched_contract_sides", 0), errors="coerce").fillna(0).astype(int)
    data["kalshi_event_candidates"] = pd.to_numeric(
        data.get("kalshi_event_candidates", 0), errors="coerce").fillna(0).astype(int)
    def category(row):
        if row["matched_contract_sides"] > 0:
            return "MATCHED"
        if row["kalshi_event_candidates"] > 0:
            return "CANDIDATE — UNMATCHED"
        return "NO EXACT EVENT"
    data["coverage_stage"] = data.apply(category, axis=1)
    if "pregame_timing" not in data.columns:
        data["pregame_timing"] = "UNKNOWN"
    data["pregame_timing"] = data["pregame_timing"].fillna("UNKNOWN")
    data["partial_event_candidates"] = data.get("partial_event_candidates", pd.Series("", index=data.index)).fillna("").astype(str)
    data["next_check"] = data.apply(lambda r:
        "Game already started; pregame evaluation prohibited" if r["pregame_timing"] == "PASSED"
        else ("Independent kickoff missing; exclude until verified" if r["pregame_timing"] == "UNKNOWN"
        else ("Matched; check estimated edge and independent verification" if r["coverage_stage"] == "MATCHED"
        else ("Inspect outcome labels, ticker date, pricing and quote validity" if r["coverage_stage"] == "CANDIDATE — UNMATCHED"
        else ("Check exact matchup and date in nearby Kalshi events; aliases are diagnostic only" if r["partial_event_candidates"] else "No related Kalshi event in scanned pages; check market availability or scan coverage")))), axis=1)
    priority = {"CANDIDATE — UNMATCHED": 0, "NO EXACT EVENT": 1, "MATCHED": 2}
    data["_priority"] = data["coverage_stage"].map(priority)
    data = data.sort_values(["_priority", "fresh_rows"], ascending=[True, False]).drop(columns="_priority")
    metrics = {"markets": market_count, "sportsbook_rows": odds_count,
               "sportsbook_games": len(data),
               "matched_games": int((data["coverage_stage"] == "MATCHED").sum()),
               "candidate_games": int((data["coverage_stage"] == "CANDIDATE — UNMATCHED").sum()),
               "excluded_games": int((data["coverage_stage"] == "NO EXACT EVENT").sum()),
               "matched_sides": matched_count}
    return metrics, data
