"""Market plug-in seams: registry, calendars, config-driven splits, and a toy market
that runs the whole import -> validate -> train -> forecast -> replay path without
any crypto-specific code. The toy market is test-only; nothing new ships."""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.app import config, markets, processor
from backend.app.markets import ContinuousCalendar, DataSource, MarketSpec
from backend.app.splits import make_splits, assign_splits_to_dataframe
from backend.app.validator import validate_dataset

UTC = timezone.utc


def test_builtin_markets_keep_the_binance_btc_defaults():
    btc = markets.get_market("btcusdt")
    assert markets.primary_market() is btc
    assert markets.symbols() == ["BTCUSDT", "ETHUSDT"]
    assert (btc.base_asset, btc.quote_asset, btc.venue) == ("BTC", "USDT", "Binance Spot")
    assert btc.cross_market == "ETHUSDT" and btc.source == "binance-spot"
    assert btc.splits is config.SPLITS
    assert btc.expected_candles == config.EXPECTED_TOTAL_HOURS == 35064
    assert btc.interval_seconds == 3600 and btc.horizon_days == 7
    assert markets.source_for(btc).archive_names(btc)[0] == "BTCUSDT-1h-2022-10.zip"
    assert len(markets.source_for(btc).archive_names(btc)) == 48
    with pytest.raises(ValueError):
        markets.get_market("XAUUSD")
    assert markets.get_market("XAUUSD", None) is None


def test_continuous_calendar_matches_the_hourly_24_7_rules():
    cal = ContinuousCalendar(3600)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 3, tzinfo=UTC)
    grid = cal.expected_open_times(start, end)
    assert len(grid) == cal.expected_count(start, end) == 48
    times = pd.Series(pd.to_datetime(["2024-01-01T01:00Z", "2024-01-01T01:30Z"], utc=True))
    assert cal.misaligned(times).tolist() == [False, True]
    origin = int(start.timestamp())
    assert cal.is_origin(origin) and not cal.is_origin(origin + 3600)
    assert cal.origins(origin + 1, origin + 3 * 86400) == [origin + 86400, origin + 2 * 86400]
    assert [cal.horizon_target(origin, d) - origin for d in (1, 7)] == [86400, 7 * 86400]
    assert cal.lookback_bars(30) == 721
    with pytest.raises(ValueError):
        ContinuousCalendar(7 * 3600)


def test_split_table_is_built_from_boundaries_and_the_calendar():
    s = config.SPLITS
    built = make_splits(
        (s["training"]["start"], s["training"]["end"], s["validation"]["end"], s["final_test"]["end"]),
        ContinuousCalendar(3600),
    )
    for key in s:
        for field in ("start", "end", "expected_hours", "duration_months", "date_label", "label", "color"):
            assert built[key][field] == s[key][field]
    with pytest.raises(ValueError):
        make_splits((s["training"]["end"], s["training"]["start"], s["validation"]["end"], s["final_test"]["end"]), ContinuousCalendar())


# ---- A toy weekday-only market, plugged in through the public seams ------------


class WeekdayCalendar(ContinuousCalendar):
    """Hourly bars Monday to Friday only; horizons count trading days."""

    kind = "weekday-test"

    def expected_open_times(self, start, end):
        grid = super().expected_open_times(start, end)
        return grid[grid.dayofweek < 5]

    def expected_count(self, start, end):
        return len(self.expected_open_times(start, end))

    def is_origin(self, t):
        # A completed bar at 00:00 closes the previous trading day (Tue..Sat 00:00).
        return t % 86400 == 0 and pd.Timestamp(t, unit="s").dayofweek in (1, 2, 3, 4, 5)

    def origins(self, start, end):
        return [t for t in super().origins(start, end) if self.is_origin(t)]

    def horizon_target(self, origin, step):
        t = origin
        for _ in range(step):
            t += 86400
            while not self.is_origin(t):
                t += 86400
        return t


def synthetic_frame(market):
    grid = market.calendar.expected_open_times(market.coverage_start, market.coverage_end)
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(grid))))
    opened = np.r_[close[0], close[:-1]]
    ms = (grid.as_unit("ms").asi8).astype("int64")
    return pd.DataFrame(
        {
            "raw_open_time": ms,
            "open": opened,
            "high": np.maximum(opened, close) * 1.001,
            "low": np.minimum(opened, close) * 0.999,
            "close": close,
            "volume": rng.uniform(1e5, 2e5, len(grid)),
            "raw_close_time": ms + 3600 * 1000 - 1,
            "month": grid.strftime("%Y-%m"),
        }
    )


class ToySource(DataSource):
    """Writes deterministic monthly CSVs instead of downloading anything."""

    key = "toy-source"
    label = "Toy exchange"

    def archive_names(self, market):
        months = pd.period_range(market.coverage_start.replace(tzinfo=None), market.coverage_end.replace(tzinfo=None) - timedelta(seconds=1), freq="M")
        return [f"{market.symbol}-{m}.csv" for m in months.astype(str)]

    def downloader(self, market, **options):
        source = self

        class Writer:
            def request_cancellation(self):
                pass

            async def download_all(self, progress_callback=None):
                raw = processor.RAW_DATA_DIR / market.symbol
                raw.mkdir(parents=True, exist_ok=True)
                frame = synthetic_frame(market)
                files = []
                for name in source.archive_names(market):
                    month = name[len(market.symbol) + 1 : -4]
                    part = frame[frame.month == month].drop(columns="month")
                    path = raw / name
                    part.to_csv(path, index=False)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    files.append({"filename": name, "checksum_verified": True, "expected_sha256": digest})
                manifest = {"symbol": market.symbol, "files": files, "verified_files": len(files)}
                (processor.MANIFESTS_DIR / f"{market.symbol}_manifest.json").write_text(json.dumps(manifest))
                return {"total": len(files), "verified": len(files)}

        return Writer()

    def parse(self, path, market):
        frame = pd.read_csv(path)
        frame["source_file"] = path.name
        return frame


def close_only_features(data, days):
    close = pd.Series(data.close)
    log = np.log(close)
    ret = log.diff()
    bars = days * 24
    return np.column_stack([log.diff(24), ret.rolling(24).std(), log.diff(bars), ret.rolling(bars).std()])


@pytest.fixture
def toy(tmp_path, monkeypatch):
    from backend.app.forecasting import data as data_module, specialist, service
    from backend.app.forecasting import features
    from backend.app.forecasting.contracts import register_specialist_market, unregister_specialist_market

    for module in (processor, data_module):
        for name, sub in (("RAW_DATA_DIR", "raw"), ("MANIFESTS_DIR", "manifests")):
            monkeypatch.setattr(module, name, tmp_path / sub)
    for module in (processor, data_module):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(processor, "PROCESSED_DATA_DIR", tmp_path / "processed")
    monkeypatch.setattr(processor, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "REPORTS_DIR", tmp_path / "reports")
    for sub in ("raw", "manifests", "processed", "reports"):
        (tmp_path / sub).mkdir()

    features.register_feature_set(
        features.FeatureSet(
            name="toy-close-only",
            version="1.0",
            names=["return_1d", "volatility_1d", "lookback_return", "lookback_volatility"],
            definitions={
                "return_1d": "Log return over 24 bars",
                "volatility_1d": "Std of bar log returns, 24 bars",
                "lookback_return": "Log return over the look-back window",
                "lookback_volatility": "Std of bar log returns over the look-back window",
            },
            required_columns=["close"],
            compute=close_only_features,
        )
    )
    calendar = WeekdayCalendar(3600)
    bounds = tuple(datetime(*d, tzinfo=UTC) for d in ((2024, 1, 1), (2024, 9, 1), (2025, 1, 1), (2025, 3, 1)))
    market = MarketSpec(
        symbol="TOYX",
        display_name="TOY/USD",
        base_asset="TOY",
        quote_asset="USD",
        asset_class="test",
        venue="Toy exchange",
        source=ToySource.key,
        interval="1h",
        interval_label="1 hour (1h)",
        calendar=calendar,
        coverage_start=bounds[0],
        coverage_end=bounds[-1],
        splits=make_splits(bounds, calendar),
        feature_set="toy-close-only",
        volume_unit="shares",
    )
    markets.register_source(ToySource())
    markets.register_market(market)
    register_specialist_market("price-volume", "TOYX")
    yield market
    unregister_specialist_market("price-volume", "TOYX")
    markets.unregister_market("TOYX")
    features._FEATURE_SETS.pop("toy-close-only", None)


def test_toy_market_imports_and_validates_on_its_own_calendar(toy):
    from backend.app.processor import DatasetProcessor

    source = markets.source_for(toy)
    asyncio.run(source.downloader(toy).download_all())
    result = DatasetProcessor("TOYX").process_and_save()
    report = result["quality_report"]
    assert report["is_verified"], report["issues"]
    assert report["total_actual"] == report["total_expected"] == toy.expected_candles
    frame = DatasetProcessor("TOYX").load_processed()
    assert (pd.to_datetime(frame.open_time).dt.dayofweek < 5).all()
    assert set(frame.split) == {"training", "validation", "final_test"}
    # Dropping a weekday bar is a gap; weekends never are.
    broken = validate_dataset(frame.drop(index=10), "TOYX")
    assert broken["missing_hours_count"] == 1
    # Datasets API and the market listing read the same spec.
    from backend.app.main import app

    client = TestClient(app)
    meta = client.get("/api/datasets/TOYX/metadata").json()
    assert meta["source"] == "Toy exchange" and meta["expected_candles"] == toy.expected_candles
    assert meta["quality"]["is_verified"] is True
    listed = {m["symbol"]: m for m in client.get("/api/markets").json()["markets"]}
    assert listed["TOYX"]["calendar"] == "weekday-test"
    assert listed["TOYX"]["forecasting_enabled"] is True
    assert listed["ETHUSDT"]["forecasting_enabled"] is False
    assert client.get("/api/markets/NOPE").status_code == 404


def test_toy_market_trains_forecasts_and_replays_through_the_shared_engine(toy, tmp_path):
    from backend.app.processor import DatasetProcessor
    from backend.app.storage import Store
    from backend.app.jobs import Jobs
    from backend.app.forecasting.service import Engine
    from backend.app.forecasting.specialist import stamp

    asyncio.run(markets.source_for(toy).downloader(toy).download_all())
    DatasetProcessor("TOYX").process_and_save()
    store = Store(tmp_path / "toy.sqlite3")
    store.setting("selected_model", "btc-model-must-stay-untouched")
    engine = Engine(store, Jobs(store), market="TOYX")
    result = engine.train_backtest({"mode": "frozen", "lookbacks": [30], "alphas": [10.0]})

    run = store.get("runs", result["run_id"])
    assert run["symbol"] == "TOYX" and run["status"] == "complete"
    origins = [stamp(f["origin"]) for f in store.list("forecasts", run["id"])]
    assert origins and all(toy.calendar.is_origin(t) for t in origins)
    f = store.get("forecasts", result["forecast_id"])
    assert (f["symbol"], f["market"], f["quote_currency"]) == ("TOYX", "Toy exchange", "USD")
    origin = stamp(f["origin"])
    targets = [stamp(p["target"]) for p in f["points"]]
    assert targets == [toy.calendar.horizon_target(origin, d) for d in range(1, 8)]
    # A Friday-close origin lands its first horizon on Monday's close (Tue 00:00).
    friday = next(t for t in origins if pd.Timestamp(t, unit="s").dayofweek == 5)
    fri = store.list("forecasts", run["id"])
    fri = next(x for x in fri if stamp(x["origin"]) == friday)
    assert stamp(fri["points"][0]["target"]) - friday == 3 * 86400
    model = store.get("models", result["model_id"])
    assert model["symbol"] == "TOYX" and model["feature_set"] == "toy-close-only"
    assert model["features"] == ["return_1d", "volatility_1d", "lookback_return", "lookback_volatility"]
    # Per-market settings and listings never touch the primary market's state.
    assert store.setting("selected_model") == "btc-model-must-stay-untouched"
    assert engine.setting("selected_model") == result["model_id"]
    assert store.setting("frozen_protocol_v2") is None
    assert engine.setting("frozen_protocol_v2") == run["protocol_id"]
    btc = Engine(store, Jobs(store))
    assert btc.models() == [] and btc.runs() == [] and btc.history()["total"] == 0
    assert engine.history()["total"] == len(origins)
    # Prediction for the latest bar and evaluation reuse the same market.
    prediction = engine.predict()
    assert prediction["symbol"] == "TOYX"


def test_contract_rejects_markets_a_specialist_is_not_enabled_for(data, model):
    from backend.app.forecasting.contracts import validate
    from backend.app.forecasting.specialist import predict, stamp

    f = predict(data, model, stamp("2026-06-01T00:00:00+00:00"), "case")
    for change in (
        dict(symbol="ETHUSDT"),
        dict(symbol="UNLISTED"),
        dict(market="Coinbase"),
        dict(quote_currency="USD"),
    ):
        with pytest.raises(ValueError):
            validate({**f, **change})


def test_feature_set_must_match_the_columns_a_source_provides(data):
    from backend.app.forecasting.data import MarketData

    with pytest.raises(ValueError, match="trade_count"):
        MarketData(data.frame.drop(columns="trade_count"), "x")


def test_model_trained_for_one_market_cannot_forecast_another(data, model):
    from backend.app.forecasting.specialist import predict, stamp

    other = {**model, "symbol": "ETHUSDT"}
    with pytest.raises(ValueError, match="market"):
        predict(data, other, stamp("2026-06-01T00:00:00+00:00"), "case")
