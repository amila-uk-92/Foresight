"""Market plug-in layer: what is traded, where its data comes from, and its calendar."""

from backend.app.markets.calendar import ContinuousCalendar
from backend.app.markets.registry import (
    get_market,
    get_source,
    markets,
    primary_market,
    register_market,
    register_source,
    source_for,
    symbols,
    unregister_market,
)
from backend.app.markets.sources import DataSource, OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from backend.app.markets.spec import MarketSpec
from backend.app.markets import binance as _binance

for _source in _binance.SOURCES:
    register_source(_source)
for _market in _binance.MARKETS:
    register_market(_market)

__all__ = [
    "ContinuousCalendar",
    "DataSource",
    "MarketSpec",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "get_market",
    "get_source",
    "markets",
    "primary_market",
    "register_market",
    "register_source",
    "source_for",
    "symbols",
    "unregister_market",
]
