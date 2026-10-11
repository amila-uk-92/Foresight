"""Development labelling, agent truthfulness, history and chart/summary agreement."""

import copy
import pytest
from backend.app.config import SPLITS
from backend.app.jobs import Jobs
from backend.app.forecasting import service
from backend.app.forecasting.contracts import coordinate
from backend.app.forecasting.evaluator import aggregate
from backend.app.forecasting.service import (
    AgentError,
    Engine,
    legacy_protocol,
    protocol_fingerprint,
)
from backend.app.forecasting.specialist import iso, predict, stamp

ORIGIN = stamp("2026-06-01T00:00:00+00:00")


@pytest.fixture
def engine(store):
    runner = Jobs(store)
    yield Engine(store, runner)
    runner.pool.shutdown()


def published(engine, data, model, origin=ORIGIN, run_id="case", mode="frozen"):
    if not any(m["id"] == model["id"] for m in engine.store.list("models")):
        engine.store.put("models", model, immutable=True)
    return engine.publish(data, model, origin, run_id, mode)


def test_first_strict_protocol_is_reference_and_any_change_is_development(engine):
    a = protocol_fingerprint((30, 90, 180), (1.0, 10.0, 100.0))
    b = protocol_fingerprint((30, 90, 180), (1.0, 10.0))
    assert a != b
    assert engine.protocol_status(a, "legacy") == (False, None)
    assert engine.protocol_status(a, "legacy") == (False, None)
    development, reason = engine.protocol_status(b, "legacy")
    assert development and "changed after final-test" in reason


def test_policy_and_model_code_changes_alter_the_protocol(monkeypatch):
    before = protocol_fingerprint((30,), (10.0,))
    monkeypatch.setitem(service.PROMOTION_POLICY, "coverage_floor", 0.6)
    assert protocol_fingerprint((30,), (10.0,)) != before
    monkeypatch.undo()
    monkeypatch.setattr(service.inspect, "getsource", lambda obj: "changed " + obj.__name__)
    assert protocol_fingerprint((30,), (10.0,)) != before


def test_legacy_protocol_mismatch_keeps_runs_in_development(engine):
    engine.store.setting("frozen_protocol", legacy_protocol((30,), (1.0,), ["x"]))
    development, reason = engine.protocol_status(
        "new", legacy_protocol((30, 90), (1.0,), ["x"])
    )
    assert development and "configuration differs" in reason
    assert engine.store.setting("frozen_protocol_v2") is None


def test_legacy_protocol_match_migrates_without_relabelling(engine):
    legacy = legacy_protocol((30,), (1.0,), ["x"])
    engine.store.setting("frozen_protocol", legacy)
    assert engine.protocol_status("strict", legacy) == (False, None)
    assert engine.store.setting("frozen_protocol_v2") == "strict"


def test_model_using_final_test_outcomes_is_flagged_on_every_forecast(data, model):
    clean = predict(data, model, ORIGIN, "clean")
    assert not any("final-test" in flag for flag in clean["quality_flags"])
    late = copy.deepcopy(model)
    late["training_cutoff"] = "2026-07-01T00:00:00+00:00"
    flagged = predict(data, late, stamp("2026-07-02T00:00:00+00:00"), "late")
    assert any("final-test-period outcomes" in flag for flag in flagged["quality_flags"])


def test_agent_failures_are_attributed_to_the_failing_agent(
    engine, data, model, monkeypatch
):
    def reject(_):
        raise ValueError("stale input")

    monkeypatch.setattr(service, "coordinate", reject)
    with pytest.raises(AgentError) as rejected:
        published(engine, data, model)
    assert rejected.value.agent == "coordinator"
    with pytest.raises(AgentError) as failed:
        published(engine, data, model, origin=stamp("2025-06-01T00:00:00+00:00"))
    assert failed.value.agent == "specialist"


def test_agent_status_follows_the_selected_forecast(engine, data, model):
    assert engine.agent_status()["specialist"] == "Not trained"
    f = published(engine, data, model)
    status = engine.agent_status(forecast_id=f["id"])
    assert (status["specialist"], status["coordinator"], status["publisher"]) == (
        "Ready",
        "Complete",
        "Saved",
    )
    assert status["evaluator"] == "Pending"
    engine.score(data, f, ORIGIN + 3 * 86400)
    assert engine.agent_status(forecast_id=f["id"])["evaluator"] == "Partial"
    engine.score(data, f, ORIGIN + 7 * 86400)
    assert engine.agent_status(forecast_id=f["id"])["evaluator"] == "Complete"


def test_run_with_rejected_origins_reports_rejected_coordinator(engine):
    run = dict(
        id="r1",
        created_at=iso(ORIGIN),
        mode="frozen",
        status="complete",
        clock=iso(ORIGIN),
        skipped_origins=[
            {"origin": iso(ORIGIN), "agent": "coordinator", "reason": "stale"}
        ],
    )
    engine.store.put("runs", run)
    status = engine.agent_status(run_id="r1")
    assert status["coordinator"] == "Rejected"
    assert status["details"]["coordinator_rejected_origins"] == 1


def test_unrelated_running_job_never_drives_a_forecasts_cards(engine, data, model):
    f = published(engine, data, model)
    with engine.store.connection() as db:
        db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?)",
            (
                "other",
                "forecasting",
                "running",
                iso(ORIGIN),
                '{"job_id":"other","kind":"forecasting","status":"running",'
                '"run_id":"another-run","agents":{"specialist":"Training"}}',
            ),
        )
    assert engine.agent_status(forecast_id=f["id"])["specialist"] == "Ready"


def test_history_detail_and_summary_use_one_stored_day_seven_point(
    engine, data, model
):
    f = published(engine, data, model, run_id="prediction-x", mode="prediction")
    row = engine.history(run_id="prediction-x")["rows"][0]
    day7 = f["points"][6]
    assert row["day7_target"] == day7["target"]
    assert row["day7_median"] == day7["median"]
    assert (row["day7_lower"], row["day7_upper"]) == (day7["lower"], day7["upper"])
    assert row["implied_return"] == pytest.approx(day7["median"] / f["origin_price"] - 1)
    detail = engine.detail(f["id"], history_days=7)
    assert detail["forecast"]["points"] == f["points"]
    assert detail["history"][-1]["time"] == ORIGIN
    assert detail["history"][0]["time"] >= ORIGIN - 7 * 86400
    assert all(p["time"] <= ORIGIN for p in detail["history"])
    with pytest.raises(ValueError, match="History range"):
        engine.detail(f["id"], history_days=11)


def test_aggregate_counts_pending_scored_and_unscorable_targets(engine, data, model):
    f = published(engine, data, model)
    engine.score(data, f, ORIGIN + 2 * 86400)
    summary = aggregate(engine.store, "case")
    assert summary["scorable_target_count"] == 2
    assert summary["pending_target_count"] == 5
    assert summary["unscorable_target_count"] == 0
    assert summary["evaluation_state_counts"]["partially_evaluated"] == 1
    by_model = summary["by_model"][model["id"]]
    assert by_model["horizon_sample_count"]["24"] == 1
    assert by_model["horizon_mae_usdt"]["168"] is None


def test_shared_evaluate_rejects_clock_before_origin(engine, data, model):
    f = published(engine, data, model)
    with pytest.raises(ValueError, match="not before the origin"):
        engine.evaluate_at(f["id"], iso(ORIGIN - 3600))
    assert engine.evaluate_at(f["id"], iso(ORIGIN + 86400))["scored_count"] == 1


def test_retraining_decision_records_use_of_final_test_outcomes(
    engine, data, model, monkeypatch
):
    engine.store.put("models", model, immutable=True)
    monkeypatch.setattr(
        service, "train", lambda *a, **k: dict(model, id="pv-candidate")
    )
    clock = stamp("2026-08-01T00:00:00+00:00")
    engine.candidate(data, model, clock, "manual", lambda: None, lambda *a: None)
    decision = engine.store.list("decisions")[0]
    assert decision["uses_final_test_outcomes"] is True
    assert clock > SPLITS["validation"]["end"].timestamp()


def test_new_http_endpoints(engine, data, model, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.api import forecasts

    f = published(engine, data, model, run_id="r-http")
    engine.store.put(
        "runs",
        dict(
            id="r-http",
            created_at=iso(ORIGIN),
            mode="frozen",
            status="complete",
            clock=iso(ORIGIN),
            skipped_origins=[],
            summary={"large": True},
        ),
    )
    monkeypatch.setattr(forecasts, "engine", engine)
    monkeypatch.setattr(forecasts, "jobs", engine.jobs)
    client = TestClient(app)
    history = client.get("/api/forecasting/forecasts?run_id=r-http").json()
    assert history["total"] == 1 and history["rows"][0]["id"] == f["id"]
    agents = client.get(f"/api/forecasting/forecasts/{f['id']}/agents").json()
    assert agents["publisher"] == "Saved"
    origins = client.get("/api/forecasting/runs/r-http/origins").json()
    assert origins["saved"][0]["forecast_id"] == f["id"]
    assert "summary" not in client.get("/api/forecasting/runs").json()[0]
    assert client.get(f"/api/forecasting/models/{model['id']}").json()["id"] == model["id"]
    assert client.get("/api/forecasting/models/nope").status_code == 404
    assert client.get("/api/forecasting/jobs/nope").status_code == 404
    assert (
        client.get(f"/api/forecasting/forecasts/{f['id']}?history_days=11").status_code
        == 400
    )
    assert client.get("/api/forecasting/forecasts/missing").status_code == 404


def test_relative_and_legacy_absolute_bundle_pointers(tmp_path, monkeypatch):
    import json
    from backend.app import processor

    monkeypatch.setattr(processor, "DATA_DIR", tmp_path)
    monkeypatch.setattr(processor, "PROCESSED_DATA_DIR", tmp_path / "processed")
    (tmp_path / "processed").mkdir()
    pointer = tmp_path / "processed" / "BTCUSDT_current.json"
    proc = processor.DatasetProcessor("BTCUSDT")
    pointer.write_text(json.dumps({"bundle": "bundles/BTCUSDT/abc"}))
    assert proc.current_bundle() == tmp_path / "bundles" / "BTCUSDT" / "abc"
    pointer.write_text(json.dumps({"bundle": "/elsewhere/data/bundles/BTCUSDT/abc"}))
    assert proc.current_bundle() == tmp_path / "bundles" / "BTCUSDT" / "abc"


def test_train_and_predict_publishes_a_prediction_from_the_trained_model(
    engine, data, model, monkeypatch
):
    engine.store.put("models", model, immutable=True)
    calls = []

    def replay(config, job_id):
        calls.append(config)
        engine.store.put(
            "runs",
            {"id": "r-tp", "mode": "frozen", "model_id": model["id"], "initial_model_id": model["id"]},
        )
        return {"run_id": "r-tp", "model_id": model["id"], "forecast_id": "replayed"}

    monkeypatch.setattr(engine, "_train_backtest", replay)
    result = engine.train_and_predict({"mode": "frozen"}, None, iso(ORIGIN))
    assert calls == [{"mode": "frozen"}]
    saved = engine.store.get("forecasts", result["forecast_id"])
    assert saved["mode"] == "prediction"
    assert saved["model_version"] == model["id"]
    assert saved["origin"] == iso(ORIGIN)
    assert result["replay_run_id"] == "r-tp"
    assert "run_id" not in result


def test_run_scores_report_stored_outcomes_and_the_no_change_miss(engine, data, model):
    engine.store.put(
        "runs",
        dict(id="r-sc", created_at=iso(ORIGIN), mode="frozen", status="complete", clock=iso(ORIGIN)),
    )
    f = published(engine, data, model, run_id="r-sc")
    engine.evaluate_at(f["id"], iso(ORIGIN + 86400))
    rows = engine.run_scores("r-sc")["rows"]
    assert [r["forecast_id"] for r in rows] == [f["id"]]
    first, later = rows[0]["points"][0], rows[0]["points"][1:]
    actual = first["actual"]
    assert first["error"] == pytest.approx(abs(actual - f["points"][0]["median"]))
    assert first["baseline_error"] == pytest.approx(abs(actual - f["origin_price"]))
    assert first["covered"] == (f["points"][0]["lower"] <= actual <= f["points"][0]["upper"])
    # Outcomes after the evaluation clock stay unknown, never filled in.
    assert all(p["actual"] is None and p["covered"] is None for p in later)
    day7 = engine.history(run_id="r-sc")["rows"][0]
    assert day7["day7_actual"] is None and day7["day7_error"] is None
    assert engine.run_scores("r-sc", model_id="other")["rows"] == []
