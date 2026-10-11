"""Data quality validation engine for Foresight market datasets.

Coverage, expected bar grid and alignment come from the market's calendar, so the
same checks work for any registered market. Unregistered symbols use the project
defaults (24/7 hourly bars over the configured coverage).
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from backend.app.config import (
    DEFAULT_START_DATE,
    DEFAULT_END_DATE,
)
from backend.app.markets import ContinuousCalendar, get_market


def validate_dataset(
    df: pd.DataFrame,
    symbol: str,
    cross_market_df: Optional[pd.DataFrame] = None,
    market=None,
) -> Dict[str, Any]:
    """Perform rigorous validation checks on parsed cryptocurrency klines dataset.

    Checks performed:
    1. Positive, finite prices (open, high, low, close)
    2. Non-negative volumes and trade counts
    3. Valid OHLC relationships (high >= low, high >= open, high >= close, low <= open, low <= close)
    4. Timestamp ordering, continuity, and exact hourly alignment (minute=0, second=0)
    5. Detection of duplicates and conflicting duplicates
    6. Identification of missing hourly gaps (without synthesizing or forward-filling)
    7. Requested vs actual coverage comparisons
    8. Cross-market timestamp alignment (BTCUSDT vs ETHUSDT)
    """
    issues: List[Dict[str, Any]] = []
    market = market or get_market(symbol, None)
    if market is not None:
        calendar = market.calendar
        coverage_start, coverage_end = market.coverage_start, market.coverage_end
    else:
        calendar = ContinuousCalendar(3600)
        coverage_start, coverage_end = DEFAULT_START_DATE, DEFAULT_END_DATE
    expected_total = calendar.expected_count(coverage_start, coverage_end)
    interval = timedelta(seconds=calendar.interval_seconds)
    bar_word = "hourly" if calendar.interval_seconds == 3600 else "expected"

    if df.empty:
        return {
            "symbol": symbol,
            "status": "awaiting_import",
            "is_verified": False,
            "total_expected": expected_total,
            "total_actual": 0,
            "completeness_percentage": 0.0,
            "missing_hours_count": expected_total,
            "missing_intervals": [],
            "duplicate_count": 0,
            "conflicting_duplicate_count": 0,
            "invalid_ohlc_count": 0,
            "negative_volume_count": 0,
            "non_positive_price_count": 0,
            "timestamp_alignment_valid": False,
            "coverage_start": None,
            "coverage_end": None,
            "cross_market_aligned": None,
            "issues": [{"category": "Empty", "description": "No data imported yet."}],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    total_actual = len(df)

    # 1. Price validity checks (finite and > 0)
    price_cols = ["open", "high", "low", "close"]
    non_positive_price_mask = pd.Series(False, index=df.index)
    for col in price_cols:
        non_positive_price_mask |= (df[col] <= 0) | df[col].isna() | np.isinf(df[col])
    non_positive_price_count = int(non_positive_price_mask.sum())
    if non_positive_price_count > 0:
        issues.append(
            {
                "category": "Price Validity",
                "description": f"Found {non_positive_price_count} records with non-positive or non-finite prices.",
                "count": non_positive_price_count,
            }
        )

    # 2. Volume & trade count validity (non-negative)
    vol_cols = [
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    negative_vol_mask = pd.Series(False, index=df.index)
    for col in vol_cols:
        if col in df.columns:
            negative_vol_mask |= (df[col] < 0) | df[col].isna() | ~np.isfinite(df[col])
    if "trade_count" in df.columns:
        negative_vol_mask |= df["trade_count"] % 1 != 0
    negative_vol_count = int(negative_vol_mask.sum())
    if negative_vol_count > 0:
        issues.append(
            {
                "category": "Volume Validity",
                "description": f"Found {negative_vol_count} records with negative or non-finite volumes or trade counts.",
                "count": negative_vol_count,
            }
        )

    # 3. OHLC relationship checks
    invalid_ohlc_mask = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )
    invalid_ohlc_count = int(invalid_ohlc_mask.sum())
    if invalid_ohlc_count > 0:
        issues.append(
            {
                "category": "OHLC Inconsistency",
                "description": f"Found {invalid_ohlc_count} records where High/Low/Open/Close bounds were violated.",
                "count": invalid_ohlc_count,
            }
        )

    # 4. Duplicate checks
    open_times = pd.to_datetime(df["open_time"], utc=True)
    exact_duplicates = df.duplicated(subset=["open_time"], keep=False)
    duplicate_count = int(exact_duplicates.sum())

    conflicting_duplicate_count = 0
    if duplicate_count > 0:
        # Check if values differ across duplicates
        grouped = df.groupby("open_time")
        for _, group in grouped:
            if len(group) > 1:
                if not (
                    group[
                        price_cols
                        + [c for c in vol_cols if c in group.columns]
                        + (["close_time"] if "close_time" in group.columns else [])
                    ].nunique(dropna=False)
                    == 1
                ).all():
                    conflicting_duplicate_count += 1
        issues.append(
            {
                "category": "Duplicates",
                "description": f"Found {duplicate_count} duplicated timestamps ({conflicting_duplicate_count} conflicting).",
                "count": duplicate_count,
            }
        )

    # 5. Timestamp alignment: hourly alignment (minute=0, second=0) and ordering
    minute_align_mask = calendar.misaligned(open_times)
    is_hourly_aligned = bool((~minute_align_mask).all())
    if not is_hourly_aligned:
        issues.append(
            {
                "category": "Timestamp Alignment",
                "description": (
                    "Some records do not start on exact hourly marks (00:00:00)."
                    if calendar.interval_seconds == 3600
                    else "Some records do not start on exact bar boundaries."
                ),
                "count": int(minute_align_mask.sum()),
            }
        )

    is_monotonic_increasing = bool(open_times.is_monotonic_increasing)
    if not is_monotonic_increasing:
        issues.append(
            {
                "category": "Timestamp Ordering",
                "description": "Timestamps are not strictly monotonically increasing.",
                "count": 1,
            }
        )

    # 6. Gaps & Missing hourly intervals
    # Generate expected hourly sequence
    coverage_start_dt = (
        open_times.min().to_pydatetime() if not open_times.empty else coverage_start
    )
    coverage_end_dt = (
        open_times.max().to_pydatetime() if not open_times.empty else coverage_end
    )

    # Calculate full expected hourly grid between configured coverage
    expected_full_grid = calendar.expected_open_times(coverage_start, coverage_end)

    existing_timestamps_set = set(open_times)
    missing_grid = [t for t in expected_full_grid if t not in existing_timestamps_set]
    missing_hours_count = len(missing_grid)

    missing_intervals: List[Dict[str, str]] = []
    if missing_hours_count > 0:
        # Group contiguous missing hours into intervals
        missing_sorted = sorted(missing_grid)
        curr_start = missing_sorted[0]
        curr_end = missing_sorted[0]
        for t in missing_sorted[1:]:
            if t == curr_end + interval:
                curr_end = t
            else:
                missing_intervals.append(
                    {
                        "start": curr_start.isoformat(),
                        "end": (curr_end + interval).isoformat(),
                        "hours": str(int((curr_end - curr_start) / interval + 1)),
                    }
                )
                curr_start = t
                curr_end = t
        missing_intervals.append(
            {
                "start": curr_start.isoformat(),
                "end": (curr_end + interval).isoformat(),
                "hours": str(int((curr_end - curr_start) / interval + 1)),
            }
        )
        issues.append(
            {
                "category": "Coverage Gaps",
                "description": f"Missing {missing_hours_count} {bar_word} records in configured range.",
                "count": missing_hours_count,
            }
        )

    # 7. Cross-market timestamp alignment check
    cross_market_aligned = None
    if cross_market_df is not None and not cross_market_df.empty:
        other_times = pd.to_datetime(cross_market_df["open_time"], utc=True)
        if (
            len(open_times) == len(other_times)
            and (open_times.values == other_times.values).all()
        ):
            cross_market_aligned = True
        else:
            cross_market_aligned = False
            issues.append(
                {
                    "category": "Cross-Market Alignment",
                    "description": f"Timestamp alignment mismatch with cross-market dataset ({len(open_times)} vs {len(other_times)}).",
                    "count": 1,
                }
            )

    completeness_percentage = round((total_actual / expected_total) * 100, 6)
    is_verified = (
        len(issues) == 0
        and total_actual == expected_total
        and non_positive_price_count == 0
        and negative_vol_count == 0
        and invalid_ohlc_count == 0
        and duplicate_count == 0
        and is_hourly_aligned
        and is_monotonic_increasing
    )

    status = (
        "verified"
        if is_verified
        else ("warnings" if total_actual > 0 else "awaiting_import")
    )

    return {
        "symbol": symbol,
        "status": status,
        "is_verified": is_verified,
        "total_expected": expected_total,
        "total_actual": total_actual,
        "completeness_percentage": completeness_percentage,
        "missing_hours_count": missing_hours_count,
        "missing_intervals": missing_intervals[:10],  # Keep top 10 for UI display
        "duplicate_count": duplicate_count,
        "conflicting_duplicate_count": conflicting_duplicate_count,
        "invalid_ohlc_count": invalid_ohlc_count,
        "negative_volume_count": negative_vol_count,
        "non_positive_price_count": non_positive_price_count,
        "timestamp_alignment_valid": is_hourly_aligned and is_monotonic_increasing,
        "coverage_start": (
            coverage_start_dt.isoformat() if not open_times.empty else None
        ),
        "coverage_end": coverage_end_dt.isoformat() if not open_times.empty else None,
        "cross_market_aligned": cross_market_aligned,
        "issues": issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
