"""Read-only summary of all sportsbook games, including exclusions."""
import pandas as pd

def coverage_funnel(odds, diagnostics, comparisons):
    if diagnostics is None or diagnostics.empty:
        return pd.DataFrame()
    result=diagnostics.copy()
    result["status"]=result["reason"].apply(
        lambda reason: "EXCLUDED" if "candidate found" not in str(reason).lower() else "CANDIDATE — further checks required")
    return result
