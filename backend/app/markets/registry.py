"""Lookup tables for markets and data sources.

Built-in markets are registered on import. A new market is added by registering
its DataSource (once per provider) and its MarketSpec; see docs/adding-a-market.md.
"""

_MARKETS = {}
_SOURCES = {}


def register_source(source):
    if not source.key:
        raise ValueError("Data source needs a key")
    _SOURCES[source.key] = source
    return source


def register_market(market):
    if market.source not in _SOURCES:
        raise ValueError(f"Unknown data source '{market.source}' for {market.symbol}")
    if market.symbol != market.symbol.upper():
        raise ValueError("Market symbols are upper case")
    _MARKETS[market.symbol] = market
    return market


def unregister_market(symbol):
    """Remove a market (tests and experiments only)."""
    _MARKETS.pop(symbol.upper(), None)


def get_market(symbol, default=...):
    market = _MARKETS.get(str(symbol).upper())
    if market is None:
        if default is not ...:
            return default
        raise ValueError(f"Unsupported market '{symbol}'")
    return market


def get_source(key):
    if key not in _SOURCES:
        raise ValueError(f"Unknown data source '{key}'")
    return _SOURCES[key]


def source_for(market):
    return get_source(market.source)


def markets():
    """Registered markets, in registration order."""
    return list(_MARKETS.values())


def symbols():
    return [m.symbol for m in markets()]


def primary_market():
    return next((m for m in markets() if m.is_primary), markets()[0])
