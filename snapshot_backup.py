"""Portable research snapshots; strictly no trade authorization or API calls."""
import io
import pandas as pd
from matcher import parse_time

REQUIRED = {"ticker", "side", "ask_cents", "net_edge_pp_1share"}
MAX_BYTES = 1_000_000

def export_snapshot(matches, league, scan_time):
    if league not in ("CFB", "NFL") or not parse_time(scan_time):
        raise ValueError("Invalid snapshot metadata")
    if not isinstance(matches, pd.DataFrame) or not REQUIRED.issubset(matches.columns):
        raise ValueError("Missing snapshot comparison columns")
    out = matches.copy()
    out["snapshot_league"] = league
    out["snapshot_time_utc"] = scan_time
    return out.to_csv(index=False).encode("utf-8")

def import_snapshot(data, expected_league, current_time=None):
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise ValueError("Snapshot file empty or too large")
    frame = pd.read_csv(io.BytesIO(data), dtype={"ticker": str, "side": str}, on_bad_lines="error")
    if frame.empty or len(frame) > 5000 or not (REQUIRED | {"snapshot_league", "snapshot_time_utc"}).issubset(frame.columns):
        raise ValueError("Not a valid Kalshi research snapshot")
    if frame["snapshot_league"].isna().any() or set(frame["snapshot_league"]) != {expected_league}:
        raise ValueError("Snapshot league does not match selected league")
    times = frame["snapshot_time_utc"].dropna().unique()
    if len(times) != 1 or not parse_time(times[0]):
        raise ValueError("Snapshot timestamp missing or inconsistent")
    timestamp = parse_time(times[0])
    if current_time is not None and (not parse_time(current_time) or timestamp >= parse_time(current_time)):
        raise ValueError("Previous snapshot must be older than the current scan")
    if frame[["ticker", "side"]].isna().any().any() or frame.duplicated(["ticker", "side"]).any():
        raise ValueError("Missing or duplicate contract routes")
    if not frame["side"].isin(["YES", "NO"]).all():
        raise ValueError("Unexpected contract side")
    for column in ("ask_cents", "net_edge_pp_1share"):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.isna().any():
            raise ValueError("Invalid numeric quote data")
        frame[column] = numeric
    if not frame["ask_cents"].between(0, 100).all():
        raise ValueError("Invalid quote range")
    return {"time": str(times[0]), "matches": frame.drop(columns=["snapshot_league", "snapshot_time_utc"])}
