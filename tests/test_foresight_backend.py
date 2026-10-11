"""Comprehensive test suite for Foresight data engine and validation."""
import pytest
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from backend.app.config import SPLITS, DEFAULT_START_DATE, DEFAULT_END_DATE
from backend.app.splits import get_split_for_timestamp, assign_splits_to_dataframe, calculate_split_summaries
from backend.app.processor import normalize_timestamp_to_utc
from backend.app.validator import validate_dataset
from backend.app.downloader import calculate_sha256

def test_timestamp_units_normalization():
    """Verify both ms (< 2025) and us (>= 2025) Binance timestamps normalize accurately to UTC."""
    # 2022-10-01 00:00:00 UTC in milliseconds (13 digits)
    ms_val = 1664582400000
    dt_ms = normalize_timestamp_to_utc(ms_val)
    assert dt_ms.year == 2022
    assert dt_ms.month == 10
    assert dt_ms.day == 1
    assert dt_ms.hour == 0
    assert dt_ms.minute == 0
    assert dt_ms.second == 0
    assert dt_ms.tzinfo == timezone.utc

    # 2025-01-01 00:00:00 UTC in microseconds (16 digits)
    us_val = 1735689600000000
    dt_us = normalize_timestamp_to_utc(us_val)
    assert dt_us.year == 2025
    assert dt_us.month == 1
    assert dt_us.day == 1
    assert dt_us.hour == 0
    assert dt_us.minute == 0
    assert dt_us.second == 0
    assert dt_us.tzinfo == timezone.utc

def test_split_boundaries_exact_half_open():
    """Verify half-open chronological interval boundaries."""
    # Training: [2022-10-01 00:00:00, 2025-10-01 00:00:00)
    assert get_split_for_timestamp(datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc)) == "training"
    assert get_split_for_timestamp(datetime(2025, 9, 30, 23, 0, 0, tzinfo=timezone.utc)) == "training"
    
    # Boundary at 2025-10-01 00:00:00 belongs to validation, NOT training!
    assert get_split_for_timestamp(datetime(2025, 10, 1, 0, 0, 0, tzinfo=timezone.utc)) == "validation"
    assert get_split_for_timestamp(datetime(2026, 5, 31, 23, 0, 0, tzinfo=timezone.utc)) == "validation"
    
    # Boundary at 2026-06-01 00:00:00 belongs to final_test, NOT validation!
    assert get_split_for_timestamp(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)) == "final_test"
    assert get_split_for_timestamp(datetime(2026, 9, 30, 23, 0, 0, tzinfo=timezone.utc)) == "final_test"
    
    # Boundary at 2026-10-01 00:00:00 is out of bounds
    assert get_split_for_timestamp(datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)) == "out_of_bounds"

def test_missing_hours_detection():
    """Verify that gaps in hourly sequence are detected and reported without synthetic filling."""
    # Create 3-hour series with hour 1 missing
    times = [
        datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2022, 10, 1, 2, 0, 0, tzinfo=timezone.utc).isoformat(),
    ]
    df = pd.DataFrame({
        "open_time": times,
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [99.0, 101.0],
        "close": [102.0, 104.0],
        "volume": [10.0, 12.0],
        "quote_volume": [1000.0, 1200.0],
        "trade_count": [50, 60],
        "taker_buy_base_volume": [5.0, 6.0],
        "taker_buy_quote_volume": [500.0, 600.0]
    })
    
    report = validate_dataset(df, "BTCUSDT")
    assert report["missing_hours_count"] > 0
    assert report["is_verified"] is False
    assert any(i["category"] == "Coverage Gaps" for i in report["issues"])

def test_conflicting_duplicates_detection():
    """Verify that duplicate timestamps with conflicting prices are flagged."""
    times = [
        datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
    ]
    df = pd.DataFrame({
        "open_time": times,
        "open": [100.0, 105.0], # Conflicting price!
        "high": [110.0, 115.0],
        "low": [95.0, 100.0],
        "close": [105.0, 110.0],
        "volume": [10.0, 10.0],
        "quote_volume": [1000.0, 1000.0],
        "trade_count": [50, 50],
        "taker_buy_base_volume": [5.0, 5.0],
        "taker_buy_quote_volume": [500.0, 500.0]
    })
    
    report = validate_dataset(df, "BTCUSDT")
    assert report["duplicate_count"] == 2
    assert report["conflicting_duplicate_count"] == 1
    assert report["is_verified"] is False

def test_invalid_ohlc_relationships():
    """Verify that High < Low, High < Open, or Low > Close are flagged as errors."""
    times = [
        datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
    ]
    df = pd.DataFrame({
        "open_time": times,
        "open": [100.0],
        "high": [90.0], # High is lower than open!
        "low": [85.0],
        "close": [88.0],
        "volume": [10.0],
        "quote_volume": [1000.0],
        "trade_count": [50],
        "taker_buy_base_volume": [5.0],
        "taker_buy_quote_volume": [500.0]
    })
    
    report = validate_dataset(df, "BTCUSDT")
    assert report["invalid_ohlc_count"] == 1
    assert report["is_verified"] is False

def test_negative_volume_and_non_positive_price():
    """Verify that negative volumes or prices <= 0 are caught."""
    times = [
        datetime(2022, 10, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
    ]
    df = pd.DataFrame({
        "open_time": times,
        "open": [0.0], # Invalid zero price!
        "high": [10.0],
        "low": [0.0],
        "close": [5.0],
        "volume": [-5.0], # Negative volume!
        "quote_volume": [50.0],
        "trade_count": [10],
        "taker_buy_base_volume": [2.0],
        "taker_buy_quote_volume": [20.0]
    })
    
    report = validate_dataset(df, "BTCUSDT")
    assert report["non_positive_price_count"] >= 1
    assert report["negative_volume_count"] >= 1
    assert report["is_verified"] is False

def test_split_summaries_calculation():
    """Verify that split summary percentages and counts compute properly."""
    df = pd.DataFrame({
        "open_time": [
            "2022-10-01T00:00:00+00:00",
            "2023-01-01T00:00:00+00:00",
            "2025-10-01T00:00:00+00:00",
            "2026-06-01T00:00:00+00:00"
        ]
    })
    df = assign_splits_to_dataframe(df)
    summaries = calculate_split_summaries(df)
    
    assert summaries["training"]["actual_count"] == 2
    assert summaries["validation"]["actual_count"] == 1
    assert summaries["final_test"]["actual_count"] == 1
    assert summaries["training"]["duration_months"] == 36 # Corrected from 26
    assert summaries["validation"]["duration_months"] == 8
    assert summaries["final_test"]["duration_months"] == 4
