"""Binance Spot public monthly kline archives (data.binance.vision)."""

from datetime import timedelta
from backend.app.config import (
    BINANCE_ARCHIVE_BASE,
    CROSS_MARKET_SYMBOL,
    DEFAULT_END_DATE,
    DEFAULT_INTERVAL,
    DEFAULT_SOURCE,
    DEFAULT_START_DATE,
    DEFAULT_TIMEZONE,
    PRIMARY_SYMBOL,
    SPLITS,
)
from backend.app.markets.calendar import ContinuousCalendar
from backend.app.markets.sources import DataSource
from backend.app.markets.spec import MarketSpec


class BinanceSpotSource(DataSource):
    key = "binance-spot"
    label = DEFAULT_SOURCE

    def months(self, market):
        from backend.app.downloader import generate_month_list

        last = market.coverage_end - timedelta(seconds=1)
        return generate_month_list(
            market.coverage_start.year,
            market.coverage_start.month,
            last.year,
            last.month,
        )

    def archive_names(self, market):
        return [
            f"{market.symbol}-{market.interval}-{month}.zip"
            for month in self.months(market)
        ]

    def archive_url_base(self, market):
        return f"{BINANCE_ARCHIVE_BASE}/{market.symbol}/{market.interval}"

    def downloader(self, market, **options):
        from backend.app.downloader import ArchiveDownloader

        return ArchiveDownloader(
            market.symbol,
            interval=market.interval,
            months=self.months(market),
            **options,
        )

    def parse(self, path, market):
        from backend.app.processor import parse_single_archive

        return parse_single_archive(path, market.symbol)


def binance_spot_market(symbol, base, quote, **overrides):
    """A Binance Spot pair on the project's configured coverage and splits."""
    values = dict(
        symbol=symbol,
        display_name=f"{base}/{quote}",
        base_asset=base,
        quote_asset=quote,
        asset_class="crypto",
        venue=DEFAULT_SOURCE,
        source=BinanceSpotSource.key,
        interval=DEFAULT_INTERVAL,
        interval_label="1 hour (1h)",
        calendar=ContinuousCalendar(3600),
        coverage_start=DEFAULT_START_DATE,
        coverage_end=DEFAULT_END_DATE,
        splits=SPLITS,
        timezone=DEFAULT_TIMEZONE,
        volume_unit=base,
        quote_volume_unit=quote,
    )
    values.update(overrides)
    return MarketSpec(**values)


SOURCES = [BinanceSpotSource()]
MARKETS = [
    binance_spot_market(
        PRIMARY_SYMBOL, "BTC", "USDT", is_primary=True, cross_market=CROSS_MARKET_SYMBOL
    ),
    binance_spot_market(CROSS_MARKET_SYMBOL, "ETH", "USDT"),
]
