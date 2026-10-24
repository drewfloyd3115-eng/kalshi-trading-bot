"""Central Time formatting for app *presentation* only.

All model calculations, order timestamps, eligibility checks and exported audit
records stay UTC. We never assign a timezone to naive timestamps because doing
so could misrepresent event timing and compromise pregame checks.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

CENTRAL = ZoneInfo("America/Chicago")

UI_COLUMN_LABELS = {
    "kickoff_utc": "Kickoff (Central)",
    "recorded_at_utc": "Recorded (Central)",
    "scan_utc": "Scan (Central)",
    "captured_utc": "Captured (Central)",
    "market_observed_utc": "Market observed (Central)",
    "close_time": "Market closes (Central)",
    "updated_time": "Market updated (Central)",
}


def format_central(value, missing="Unverified") -> str:
    """Render timezone-aware UTC/offset timestamps with correct CST/CDT.

    Naive datetime inputs, missing strings and invalid timestamps are not
    converted. Source timestamps are untouched by this function.
    """
    if value is None:
        return missing
    try:
        parsed = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError):
        return missing
    if pd.isna(parsed) or parsed.tzinfo is None:
        return missing
    try:
        return parsed.tz_convert(CENTRAL).strftime("%b %d, %Y %I:%M %p %Z")
    except (ValueError, TypeError, OverflowError):
        return missing


def display_central_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Non-mutating dataframe copy with human Central-time display columns.

    Raw source CSV and backing data remain UTC, even when we show human-readable
    localized times in Streamlit tables. Unknown time columns are left unchanged.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Expected a DataFrame")
    view = frame.copy()
    for original, label in UI_COLUMN_LABELS.items():
        if original in view.columns:
            if label in view.columns:
                raise ValueError(f"Cannot rename {original}: {label} already exists")
            view[original] = view[original].map(
                lambda x: format_central(x, missing="—"))
            view = view.rename(columns={original: label})
    return view
