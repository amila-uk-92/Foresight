"""Causal, contract, maturity and persistence acceptance checks (no UI snapshots)."""

import copy
import json
import sqlite3
import threading
import time
from datetime import timezone
import numpy as np
import pandas as pd
import pytest
from backend.app.storage import Store
from backend.app.jobs import Jobs, Cancelled
from backend.app.forecasting.data import MarketData
from backend.app.forecasting.specialist import train, predict, stamp
from backend.app.forecasting.contracts import coordinate, validate
from backend.app.forecasting.evaluator import evaluate, interval_score, aggregate
from backend.app.forecasting.service import Engine
from backend.app.processor import DatasetProcessor
from backend.app.validator import validate_dataset


def test_future_mutation_does_not_change_origin_features_or_targets(data):
    origin = stamp("2026-06-01T00:00:00+00:00")
    frame = data.frame.copy()
    mask = frame.open_time_unix >= origin
    frame.loc[mask, ["open", "high", "low", "close", "volume", "quote_volume"]] *= 7
    changed = MarketData(frame, "changed")
    i, x = data.input(origin, 30)
    j, z = changed.input(origin, 30)
    np.testing.assert_array_equal(x, z)
    a = data.examples(30, stamp("2025-10-01T00:00:00+00:00"), origin)
    b = changed.examples(30, stamp("2025-10-01T00:00:00+00:00"), origin)
    np.testing.assert_array_equal(a[1], b[1])
    np.testing.assert_array_equal(a[2], b[2])


def test_final_test_mutation_cannot_change_model_selection(
    data, model, store, tmp_path, monkeypatch
):
    from backend.app.forecasting import specialist

    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    frame = data.frame.copy()
    mask = frame.open_time_unix >= stamp("2026-06-01T00:00:00+00:00")
    frame.loc[mask, ["open", "high", "low", "close"]] *= 4
    changed = train(
        MarketData(frame, "changed"), store, lookbacks=(30,), alphas=(10.0,)
    )
    assert changed["parameters"] == model["parameters"]
    assert changed["residuals"] == model["residuals"]
    assert changed["selection_mae_usdt"] == model["selection_mae_usdt"]
    assert stamp(model["fitting_latest_target"]) <= stamp(
        model["fitting_period"]["end_exclusive"]
    )
    assert stamp(model["calibration_latest_target"]) <= stamp(model["training_cutoff"])


def test_exact_completed_candle_and_seven_targets(data, model):
    origin = stamp("2026-06-01T00:00:00+00:00")
    f = predict(data, model, origin, "case")
    assert f["origin_price"] == data.close[data.indices[int(origin)]]
    assert stamp(f["latest_input_close"]) < origin
    assert [p["horizon_hours"] for p in f["points"]] == list(range(24, 169, 24))
    assert sum(f["probabilities"].values()) == pytest.approx(1)
    assert stamp(f["baseline"]["latest_target"]) <= origin
    assert (
        f["input_summary"]["candle_count"]
        == model["configuration"]["lookback_days"] * 24 + 1
    )
    with pytest.raises(ValueError):
        predict(data, model, stamp("2025-06-01T00:00:00+00:00"), "past")


@pytest.mark.parametrize(
    "change",
    [
        lambda f: f.update(latest_input_availability="2027-01-01T00:00:00+00:00"),
        lambda f: f["points"][0].update(lower=float("inf")),
        lambda f: f["points"][0].update(horizon_hours=25),
        lambda f: f["probabilities"].update(positive=2),
        lambda f: f.update(symbol="ETHUSDT"),
        lambda f: f["points"][0].update(upper=1),
    ],
)
def test_coordinator_rejects_invalid_contract(data, model, change):
    f = predict(data, model, stamp("2026-06-01T00:00:00+00:00"), "invalid")
    change(f)
    with pytest.raises(ValueError):
        coordinate(f)


def test_distinct_passthrough_idempotent_immutable_and_restart(data, model, store):
    f = predict(data, model, stamp("2026-06-01T00:00:00+00:00"), "immutable")
    c = coordinate(f)
    assert (
        c["id"] != f["id"]
        and c["points"] == f["points"]
        and c["probabilities"] == f["probabilities"]
    )
    assert c["weights"] == {"price-volume": 1.0}
    store.publish(f, c)
    store.publish(f, c)
    assert len(store.list("forecasts")) == 2
    reloaded = Store(store.path)
    assert reloaded.get("forecasts", c["id"]) == c
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as db:
            db.execute("UPDATE forecasts SET origin=? WHERE id=?", ("changed", c["id"]))
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as db:
            db.execute("DELETE FROM forecasts")


def test_maturity_partial_end_of_data_and_missing_exact_target(data, model):
    origin = stamp("2026-06-01T00:00:00+00:00")
    f = predict(data, model, origin, "maturity")
    assert evaluate(data, f, origin)["state"] == "pending"
    e = evaluate(data, f, origin + 86400)
    assert e["scored_count"] == 1 and e["points"][1]["state"] == "pending"
    i = data.indices[int(origin + 86400)]
    missing = MarketData(data.frame.drop(index=i), data.version)
    e = evaluate(missing, f, origin + 7 * 86400)
    assert e["points"][0]["state"] == "unscorable" and e["scored_count"] == 6
    end = predict(data, model, int(data.times[-1]), "end")
    assert evaluate(data, end, int(data.times[-1]))["scored_count"] == 0


def test_scores_against_hand_calculation():
    assert interval_score(9, 10, 12) == 12
    assert interval_score(13, 10, 12) == 12
    assert interval_score(11, 10, 12) == 2
    from backend.app.forecasting.evaluator import score_point

    p = score_point(110, 100, {"median": 105, "lower": 90, "upper": 108})
    assert p["absolute_price_error"] == 5
    assert p["absolute_return_error_percentage_points"] == 5
    assert p["interval_score"] == 38
    assert p["interval_coverage"] is False


def test_evaluation_does_not_modify_forecast_and_rewind_keeps_outcomes(
    data, model, store
):
    f = predict(data, model, stamp("2026-06-01T00:00:00+00:00"), "score")
    c = coordinate(f)
    store.publish(f, c)
    origin = stamp(c["origin"])
    before = store.get("forecasts", c["id"])
    store.evaluation(c["id"], evaluate(data, c, origin + 7 * 86400))
    store.evaluation(c["id"], evaluate(data, c, origin))
    assert store.evaluation(c["id"])["scored_count"] == 7
    assert store.get("forecasts", c["id"]) == before


def test_gap_window_is_excluded(data):
    gap = stamp("2023-03-24T14:00:00+00:00")
    with pytest.raises(ValueError):
        data.input(gap, 30)
    with pytest.raises(ValueError):
        data.input(gap + 86400, 30)


def test_nonfinite_volume_fractional_trades_and_volume_conflicts(data):
    frame = data.frame.iloc[:2].copy()
    frame.loc[0, "quote_volume"] = float("inf")
    assert validate_dataset(frame, "BTCUSDT")["negative_volume_count"] == 1
    frame = data.frame.iloc[:2].copy()
    frame["trade_count"] = frame.trade_count.astype(float)
    frame.loc[0, "trade_count"] = 1.5
    assert validate_dataset(frame, "BTCUSDT")["negative_volume_count"] == 1
    frame = pd.concat([data.frame.iloc[:1], data.frame.iloc[:1]], ignore_index=True)
    frame.loc[1, "volume"] += 1
    assert validate_dataset(frame, "BTCUSDT")["conflicting_duplicate_count"] == 1


def test_job_conflict_cooperative_cancel_and_restart_recovery(store):
    runner = Jobs(store)
    entered = threading.Event()
    release = threading.Event()

    def work(id):
        entered.set()
        release.wait(3)
        runner.check(id)

    first = runner.start("forecasting", work)
    assert entered.wait(2)
    with pytest.raises(ValueError):
        runner.start("import", lambda id: None)
    runner.cancel(first["job_id"])
    release.set()
    for _ in range(100):
        if runner.get(first["job_id"])["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert runner.get(first["job_id"])["status"] == "cancelled"
    runner.update(first["job_id"], status="running")
    Jobs(store).recover()
    assert Store(store.path).path.exists()
    assert runner.get(first["job_id"])["status"] == "failed"
    assert "restarted" in runner.get(first["job_id"])["error"]
    runner.pool.shutdown()


def test_model_rollback_persists_without_changing_forecasts(model, store):
    store.put("models", model, immutable=True)
    Engine(store).rollback(model["id"])
    assert Store(store.path).setting("selected_model") == model["id"]
    assert store.list("decisions")[0]["kind"] == "rollback"


def test_adaptive_fit_uses_only_matured_earlier_cases(
    data, store, tmp_path, monkeypatch
):
    from backend.app.forecasting import specialist

    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    cutoff = stamp("2026-06-16T00:00:00+00:00")
    candidate = train(data, store, cutoff=cutoff, lookbacks=(30,), alphas=(10.0,))
    assert stamp(candidate["calibration_latest_target"]) <= cutoff
    assert stamp(candidate["fitting_latest_target"]) <= stamp(
        candidate["selection_period"]["start"]
    )
    assert candidate["development"] is True


def test_promotion_applies_all_predeclared_gates(data, model, store, monkeypatch):
    from backend.app.forecasting import service

    candidate = copy.deepcopy(model)
    candidate["id"] = "candidate-under-test"
    monkeypatch.setattr(service, "train", lambda *args, **kwargs: candidate)

    # Verify each recorded gate, including retained incumbent when uncertainty worsens.
    def good_loss(m, cases):
        return {
            "sample_count": len(cases[0]),
            "mae_usdt": 2.0 if m["id"] == model["id"] else 1.0,
            "interval_score_usdt": 10.0 if m["id"] == model["id"] else 9.0,
            "coverage": 0.8,
        }

    monkeypatch.setattr(service, "loss", good_loss)
    clock = stamp("2026-09-30T00:00:00+00:00")
    assert (
        Engine(store).candidate(
            data, model, clock, "policy", lambda: None, lambda *args: None
        )["id"]
        == candidate["id"]
    )
    decision = store.list("decisions")[0]
    assert decision["promoted"] and decision["sample_count"] >= 30
    assert stamp(decision["comparison_end"]) == clock
    assert stamp(decision["comparison_start"]) == clock - 45 * 86400

    def bad_loss(m, cases):
        values = good_loss(m, cases)
        if m["id"] != model["id"]:
            values["coverage"] = 0.5
        return values

    monkeypatch.setattr(service, "loss", bad_loss)
    assert (
        Engine(store).candidate(
            data, model, clock, "reject", lambda: None, lambda *args: None
        )["id"]
        == model["id"]
    )
    assert store.list("decisions")[0]["promoted"] is False


def test_unverified_archive_cannot_replace_published_bundle(tmp_path, monkeypatch):
    from backend.app import processor
    import hashlib
    import zipfile

    raw = tmp_path / "raw"
    manifests = tmp_path / "manifests"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    for p in (raw, manifests, processed, reports):
        p.mkdir()
    monkeypatch.setattr(processor, "RAW_DATA_DIR", raw)
    monkeypatch.setattr(processor, "MANIFESTS_DIR", manifests)
    monkeypatch.setattr(processor, "PROCESSED_DATA_DIR", processed)
    monkeypatch.setattr(processor, "REPORTS_DIR", reports)
    (raw / "BTCUSDT").mkdir()
    archive = raw / "BTCUSDT" / "BTCUSDT-1h-2022-10.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("bad.csv", "broken")
    (manifests / "BTCUSDT_manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "filename": archive.name,
                        "checksum_verified": False,
                        "expected_sha256": hashlib.sha256(
                            archive.read_bytes()
                        ).hexdigest(),
                    }
                ]
            }
        )
    )
    pointer = processed / "BTCUSDT_current.json"
    pointer.write_text('{"bundle":"previous-version"}')
    before = pointer.read_bytes()
    with pytest.raises(ValueError, match="Unverified"):
        DatasetProcessor("BTCUSDT").process_and_save()
    assert pointer.read_bytes() == before


def test_missing_checksum_never_reuses_an_unverified_file(tmp_path):
    import asyncio
    from backend.app.downloader import ArchiveDownloader

    path = tmp_path / "archive.zip"
    path.write_bytes(b"not-a-verified-archive")
    result = asyncio.run(
        ArchiveDownloader("BTCUSDT").download_file(
            None, "https://example.invalid", path, None
        )
    )
    assert result["status"] == "failed"
    assert path.read_bytes() == b"not-a-verified-archive"


def test_atomic_dataset_bundle_matches_report_and_manifest(data):
    processor = DatasetProcessor("BTCUSDT")
    bundle = processor.current_bundle()
    if bundle is None:
        pytest.skip("Explicit bundle import has not been run in this checkout")
    saved = pd.read_parquet(bundle / "candles.parquet")
    report = json.loads((bundle / "quality.json").read_text())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert len(saved) == report["total_actual"] == 35063
    assert manifest["verified_files"] == 48
    assert report["is_verified"] is False and report["missing_hours_count"] == 1


def test_forecasting_http_workflow_uses_persistent_services(
    data, model, store, monkeypatch
):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.api import forecasts

    runner = Jobs(store)
    store.put("models", model, immutable=True)
    store.setting("selected_model", model["id"])
    monkeypatch.setattr(forecasts, "engine", Engine(store))
    monkeypatch.setattr(forecasts, "jobs", runner)
    client = TestClient(app)
    result = client.post(
        "/api/forecasting/predict", json={"origin": "2026-06-01T00:00:00+00:00"}
    )
    assert result.status_code == 200
    id = result.json()["job_id"]
    for _ in range(100):
        job = runner.get(id)
        if job["status"] in ("complete", "failed"):
            break
        time.sleep(0.02)
    assert job["status"] == "complete", job.get("error")
    forecast_id = job["result"]["forecast_id"]
    detail = client.get("/api/forecasting/forecasts/" + forecast_id)
    assert detail.status_code == 200
    assert detail.json()["forecast"]["model_version"] == model["id"]
    assert detail.json()["evaluation"]["scored_count"] == 0
    inputs = client.get(
        "/api/forecasting/forecasts/" + forecast_id + "/inputs?page=2&page_size=25"
    )
    assert inputs.status_code == 200 and len(inputs.json()["rows"]) == 25
    origin = stamp("2026-06-01T00:00:00+00:00")
    assert all(
        pd.Timestamp(r["close_time"]).timestamp() < origin
        for r in inputs.json()["rows"]
    )
    evaluate = client.post(
        "/api/forecasting/forecasts/" + forecast_id + "/evaluate",
        json={"clock": "2026-06-08T00:00:00+00:00"},
    )
    assert evaluate.status_code == 200 and evaluate.json()["scored_count"] == 7
    invalid = client.post(
        "/api/forecasting/forecasts/" + forecast_id + "/evaluate",
        json={"clock": "2027-01-01T00:00:00+00:00"},
    )
    assert invalid.status_code == 400
    state = client.get("/api/forecasting/state").json()
    assert (
        state["selected_model"] == model["id"]
        and state["forecasts"][0]["id"] == forecast_id
    )
    assert "parameters" not in state["models"][0]
    runner.pool.shutdown()


def test_publisher_rejects_modified_coordinated_predictions(data, model, store):
    from backend.app.forecasting.publisher import Publisher

    original = predict(data, model, stamp("2026-06-01T00:00:00+00:00"), "publisher")
    coordinated = coordinate(original)
    coordinated["points"][0]["median"] += 1
    with pytest.raises(ValueError, match="pass-through"):
        Publisher(store).publish(original, coordinated)
    assert store.list("forecasts") == []
    original["status"] = "unavailable"
    with pytest.raises(ValueError, match="Unavailable"):
        coordinate(original)
