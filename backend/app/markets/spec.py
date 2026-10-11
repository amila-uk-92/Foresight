"""What Foresight needs to know about one tradable market."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MarketSpec:
    """Static description of one instrument on one venue.

    Nothing in the pipeline should hard-code a symbol, venue, interval, calendar,
    split dates or feature set; it should read them from here.
    """

    symbol: str  # Storage key and API path segment, e.g. "BTCUSDT"
    display_name: str  # e.g. "BTC/USDT"
    base_asset: str  # What one unit of volume counts, e.g. "BTC"
    quote_asset: str  # Price currency, e.g. "USDT"
    asset_class: str  # "crypto", later "equity", "commodity", ...
    venue: str  # Human label stored on every forecast, e.g. "Binance Spot"
    source: str  # Key of the registered DataSource that imports this market
    interval: str  # Source interval code, e.g. "1h"
    interval_label: str  # e.g. "1 hour (1h)"
    calendar: Any  # A calendar object (see calendar.py)
    coverage_start: datetime  # Half-open UTC coverage [start, end)
    coverage_end: datetime
    splits: Dict[str, Dict[str, Any]]  # training / validation / final_test
    timezone: str = "UTC"
    feature_set: str = "crypto-price-volume"
    specialist: str = "price-volume"
    horizon_days: int = 7
    cross_market: Optional[str] = None  # Symbol whose timestamps must align
    is_primary: bool = False
    volume_unit: str = ""  # Unit of the "volume" column
    quote_volume_unit: str = ""  # Unit of "quote_volume", if the source has it
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def interval_seconds(self):
        return self.calendar.interval_seconds

    @property
    def expected_candles(self):
        return self.calendar.expected_count(self.coverage_start, self.coverage_end)

    @property
    def date_coverage(self):
        return (
            self.coverage_start.strftime("%b %Y")
            + " – "
            + (self.coverage_end - timedelta(seconds=1)).strftime("%b %Y")
        )

    @property
    def total_months(self):
        return (
            (self.coverage_end.year - self.coverage_start.year) * 12
            + self.coverage_end.month
            - self.coverage_start.month
        )

    def summary(self):
        """JSON-safe description for the API and CLI."""
        return {
            "symbol": self.symbol,
            "display_name": self.display_name,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "asset_class": self.asset_class,
            "venue": self.venue,
            "source": self.source,
            "interval": self.interval,
            "interval_seconds": self.interval_seconds,
            "calendar": self.calendar.kind,
            "timezone": self.timezone,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
            "expected_candles": self.expected_candles,
            "splits": {
                k: {"start": v["start"].isoformat(), "end": v["end"].isoformat()}
                for k, v in self.splits.items()
            },
            "feature_set": self.feature_set,
            "specialist": self.specialist,
            "horizon_days": self.horizon_days,
            "cross_market": self.cross_market,
            "is_primary": self.is_primary,
            "volume_unit": self.volume_unit,
            "quote_volume_unit": self.quote_volume_unit,
        }
