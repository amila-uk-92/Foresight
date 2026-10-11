"""Shared fixtures: real local BTC observations and one controlled model fit."""

import pytest
from backend.app.storage import Store
from backend.app.forecasting.data import MarketData
from backend.app.forecasting.specialist import train


@pytest.fixture(scope="module")
def data():
    # Real local market observations; never write test fixtures into runtime storage.
    return MarketData.load()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


@pytest.fixture(scope="module")
def model(data, tmp_path_factory):
    # A single controlled scientific fit; fast test candidate grid.
    from backend.app.forecasting import specialist

    old = specialist.DATA_DIR
    specialist.DATA_DIR = tmp_path_factory.mktemp("models")
    try:
        return train(
            data,
            Store(specialist.DATA_DIR / "test.sqlite3"),
            lookbacks=(30,),
            alphas=(10.0,),
        )
    finally:
        specialist.DATA_DIR = old
