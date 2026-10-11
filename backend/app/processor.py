"""Dataset parsing, timestamp normalization, split assignment, and Parquet persistence.

Source-specific work (which raw files exist, how to read one) is delegated to the
market's DataSource; everything here is shared by every market.
"""

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.config import (
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    REPORTS_DIR,
    MANIFESTS_DIR,
    DATA_DIR,
)
from backend.app.markets import get_market, source_for
from backend.app.splits import assign_splits_to_dataframe
from backend.app.validator import validate_dataset

logger = logging.getLogger(__name__)

# Binance kline columns in monthly CSVs
BINANCE_COLUMNS = [
    "raw_open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "raw_close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]


def normalize_timestamp_to_utc(val: int) -> datetime:
    """Normalize timestamp in ms or us to UTC datetime.

    Binance spot archives prior to Jan 2025 use milliseconds (13 digits).
    Archives from Jan 2025 onward use microseconds (16 digits).
    """
    if val >= 10**14:  # Microseconds (16 digits)
        seconds = val / 1_000_000.0
    elif val >= 10**11:  # Milliseconds (13 digits)
        seconds = val / 1_000.0
    else:  # Seconds (10 digits)
        seconds = float(val)
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def parse_single_archive(zip_path: Path, symbol: str) -> pd.DataFrame:
    """Read and parse CSV records from a single monthly zip archive."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_files = [f for f in zf.namelist() if f.endswith(".csv")]
        if not csv_files:
            raise ValueError("Archive contains no CSV")

        csv_name = csv_files[0]
        with zf.open(csv_name) as f:
            df = pd.read_csv(
                f,
                header=None,
                names=BINANCE_COLUMNS,
                usecols=BINANCE_COLUMNS[:11],  # Skip ignore column
                dtype={
                    "raw_open_time": "int64",
                    "open": "float64",
                    "high": "float64",
                    "low": "float64",
                    "close": "float64",
                    "volume": "float64",
                    "raw_close_time": "int64",
                    "quote_volume": "float64",
                    "trade_count": "int64",
                    "taker_buy_base_volume": "float64",
                    "taker_buy_quote_volume": "float64",
                },
            )

    df["source_file"] = zip_path.name
    return df


class DatasetProcessor:
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        # Unregistered symbols can still be read (the API returns empty data);
        # importing requires a registered market.
        self.market = get_market(self.symbol, None)
        self.raw_dir = RAW_DATA_DIR / self.symbol
        self.parquet_path = PROCESSED_DATA_DIR / f"{self.symbol}.parquet"
        self.report_path = REPORTS_DIR / f"{self.symbol}_quality.json"

    def process_and_save(
        self,
        cross_market_df: Optional[pd.DataFrame] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_check: Callable[[], None] = lambda: None,
    ) -> Dict[str, Any]:
        """Parse all raw archives for the symbol, normalize timestamps, assign splits, validate, and write Parquet."""
        market = self.market
        if market is None:
            raise ValueError(f"Unsupported market '{self.symbol}'")
        source = source_for(market)
        raw_dir = self.raw_dir
        names = source.archive_names(market)
        if not any((raw_dir / name).exists() for name in names):
            raise FileNotFoundError(
                f"No raw archives found for {self.symbol} in {raw_dir}"
            )

        from backend.app.downloader import calculate_sha256
        from backend.app.storage import atomic_json
        import uuid

        manifest_path = MANIFESTS_DIR / f"{self.symbol}_manifest.json"
        if not manifest_path.exists():
            raise ValueError("Source manifest missing; import verified archives first")
        manifest = json.loads(manifest_path.read_text())
        entries = {e["filename"]: e for e in manifest["files"]}
        zip_files = [raw_dir / name for name in names]
        for archive in zip_files:
            cancellation_check()
            entry = entries.get(archive.name, {})
            if (
                not entry.get("checksum_verified")
                or not archive.exists()
                or calculate_sha256(archive) != entry.get("expected_sha256")
            ):
                raise ValueError(f"Unverified or modified archive: {archive.name}")
        total_files = len(zip_files)
        dfs: List[pd.DataFrame] = []

        for idx, zf in enumerate(zip_files, start=1):
            cancellation_check()
            if progress_callback:
                progress_callback(
                    {
                        "symbol": self.symbol,
                        "status": "parsing",
                        "completed_files": idx,
                        "total_files": total_files,
                        "current_file": zf.name,
                        "percent": round(
                            (idx / total_files) * 50, 1
                        ),  # First 50% for parsing
                    }
                )
            try:
                part_df = source.parse(zf, market)
                if not part_df.empty:
                    dfs.append(part_df)
            except Exception as e:
                raise ValueError(f"Error parsing {zf.name}: {e}") from e

        if not dfs:
            raise ValueError(f"Could not parse any valid records for {self.symbol}")

        combined = pd.concat(dfs, ignore_index=True)

        if progress_callback:
            progress_callback(
                {
                    "symbol": self.symbol,
                    "status": "normalizing",
                    "completed_files": total_files,
                    "total_files": total_files,
                    "current_file": "normalizing timestamps",
                    "percent": 60.0,
                }
            )

        # Timestamp normalization
        # Handle ms vs us
        open_dts = combined["raw_open_time"].apply(source.normalize_timestamp)
        close_dts = combined["raw_close_time"].apply(source.normalize_timestamp)

        combined["open_time"] = open_dts.apply(lambda dt: dt.isoformat())
        combined["close_time"] = close_dts.apply(lambda dt: dt.isoformat())
        combined["open_time_unix"] = open_dts.apply(lambda dt: int(dt.timestamp()))
        combined["open_time_ms"] = open_dts.apply(lambda dt: int(dt.timestamp() * 1000))

        # Sort strictly by timestamp
        combined = combined.sort_values(by="open_time_unix").reset_index(drop=True)

        # Filter strictly to the market's half-open coverage [start, end)
        start_ts = int(market.coverage_start.timestamp())
        end_ts = int(market.coverage_end.timestamp())
        combined = combined[
            (combined["open_time_unix"] >= start_ts)
            & (combined["open_time_unix"] < end_ts)
        ].reset_index(drop=True)

        # Assign chronological splits
        combined = assign_splits_to_dataframe(
            combined, timestamp_col="open_time", splits=market.splits
        )

        if progress_callback:
            progress_callback(
                {
                    "symbol": self.symbol,
                    "status": "validating",
                    "completed_files": total_files,
                    "total_files": total_files,
                    "current_file": "quality validation",
                    "percent": 80.0,
                }
            )

        # Run quality validation
        quality_report = validate_dataset(
            combined, self.symbol, cross_market_df=cross_market_df, market=market
        )

        cancellation_check()
        if (
            any(
                quality_report[k]
                for k in (
                    "duplicate_count",
                    "invalid_ohlc_count",
                    "negative_volume_count",
                    "non_positive_price_count",
                )
            )
            or not quality_report["timestamp_alignment_valid"]
        ):
            raise ValueError("Invalid dataset; existing published dataset retained")

        if progress_callback:
            progress_callback(
                {
                    "symbol": self.symbol,
                    "status": "saving",
                    "completed_files": total_files,
                    "total_files": total_files,
                    "current_file": "writing parquet",
                    "percent": 90.0,
                }
            )

        # Save to Parquet with PyArrow
        table = pa.Table.from_pandas(combined, preserve_index=False)
        # Commit an immutable bundle, then one atomic pointer. Readers never mix versions.
        bundle = DATA_DIR / "bundles" / self.symbol / uuid.uuid4().hex
        bundle.mkdir(parents=True)
        pq.write_table(table, bundle / "candles.parquet", compression="snappy")
        atomic_json(bundle / "quality.json", quality_report)
        atomic_json(bundle / "manifest.json", manifest)
        cancellation_check()
        atomic_json(
            PROCESSED_DATA_DIR / f"{self.symbol}_current.json",
            # Relative to data/, so the project folder can be moved or copied.
            {"bundle": str(bundle.relative_to(DATA_DIR))},
        )

        if progress_callback:
            progress_callback(
                {
                    "symbol": self.symbol,
                    "status": "complete",
                    "completed_files": total_files,
                    "total_files": total_files,
                    "current_file": "finished",
                    "percent": 100.0,
                }
            )

        return {
            "symbol": self.symbol,
            "total_rows": len(combined),
            "parquet_path": str(bundle / "candles.parquet"),
            "quality_report": quality_report,
        }

    def load_processed(self) -> Optional[pd.DataFrame]:
        """Load processed Parquet DataFrame if exists."""
        path = self.current_parquet_path()
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def current_bundle(self):
        pointer = PROCESSED_DATA_DIR / f"{self.symbol}_current.json"
        if not pointer.exists():
            return None
        bundle = Path(json.loads(pointer.read_text())["bundle"])
        if not bundle.is_absolute():
            return DATA_DIR / bundle
        if bundle.exists():
            return bundle
        # Older pointers stored an absolute path; recover after the project moved.
        return DATA_DIR / "bundles" / self.symbol / bundle.name

    def current_parquet_path(self):
        bundle = self.current_bundle()
        return bundle / "candles.parquet" if bundle else self.parquet_path

    def load_quality_report(self) -> Optional[Dict[str, Any]]:
        """Load quality report JSON if exists."""
        bundle = self.current_bundle()
        path = bundle / "quality.json" if bundle else self.report_path
        if not path.exists():
            return None
        return json.loads(path.read_text())
