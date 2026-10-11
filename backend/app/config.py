"""Configuration constants and paths for Foresight."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import os


def configured_date(name, default):
    result = datetime.fromisoformat(os.environ.get(name, default))
    if result.tzinfo is not None and result.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")
    result = result.replace(tzinfo=timezone.utc)
    if (
        result.day != 1
        or result.hour
        or result.minute
        or result.second
        or result.microsecond
    ):
        raise ValueError(f"{name} must be a UTC month boundary")
    return result


# Root directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MANIFESTS_DIR = DATA_DIR / "manifests"
REPORTS_DIR = DATA_DIR / "reports"

# Ensure directories exist
for path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, MANIFESTS_DIR, REPORTS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Symbols & Market
PRIMARY_SYMBOL = "BTCUSDT"
CROSS_MARKET_SYMBOL = "ETHUSDT"
SUPPORTED_SYMBOLS = [PRIMARY_SYMBOL, CROSS_MARKET_SYMBOL]

DEFAULT_INTERVAL = "1h"
DEFAULT_SOURCE = "Binance Spot"
DEFAULT_TIMEZONE = "UTC"

# Coverage definition (half-open: [start, end))
DEFAULT_START_DATE = configured_date("FORESIGHT_START", "2022-10-01")
DEFAULT_END_DATE = configured_date("FORESIGHT_END", "2026-10-01")

# Expected complete count (48 months = 35,064 hours)
EXPECTED_TOTAL_HOURS = int(
    (DEFAULT_END_DATE - DEFAULT_START_DATE).total_seconds() // 3600
)

# Splits definition: half-open UTC intervals
SPLITS = {
    "training": {
        "name": "Training",
        "key": "training",
        "start": configured_date("FORESIGHT_START", "2022-10-01"),
        "end": configured_date("FORESIGHT_TRAIN_END", "2025-10-01"),
        "duration_months": 36,
        "expected_hours": 26304,
        "color": "#00f0ff",
        "badge_color": "cyan",
        "label": "TRAINING",
        "date_label": "Oct 2022 – Sep 2025",
    },
    "validation": {
        "name": "Validation",
        "key": "validation",
        "start": configured_date("FORESIGHT_TRAIN_END", "2025-10-01"),
        "end": configured_date("FORESIGHT_VALIDATION_END", "2026-06-01"),
        "duration_months": 8,
        "expected_hours": 5832,
        "color": "#f59e0b",
        "badge_color": "amber",
        "label": "VALIDATION",
        "date_label": "Oct 2025 – May 2026",
    },
    "final_test": {
        "name": "Final test",
        "key": "final_test",
        "start": configured_date("FORESIGHT_VALIDATION_END", "2026-06-01"),
        "end": configured_date("FORESIGHT_END", "2026-10-01"),
        "duration_months": 4,
        "expected_hours": 2928,
        "color": "#a855f7",
        "badge_color": "violet",
        "label": "FINAL TEST",
        "date_label": "Jun 2026 – Sep 2026",
        "note": "Held out for evaluation",
    },
}

# Train & Compare model families. The ten families in
# backend/app/forecasting/estimators.py stay available; this list picks which
# ones a comparison trains. Override with a comma-separated
# FORESIGHT_COMPARISON_FAMILIES, e.g. "direct-ridge-log-return,lightgbm,knn,catboost".
DEFAULT_COMPARISON_FAMILIES = ("direct-ridge-log-return", "lightgbm", "knn")
COMPARISON_FAMILIES = tuple(
    f.strip()
    for f in os.environ.get(
        "FORESIGHT_COMPARISON_FAMILIES", ",".join(DEFAULT_COMPARISON_FAMILIES)
    ).split(",")
    if f.strip()
)

# Binance public archive URL pattern
BINANCE_ARCHIVE_BASE = "https://data.binance.vision/data/spot/monthly/klines"

if (
    not DEFAULT_START_DATE
    < SPLITS["training"]["end"]
    < SPLITS["validation"]["end"]
    < DEFAULT_END_DATE
):
    raise ValueError("Chronological periods must be ordered")
for spec in SPLITS.values():
    spec["expected_hours"] = int((spec["end"] - spec["start"]).total_seconds() // 3600)
    spec["duration_months"] = (
        (spec["end"].year - spec["start"].year) * 12
        + spec["end"].month
        - spec["start"].month
    )
    spec["date_label"] = (
        spec["start"].strftime("%b %Y")
        + " – "
        + (spec["end"] - timedelta(seconds=1)).strftime("%b %Y")
    )
