"""Feature-set registry. A feature set turns completed candles into model inputs.

Each set declares the candle columns it needs, so a market whose source lacks a
column (for example trade counts or taker volume on a stock feed) must use a set
that does not depend on it. All windows look backwards only and end at the
completed origin candle.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureSet:
    name: str
    version: str
    names: List[str]
    definitions: Dict[str, str]
    required_columns: List[str]
    # compute(data, days) -> (rows x len(names)) array; NaN where history is incomplete
    compute: Callable

    def missing_columns(self, frame):
        return [c for c in self.required_columns if c not in frame.columns]


_FEATURE_SETS = {}


def register_feature_set(feature_set):
    if len(feature_set.names) != len(set(feature_set.names)):
        raise ValueError("Duplicate feature names")
    if set(feature_set.definitions) != set(feature_set.names):
        raise ValueError("Every feature needs exactly one definition")
    _FEATURE_SETS[feature_set.name] = feature_set
    return feature_set


def get_feature_set(name):
    if name not in _FEATURE_SETS:
        raise ValueError(f"Unknown feature set '{name}'")
    return _FEATURE_SETS[name]


def feature_sets():
    return list(_FEATURE_SETS.values())


CRYPTO_PRICE_VOLUME = [
    "return_1h",
    "return_24h",
    "return_7d",
    "return_30d",
    "lookback_return",
    "volatility_24h",
    "volatility_7d",
    "lookback_volatility",
    "range_24h",
    "volume_24h_vs_7d",
    "volume_7d_vs_lookback",
    "quote_volume_24h_vs_7d",
    "taker_fraction_24h",
    "log_trades_24h",
    "weekday_sin",
    "weekday_cos",
]

# Saved with every model artifact. Wording kept exactly as published for BTC models.
CRYPTO_PRICE_VOLUME_DEFINITIONS = {
    "return_1h": "Log close return over the last completed hour",
    "return_24h": "Log close return over the last 24 hours",
    "return_7d": "Log close return over the last 168 hours",
    "return_30d": "Log close return over the last 720 hours",
    "lookback_return": "Log close return over the configured look-back window",
    "volatility_24h": "Standard deviation of hourly log returns, last 24 hours",
    "volatility_7d": "Standard deviation of hourly log returns, last 168 hours",
    "lookback_volatility": "Standard deviation of hourly log returns over the look-back window",
    "range_24h": "Mean (high - low) / close over the last 24 hours",
    "volume_24h_vs_7d": "Log ratio of mean BTC base volume, 24 hours vs 168 hours",
    "volume_7d_vs_lookback": "Log ratio of mean BTC base volume, 168 hours vs look-back window",
    "quote_volume_24h_vs_7d": "Log ratio of mean USDT quote volume, 24 hours vs 168 hours",
    "taker_fraction_24h": "Taker-buy BTC volume / BTC volume, last 24 hours",
    "log_trades_24h": "log(1 + mean hourly trade count), last 24 hours",
    "weekday_sin": "sin(2π · UTC weekday of origin / 7)",
    "weekday_cos": "cos(2π · UTC weekday of origin / 7)",
}


def crypto_price_volume(data, days):
    """Hourly 24/7 price-volume features. Windows are counted in hourly bars."""
    f = data.frame
    close = pd.Series(data.close)
    log = np.log(close)
    ret = log.diff()
    hours = days * 24
    volume, quote = f["volume"], f["quote_volume"]
    ratio = lambda a, b: np.log((a + 1e-9) / (b + 1e-9))
    weekday = pd.to_datetime(data.times, unit="s", utc=True).dayofweek.to_numpy()
    cols = [
        ret,
        log.diff(24),
        log.diff(168),
        log.diff(720),
        log.diff(hours),
        ret.rolling(24).std(),
        ret.rolling(168).std(),
        ret.rolling(hours).std(),
        ((f["high"] - f["low"]) / close).rolling(24).mean(),
        ratio(volume.rolling(24).mean(), volume.rolling(168).mean()),
        ratio(volume.rolling(168).mean(), volume.rolling(hours).mean()),
        ratio(quote.rolling(24).mean(), quote.rolling(168).mean()),
        f["taker_buy_base_volume"].rolling(24).sum() / (volume.rolling(24).sum() + 1e-9),
        np.log1p(f["trade_count"].rolling(24).mean()),
        np.sin(2 * np.pi * weekday / 7),
        np.cos(2 * np.pi * weekday / 7),
    ]
    values = np.column_stack(cols)
    # A full lookback and its first return must be observed; never fill a gap.
    contiguous = pd.Series(data.times).diff(hours).to_numpy() == hours * 3600
    values[~contiguous] = np.nan
    return values


register_feature_set(
    FeatureSet(
        name="crypto-price-volume",
        version="1.0",
        names=CRYPTO_PRICE_VOLUME,
        definitions=CRYPTO_PRICE_VOLUME_DEFINITIONS,
        required_columns=[
            "close",
            "high",
            "low",
            "volume",
            "quote_volume",
            "taker_buy_base_volume",
            "trade_count",
        ],
        compute=crypto_price_volume,
    )
)
