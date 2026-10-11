"""Data-source plugin interface.

A data source turns a MarketSpec into verified raw files on disk and parses those
files into the canonical candle frame below. Everything after parsing (timestamp
normalisation, splits, validation, Parquet bundles, forecasting) is shared.
"""

from abc import ABC, abstractmethod

# Columns every source must produce from ``parse``. Optional columns may be absent
# when a venue does not publish them; features that need them must not be used.
REQUIRED_COLUMNS = [
    "raw_open_time",  # Integer epoch (s, ms or us) of the bar open
    "open",
    "high",
    "low",
    "close",
    "volume",  # Traded quantity in MarketSpec.volume_unit
    "raw_close_time",  # Integer epoch of the last instant inside the bar
]
OPTIONAL_COLUMNS = [
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]


class DataSource(ABC):
    """One provider of historical bars (an exchange archive, a vendor API, ...)."""

    key = ""
    label = ""

    @abstractmethod
    def archive_names(self, market):
        """Filenames that together cover the market's full configured coverage."""

    @abstractmethod
    def downloader(self, market, **options):
        """Object with ``async download_all(progress_callback)`` and
        ``request_cancellation()`` that writes verified files and a manifest."""

    @abstractmethod
    def parse(self, path, market):
        """Read one raw file into a DataFrame with REQUIRED_COLUMNS (plus any
        OPTIONAL_COLUMNS) and a ``source_file`` column."""

    def normalize_timestamp(self, value):
        """Integer epoch from this source to an aware UTC datetime."""
        from backend.app.processor import normalize_timestamp_to_utc

        return normalize_timestamp_to_utc(value)

    def archive_url_base(self, market):
        return ""
