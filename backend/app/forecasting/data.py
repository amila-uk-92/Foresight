"""Market data for forecasting: verified snapshots, causal features and examples.

Market-specific rules come from the MarketSpec: its calendar decides daily origins
and horizon targets, its feature set computes inputs. All rolling calculations
look backwards only.
"""

import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
from backend.app.config import DATA_DIR, MANIFESTS_DIR, RAW_DATA_DIR
from backend.app.downloader import calculate_sha256
from backend.app.markets import get_market, primary_market, source_for
from backend.app.processor import DatasetProcessor
from backend.app.storage import atomic_json
from backend.app.validator import validate_dataset
from backend.app.forecasting.features import (
    CRYPTO_PRICE_VOLUME,
    CRYPTO_PRICE_VOLUME_DEFINITIONS,
    get_feature_set,
)

# The primary market's feature set, kept under the original names for callers and
# stored artifacts. Other markets read theirs from MarketData.feature_set.
FEATURES = CRYPTO_PRICE_VOLUME
FEATURE_DEFINITIONS = CRYPTO_PRICE_VOLUME_DEFINITIONS


class MarketData:
    def __init__(self, frame, version, quality=None, end=None, market=None):
        self.market = market or primary_market()
        self.calendar = self.market.calendar
        self.feature_set = get_feature_set(self.market.feature_set)
        self.feature_names = self.feature_set.names
        self.horizons = self.market.horizon_days
        missing = self.feature_set.missing_columns(frame)
        if missing:
            raise ValueError(
                f"{self.market.symbol} data lacks columns for feature set "
                f"'{self.feature_set.name}': {', '.join(missing)}"
            )
        self.frame = frame.sort_values("open_time_unix").reset_index(drop=True).copy()
        self.version = version
        self.end = int(end or self.market.coverage_end.timestamp())
        self.quality = quality or {}
        interval = self.calendar.interval_seconds
        # A bar's time is when it completes: open + interval.
        self.times = self.frame["open_time_unix"].to_numpy(dtype=np.int64) + interval
        # pandas may preserve microsecond units. Use explicit timestamp conversion.
        self.available = np.array(
            [pd.Timestamp(x).timestamp() for x in self.frame["close_time"]]
        )
        if not np.all(
            (self.available < self.times) & (self.available >= self.times - interval)
        ):
            raise ValueError("Candle close timestamps violate hourly availability")
        self.close = self.frame["close"].to_numpy(dtype=float)
        self.indices = {int(t): i for i, t in enumerate(self.times)}
        self._features = {}

    @classmethod
    def load(cls, version=None, symbol=None):
        market = get_market(symbol) if symbol else primary_market()
        root = DATA_DIR / "versions"
        if version:
            path = root / version / f"{market.symbol}.parquet"
            if not path.exists() or calculate_sha256(path) != version:
                raise ValueError("Dataset snapshot missing or modified")
            return cls(
                pd.read_parquet(path),
                version,
                json.loads((path.parent / "quality.json").read_text()),
                market=market,
            )
        proc = DatasetProcessor(market.symbol)
        frame = proc.load_processed()
        if frame is None or frame.empty:
            raise ValueError(f"Import {market.display_name} before training")
        quality = validate_dataset(frame, market.symbol, market=market)
        if (
            any(
                quality[k]
                for k in (
                    "duplicate_count",
                    "invalid_ohlc_count",
                    "non_positive_price_count",
                    "negative_volume_count",
                )
            )
            or not quality["timestamp_alignment_valid"]
        ):
            raise ValueError(
                f"Invalid {market.base_asset} dataset. Correct the quality issues before training."
            )
        manifest_path = MANIFESTS_DIR / f"{market.symbol}_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        )
        entries = {x["filename"]: x for x in manifest.get("files", [])}
        for filename in source_for(market).archive_names(market):
            entry = entries.get(filename, {})
            path = RAW_DATA_DIR / market.symbol / filename
            if (
                not entry.get("checksum_verified")
                or not path.exists()
                or calculate_sha256(path) != entry.get("expected_sha256")
            ):
                raise ValueError(
                    f"Archive integrity unavailable: {filename}. Re-import to verify."
                )
        # Immutable snapshot for models and exact, reproducible later evaluation.
        path = proc.current_parquet_path()
        version = calculate_sha256(path)
        destination = root / version
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"{market.symbol}.parquet"
        if not target.exists():
            temp = target.with_suffix(".tmp")
            shutil.copyfile(path, temp)
            temp.replace(target)
        atomic_json(destination / "quality.json", quality)
        atomic_json(destination / "manifest.json", manifest)
        return cls(frame, version, quality, market=market)

    def features(self, days):
        if days not in self._features:
            self._features[days] = self.feature_set.compute(self, days)
        return self._features[days]

    def input(self, origin, days):
        i = self.indices.get(int(origin))
        if i is None or self.available[i] > origin:
            raise ValueError("Exact completed origin candle is missing")
        x = self.features(days)[i]
        if not np.isfinite(x).all():
            raise ValueError(
                "Incomplete look-back history; no candles are manufactured"
            )
        return i, x

    def examples(self, days, start, end):
        origins, rows, targets, prices = [], [], [], []
        features = self.features(days)
        calendar, steps = self.calendar, range(1, self.horizons + 1)
        for i, t in enumerate(self.times):
            if (
                not calendar.is_origin(t)
                or t < start
                or calendar.horizon_target(t, self.horizons) > end
                or not np.isfinite(features[i]).all()
            ):
                continue
            idx = [self.indices.get(int(calendar.horizon_target(t, d))) for d in steps]
            if any(j is None for j in idx):
                continue
            origins.append(t)
            rows.append(features[i])
            prices.append(self.close[i])
            targets.append(np.log(self.close[idx] / self.close[i]))
        if not rows:
            return (
                np.empty(0),
                np.empty((0, len(self.feature_names))),
                np.empty((0, self.horizons)),
                np.empty(0),
            )
        return np.array(origins), np.array(rows), np.array(targets), np.array(prices)
