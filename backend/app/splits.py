"""Chronological split calculation and forecasting safeguards."""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import pandas as pd
from backend.app.config import SPLITS

# Documentation of Future Forecasting Safeguards per Section 6
FORECASTING_SAFEGUARDS = {
    "no_random_splits": (
        "Time-series data must never be split randomly or shuffled. "
        "Strict chronological ordering is required to prevent lookahead leakage."
    ),
    "preprocessing_fitted_on_train_only": (
        "Any scaling, normalization, feature encoding, or imputation must be fit strictly "
        "on the training split (2022-10-01 to 2025-10-01) and transformed onto validation and test splits."
    ),
    "target_horizon_boundary_protection": (
        "Future multi-day prediction targets (e.g., 7-day forward horizon) computed near split boundaries "
        "must not cross into the subsequent split. Training targets must terminate strictly before 2025-10-01 00:00:00 UTC. "
        "Validation targets must terminate strictly before 2026-06-01 00:00:00 UTC."
    ),
    "lookback_context_allowed": (
        "Lagged feature windows (look-back context) may draw from earlier split observations to form features "
        "for points at the beginning of validation or test periods, as this represents historical knowledge."
    ),
    "evaluation_sufficiency": (
        "Final 7-day outcome labels require sufficient subsequent data; observations without full forward horizon "
        "must be handled explicitly without truncating ground truth."
    )
}

def make_splits(boundaries, calendar, colors=None):
    """Build a market's split table from four UTC boundaries.

    ``boundaries`` is (start, training_end, validation_end, end), half-open and
    strictly increasing. Expected bar counts come from the market calendar, so a
    session-based market gets session counts rather than 24 x days.
    """
    start, train_end, val_end, end = boundaries
    if not start < train_end < val_end < end:
        raise ValueError("Chronological periods must be ordered")
    colors = colors or {}
    defaults = {
        "training": ("Training", "TRAINING", "#00f0ff", "cyan", None),
        "validation": ("Validation", "VALIDATION", "#f59e0b", "amber", None),
        "final_test": ("Final test", "FINAL TEST", "#a855f7", "violet", "Held out for evaluation"),
    }
    result = {}
    for key, (a, b) in zip(defaults, ((start, train_end), (train_end, val_end), (val_end, end))):
        name, label, color, badge, note = defaults[key]
        spec = {
            "name": name,
            "key": key,
            "start": a,
            "end": b,
            "duration_months": (b.year - a.year) * 12 + b.month - a.month,
            "expected_hours": calendar.expected_count(a, b),
            "color": colors.get(key, color),
            "badge_color": badge,
            "label": label,
            "date_label": a.strftime("%b %Y")
            + " – "
            + (b - timedelta(seconds=1)).strftime("%b %Y"),
        }
        if note:
            spec["note"] = note
        result[key] = spec
    return result


def get_split_for_timestamp(dt: datetime, splits=None) -> str:
    """Return split key ('training', 'validation', 'final_test') for a given UTC datetime.
    
    Uses exact half-open UTC intervals:
    - Training:   [2022-10-01, 2025-10-01)
    - Validation: [2025-10-01, 2026-06-01)
    - Final test: [2026-06-01, 2026-10-01)
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
        
    for key, spec in (splits or SPLITS).items():
        if spec["start"] <= dt < spec["end"]:
            return key
    return "out_of_bounds"

def assign_splits_to_dataframe(
    df: pd.DataFrame, timestamp_col: str = "open_time", splits=None
) -> pd.DataFrame:
    """Assign split column to a pandas DataFrame containing UTC open_time.

    ``splits`` is a market's split table (MarketSpec.splits); defaults to config.SPLITS.
    """
    if df.empty:
        df["split"] = []
        return df

    splits = splits or SPLITS
    ts = pd.to_datetime(df[timestamp_col], utc=True)

    df["split"] = "out_of_bounds"
    for key, spec in splits.items():
        df.loc[(ts >= spec["start"]) & (ts < spec["end"]), "split"] = key

    return df

def calculate_split_summaries(df: pd.DataFrame, splits=None) -> Dict[str, Dict[str, Any]]:
    """Calculate actual counts, percentages, and metadata for each split."""
    total_candles = len(df)
    summaries = {}

    for key, spec in (splits or SPLITS).items():
        if total_candles > 0 and "split" in df.columns:
            actual_count = int((df["split"] == key).sum())
            percentage = round((actual_count / total_candles) * 100, 2)
        else:
            actual_count = 0
            percentage = 0.0
            
        summary = {
            "key": key,
            "name": spec["name"],
            "label": spec["label"],
            "date_label": spec["date_label"],
            "duration_months": spec["duration_months"],
            "start": spec["start"].isoformat(),
            "end": spec["end"].isoformat(),
            "expected_count": spec["expected_hours"],
            "actual_count": actual_count,
            "percentage": percentage,
            "color": spec["color"],
            "note": spec.get("note")
        }
        summaries[key] = summary
        
    return summaries
