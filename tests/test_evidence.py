"""Read-only forecast evidence view: stored records only, truthful missing states."""

import json
import pytest
from fastapi.testclient import TestClient
from backend.app.jobs import Jobs
from backend.app.forecasting.service import Engine
from backend.app.forecasting.specialist import iso, stamp

ORIGIN = stamp("2026-06-01T00:00:00+00:00")


@pytest.fixture
def engine(store):
    runner = Jobs(store)
    yield Engine(store, runner)
    runner.pool.shutdown()


@pytest.fixture
def client(engine, monkeypatch):
    from backend.app.main import app
    from backend.app.api import forecasts

    monkeypatch.setattr(forecasts, "engine", engine)
    monkeypatch.setattr(forecasts, "jobs", engine.jobs)
    return TestClient(app)


def published(engine, data, model, run_id="r-evidence"):
    if not any(m["id"] == model["id"] for m in engine.store.list("models")):
        engine.store.put("models", model, immutable=True)
    return engine.publish(data, model, ORIGIN, run_id, "frozen")


def snapshot(store):
    with store.connection() as db:
        return {
            t: db.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in ("forecasts", "evaluations", "runs", "models", "jobs", "settings")
        }


def test_legacy_forecast_reports_reasoning_not_recorded_and_planned_agents(engine, data, model, client):
    f = published(engine, data, model)
    before = [list(map(tuple, v)) for v in snapshot(engine.store).values()]
    r = client.get(f"/api/forecasting/forecasts/{f['id']}/evidence")
    assert r.status_code == 200
    e = r.json()
    assert e["schema_version"] == "forecast-evidence/1"
    assert e["forecast"]["origin"] == f["origin"]
    assert e["forecast"]["evidence_cutoff"] == f["latest_input_availability"]
    assert [t["target"] for t in e["forecast"]["targets"]] == [p["target"] for p in f["points"]]
    # Numerical data is the stored forecast, unchanged, and kept apart from research evidence.
    assert e["numerical"]["points"] == [
        {k: p[k] for k in ("target", "horizon_hours", "median", "lower", "upper")} for p in f["points"]
    ]
    assert e["numerical"]["coordination"]["weights"] == {"price-volume": 1.0}
    # Nothing is invented for components that do not exist.
    assert e["reasoning"]["state"] == "not_implemented"
    assert e["reasoning"]["forecast_state"] == "not_recorded"
    assert e["reasoning"]["findings"] == [] and e["reasoning"]["summary"] is None
    assert e["reasoning"]["agreement"] is None
    assert e["sources"]["research"]["state"] == "not_recorded"
    states = {a["id"]: a["state"] for a in e["agents"]}
    assert states["price-volume"] == "active"
    assert states["news-macro"] == "experimental"
    assert states["moderator"] == states["bull-researcher"] == "planned"
    assert e["versions"]["prompt_version"]["state"] == "not_implemented"
    assert e["cost_latency"]["inference_cost"]["state"] == "not_recorded"
    assert e["trading"]["state"] == "not_enabled"
    # Market data citations are the real archive files behind the look-back window.
    market = e["sources"]["market_data"]
    assert market["state"] == "recorded"
    assert sum(x["candles_used"] for x in market["records"]) == market["candle_count"] > 0
    assert all(x["source_id"].endswith(".zip") for x in market["records"])
    assert stamp(market["latest_candle_close"]) < ORIGIN
    # Reading evidence writes nothing.
    assert [list(map(tuple, v)) for v in snapshot(engine.store).values()] == before


def test_outcomes_separate_known_pending_and_missing(engine, data, model, client):
    f = published(engine, data, model)
    engine.evaluate_at(f["id"], iso(ORIGIN + 3 * 86400))
    e = client.get(f"/api/forecasting/forecasts/{f['id']}/evidence").json()
    statuses = [p["status"] for p in e["outcomes"]["points"]]
    assert statuses[:3] == ["known"] * 3 and set(statuses[3:]) == {"pending"}
    assert e["outcomes"]["counts"] == {"known": 3, "pending": 4, "missing": 0}
    assert all(p["actual_price"] for p in e["outcomes"]["points"][:3])
    assert all(p["actual_price"] is None for p in e["outcomes"]["points"][3:])


def test_specialist_id_resolves_to_its_published_pair(engine, data, model, client):
    f = published(engine, data, model)
    e = client.get(f"/api/forecasting/forecasts/{f['specialist_forecast_id']}/evidence").json()
    assert e["forecast_id"] == f["id"]
    assert e["specialist_forecast_id"] == f["specialist_forecast_id"]


def test_missing_forecast_and_missing_snapshot(engine, data, model, client):
    assert client.get("/api/forecasting/forecasts/nope/evidence").status_code == 404
    f = published(engine, data, model)
    broken = dict(f, id="broken", dataset_version="0" * 64, specialist_forecast_id="absent")
    with engine.store.connection() as db:
        db.execute(
            "INSERT INTO forecasts VALUES(?,?,?,?,?,?,?)",
            ("broken", "other-run", f["origin"], f["model_version"], "coordinated", f["generated_at"], json.dumps(broken)),
        )
    e = client.get("/api/forecasting/forecasts/broken/evidence").json()
    # The record that should exist but cannot be read is reported, not hidden.
    assert e["sources"]["market_data"]["state"] == "unavailable"
    assert "missing" in e["sources"]["market_data"]["error"]
    assert e["specialist_forecast_id"] is None
    assert e["numerical"]["state"] == "recorded"
