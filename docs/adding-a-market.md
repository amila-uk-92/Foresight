# Adding a new market

Foresight's backend is split into plug-in pieces so the same import, validation,
forecasting, replay and evaluation code can run on markets other than Binance
BTC/USDT. Only Binance Spot BTCUSDT and ETHUSDT are registered today. This guide
says what to write to add something else (a stock, gold, an index, another
exchange).

## The pieces

| Piece | Where | What it decides |
|---|---|---|
| `MarketSpec` | `backend/app/markets/spec.py` | Symbol, display name, base/quote units, asset class, venue label, interval, timezone, coverage, splits, feature set, specialist, horizon count, cross-market partner |
| Calendar | `backend/app/markets/calendar.py` | Which bar timestamps should exist, alignment, daily forecast origins, where horizon *d* lands, look-back bar counts |
| `DataSource` | `backend/app/markets/sources.py` | Which raw files cover the coverage, how to download and verify them, how to parse one file into canonical candles |
| Feature set | `backend/app/forecasting/features.py` | Model inputs, their written definitions, and the candle columns they need |
| Specialist enablement | `backend/app/forecasting/contracts.py` | Which markets a specialist may publish forecasts for |
| Splits | `backend/app/splits.py` (`make_splits`) | Training / validation / final-test boundaries and expected bar counts |

The registry (`backend/app/markets/registry.py`) holds markets and sources;
`backend/app/markets/__init__.py` registers the built-in Binance ones on import.

Everything else (processor, validator, Parquet bundles, dataset snapshots,
training, coordinator contract, publisher, evaluator, replay, history, the
`/api/datasets/*` routes and the CLI) reads these objects instead of hard-coding
BTC, Binance, hourly 24/7 bars or fixed dates.

## Steps

### 1. Write a data source (once per provider)

Subclass `DataSource` in a new module such as `backend/app/markets/<provider>.py`:

- `key` and `label`, e.g. `"stooq-daily"` and `"Stooq"`.
- `archive_names(market)`: the filenames that together cover
  `market.coverage_start` to `market.coverage_end`.
- `downloader(market, **options)`: an object with
  `async download_all(progress_callback)` and `request_cancellation()`. It must
  write each file to `data/raw/<SYMBOL>/` and a manifest at
  `data/manifests/<SYMBOL>_manifest.json` whose `files` entries carry
  `filename`, `checksum_verified` and `expected_sha256`. The processor refuses
  any file that is not in the manifest as verified with a matching SHA-256, so
  if the provider publishes no checksums, decide explicitly how a file becomes
  "verified" (for example, hash on first download and pin it).
- `parse(path, market)`: return a DataFrame with `REQUIRED_COLUMNS`
  (`raw_open_time`, `open`, `high`, `low`, `close`, `volume`, `raw_close_time`),
  any `OPTIONAL_COLUMNS` the provider has, and `source_file`. Epochs may be in
  seconds, milliseconds or microseconds; override `normalize_timestamp` if the
  source uses something else.

`backend/app/markets/binance.py` is the reference implementation, and
`ToySource` in `tests/test_markets.py` is a minimal one that writes CSVs.

### 2. Pick or write a calendar

`ContinuousCalendar(interval_seconds)` fits any 24/7 market. A market with
sessions, weekends or holidays needs its own class with the same methods:
`expected_open_times`, `expected_count`, `misaligned`, `is_origin`, `origins`,
`horizon_target`, `horizon_hours` and `lookback_bars`. `WeekdayCalendar` in
`tests/test_markets.py` shows the idea: bars only on weekdays, origins at each
trading day's close, horizons counted in trading days.

Decide here what "7 days ahead" means for the market (calendar days or trading
days) and at what time the daily origin sits (for US equities, the 16:00 New
York close, which moves between 20:00 and 21:00 UTC with daylight saving).

### 3. Pick or write a feature set

The built-in `crypto-price-volume` set uses quote volume, taker-buy volume and
trade counts, and counts its windows in hourly bars. A stock or gold feed
usually lacks those columns, and `MarketData` refuses a market whose data lacks
a column its feature set needs. Register a new `FeatureSet` with its names,
plain-language definitions (saved into every model artifact), required columns
and a `compute(data, days)` function that only looks backwards and returns NaN
where history is incomplete. Bump `version` whenever the computation changes.

### 4. Describe the market

Build a `MarketSpec`, with splits from `make_splits`, and register it:

```python
from datetime import datetime, timezone
from backend.app.markets import MarketSpec, register_market, register_source
from backend.app.splits import make_splits

UTC = timezone.utc
calendar = MyExchangeCalendar(3600)
bounds = tuple(datetime(*d, tzinfo=UTC) for d in
               ((2019, 1, 1), (2023, 1, 1), (2024, 7, 1), (2025, 7, 1)))
register_source(MyProviderSource())
register_market(MarketSpec(
    symbol="SPY", display_name="SPY", base_asset="SPY", quote_asset="USD",
    asset_class="equity", venue="NYSE Arca", source="my-provider",
    interval="1h", interval_label="1 hour (1h)", calendar=calendar,
    coverage_start=bounds[0], coverage_end=bounds[-1],
    splits=make_splits(bounds, calendar),
    timezone="America/New_York", feature_set="equity-price-volume",
    volume_unit="shares",
))
```

Add the registration next to the Binance one in `backend/app/markets/__init__.py`
so the API and CLI see it at startup. The new market then appears in
`GET /api/markets`, `GET /api/datasets`, `python cli/foresight_cli.py markets`,
and can be imported with `--symbol SPY` or `POST /api/import/start`.

### 5. Enable forecasting

Importing and inspecting a market needs nothing more. To train and forecast it,
enable the specialist for it and use an engine for that market:

```python
from backend.app.forecasting.contracts import register_specialist_market
from backend.app.forecasting.service import Engine

register_specialist_market("price-volume", "SPY")
engine = Engine(market="SPY")
engine.train_backtest({"mode": "frozen", "lookbacks": [30, 90, 180]})
```

Each non-primary market keeps its own `selected_model` and frozen-protocol
settings (stored as `selected_model:SPY`, `frozen_protocol_v2:SPY`), and its
models, runs and history are listed separately from BTC's. Forecasts carry the
market's `symbol`, venue and quote currency, and the coordinator rejects a
forecast for a market its specialist is not enabled for.

### 6. Test it

Copy the toy-market tests in `tests/test_markets.py`: import through the source,
check the quality report is verified against the calendar, train and replay,
and assert that every origin and horizon target falls where the calendar says.
Then run the whole suite (`python -m pytest -q`) to confirm BTC is unchanged.

## What is still BTC-only

- The `/api/forecasting/*` routes and the forecasting CLI commands use the
  primary market's engine. A `market` query parameter (or one engine per
  market) is the next step once a second forecastable market exists.
- The frontend assumes BTC/USDT and ETH/USDT labels.
- The Binance downloader itself (`backend/app/downloader.py`) is Binance-only by
  design; other providers bring their own downloader through their source.
- `/api/import/start` with `import_both` imports the primary market and its
  cross-market partner.

## Timestamped news extensions

News reuses the existing `MarketSpec` and registry; do not create another symbol registry. Configure `extra['news_profile']` with explicit aliases, issuer/entity context, identifiers (for example ISIN), instrument type and news scope. Canonical instrument ID, asset class, venue and quote currency cannot be overridden. Equity keyword relevance requires issuer context; short ticker substrings are not sufficient. A gold ETF, futures contract and spot XAU/USD require separate profiles and real market/provider contracts.

Register provider-specific `NewsSource` implementations using `backend.app.news.sources.register_news_source`; each returns typed `ArticleInput` records, preserves source-version availability evidence and declares content rights. Source format/access belongs in its adapter. Collector and classifier are separate interfaces. The built-in official macro RSS is forward-only; it does not establish a historical Bitcoin archive. Generic JSON/JSONL import accepts up to 2 MB/1,000 records per batch.

Configure timezone/DST/session/holiday rules in the market calendar. News window logic reads this calendar; for exchange calendars with variable UTC close times, supply and verify the corresponding past-session window behavior before activating the instrument. Current tested non-continuous fixture has a fixed UTC close; real NYSE holiday/DST feeds are not implemented.

Shared `NewsService` powers `/api/news` and `cli/news_cli.py`. News content is stored once, while profile-specific extraction and as-of packets carry instrument associations. Adding an instrument should not require shared UI edits. Adequate price data, chronological news coverage and cached classifications are required before numerical news training; missing evidence is not silently replaced with price-only output.
