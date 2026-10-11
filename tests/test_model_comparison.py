"""Numerical families, artifact integrity and aligned visual comparison evidence."""

import copy
import numpy as np
import pytest
from backend.app.forecasting import estimators
from backend.app.forecasting.specialist import fit, raw, train, stamp
from backend.app.forecasting import comparison
from backend.app.forecasting.comparison import (
    configured_families,
    evidence,
    run_comparison,
    select_on_validation,
    validation_errors,
)
from backend.app.forecasting.service import Engine


@pytest.mark.parametrize("family", list(estimators.FAMILIES))
def test_all_registered_families_predict_seven_outputs_from_training_only(family):
    rng = np.random.default_rng(123)
    x = rng.normal(size=(90, 16))
    y = rng.normal(scale=0.01, size=(90, 7))
    params = (
        fit(x, y, 10)
        if family == "direct-ridge-log-return"
        else estimators.fit(x, y, family)
    )
    prediction = raw(params, x[-2:])
    assert prediction.shape == (2, 7) and np.isfinite(prediction).all()
    assert np.allclose(params["mean"], x.mean(axis=0))
    if family != "direct-ridge-log-return":
        assert params["family"] == family
        tampered = dict(params, estimator_sha256="bad")
        with pytest.raises(ValueError, match="checksum"):
            raw(tampered, x[-1:])


def test_nonridge_model_selection_ignores_final_test_mutation(
    data, store, tmp_path, monkeypatch
):
    from backend.app.forecasting import specialist

    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    original = train(data, store, lookbacks=(30,), family="elastic-net")
    changed = copy.deepcopy(data)
    changed.close[changed.times > stamp("2026-06-01T00:00:00Z")] *= 2
    changed._features = {}
    repeated = train(changed, store, lookbacks=(30,), family="elastic-net")
    assert original["parameters"] == repeated["parameters"]
    assert original["residuals"] == repeated["residuals"]


def test_visual_evidence_aligns_targets_and_preserves_unavailable_prices(
    data, model, store
):
    engine = Engine(store)
    store.put("models", model, immutable=True)
    start = stamp("2026-06-01T00:00:00Z")
    end = int(data.times[-1])
    for o in (start, end - 86400):
        f = engine.publish(data, model, o, "visual", "comparison")
        engine.score(data, f, end)
    store.put(
        "runs",
        dict(
            id="visual",
            mode="comparison",
            status="complete",
            start="2026-06-01T00:00:00Z",
            end="2026-10-01T00:00:00Z",
            clock="2026-10-01T00:00:00Z",
            dataset_version=data.version,
            models=[dict(model_id=model["id"], label="Ridge", family=model["family"])],
        ),
    )
    result = evidence(engine, "visual", 168)
    assert len(result["lines"][0]["points"]) == 2
    assert len(result["actual"]) == 1
    assert result["actual"][0]["time"] == start + 7 * 86400
    assert (
        result["actual"][0]["value"] == data.close[data.indices[int(start + 7 * 86400)]]
    )
    with pytest.raises(ValueError, match="horizon"):
        evidence(engine, "visual", 25)


def test_default_comparison_trains_three_distinct_families_and_others_stay_available(
    monkeypatch,
):
    assert configured_families() == ["direct-ridge-log-return", "lightgbm", "knn"]
    assert len(estimators.FAMILIES) == 10
    monkeypatch.setattr(comparison, "COMPARISON_FAMILIES", ("catboost", "knn", "knn"))
    assert configured_families() == ["catboost", "knn"]
    assert configured_families(["elastic-net"]) == ["elastic-net"]
    with pytest.raises(ValueError, match="Unknown model family"):
        configured_families(["prophet"])


def test_validation_selection_uses_shared_origins_and_lowest_day7_error():
    base = np.full(7, 100.0)
    origins = range(40)
    errors = {
        "direct-ridge-log-return": {o: (np.full(7, 90.0), base) for o in origins},
        "knn": {o: (np.full(7, 120.0), base) for o in origins},
        # Extra origin outside the shared set must not count for anyone.
        "lightgbm": {o: (np.full(7, 80.0), base) for o in range(41)},
    }
    errors["lightgbm"][40] = (np.full(7, 1e9), base)
    result = select_on_validation(errors)
    assert result["sample_count"] == 40
    assert result["winner"] == "lightgbm" and result["winner_beats_no_change"]
    assert [c["family"] for c in result["candidates"]] == [
        "lightgbm",
        "direct-ridge-log-return",
        "knn",
    ]
    assert result["candidates"][0]["day7_mae_usdt"] == 80
    assert result["candidates"][2]["day7_skill_vs_no_change"] == pytest.approx(-0.2)
    assert [c["selected"] for c in result["candidates"]] == [True, False, False]
    worse = {f: {o: (np.full(7, 150.0), base) for o in origins} for f in ("knn",)}
    assert not select_on_validation(worse)["winner_beats_no_change"]
    with pytest.raises(ValueError, match="validation evidence"):
        select_on_validation({"knn": {o: (base, base) for o in range(10)}})


def test_validation_errors_end_before_final_test_and_ignore_its_outcomes(data, model):
    errors = validation_errors(data, model)
    final_test = data.market.splits["final_test"]["start"].timestamp()
    assert len(errors) >= 30
    assert all(
        data.calendar.horizon_target(o, 7) <= final_test
        and o >= stamp(model["calibration_period"]["start"])
        for o in errors
    )
    changed = copy.deepcopy(data)
    changed.close[changed.times > final_test] *= 2
    changed._features = {}
    repeated = validation_errors(changed, model)
    assert errors.keys() == repeated.keys()
    assert all(np.array_equal(errors[o][0], repeated[o][0]) for o in errors)


def test_comparison_final_tests_only_the_validation_winner(
    data, store, tmp_path, monkeypatch
):
    from backend.app.forecasting import specialist

    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    (tmp_path / "models").mkdir()
    monkeypatch.setattr(comparison, "REPORTS_DIR", tmp_path)
    engine = Engine(store)
    families = ["direct-ridge-log-return", "bayesian-ridge"]
    run_id = run_comparison(engine, families=families)["comparison_id"]
    run = store.get("runs", run_id)
    selection = run["validation_selection"]
    assert run["status"] == "complete" and run["families"] == families
    assert {c["family"] for c in selection["candidates"]} == set(families)
    winner = selection["winner"]
    assert [m["family"] for m in run["models"]] == [winner]
    assert run["model_id"] == run["models"][0]["model_id"]
    loser = next(c for c in selection["candidates"] if not c["selected"])
    assert loser["status"] == "not_selected"
    # Only the chosen model is kept; the loser's validation scores stay on the run.
    assert [m["id"] for m in store.list("models")] == [run["model_id"]]
    assert loser["day7_mae_usdt"] is not None
    forecasts = store.list("forecasts")
    assert forecasts and all(
        f["model_version"] == run["model_id"] for f in forecasts
    )
    assert not any(f["model_version"] == loser["model_id"] for f in forecasts)
    result = evidence(engine, run_id, 168)
    assert [line["family"] for line in result["lines"]] == [winner]
    assert (tmp_path / f"{run_id}_comparison.json").exists()


def _comparison_engine(store, tmp_path, monkeypatch):
    from backend.app.forecasting import specialist, service

    monkeypatch.setattr(specialist, "DATA_DIR", tmp_path)
    (tmp_path / "models").mkdir(exist_ok=True)
    monkeypatch.setattr(comparison, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(service, "REPORTS_DIR", tmp_path)
    return Engine(store)


def test_new_comparison_replaces_the_previous_run_models_and_forecasts(
    data, store, tmp_path, monkeypatch
):
    engine = _comparison_engine(store, tmp_path, monkeypatch)
    families = ["direct-ridge-log-return"]
    first = run_comparison(engine, families=families)["comparison_id"]
    old = store.get("runs", first)
    old_forecasts = {f["id"] for f in store.list("forecasts")}
    store.put("decisions", {"id": "d-old", "run_id": first}, immutable=True)
    engine.setting("selected_model", old["model_id"])

    second = run_comparison(engine, families=families)["comparison_id"]
    run = store.get("runs", second)
    assert [r["id"] for r in store.list("runs")] == [second]
    assert [m["id"] for m in store.list("models")] == [run["model_id"]]
    assert run["model_id"] != old["model_id"]
    forecasts = store.list("forecasts")
    assert forecasts and not old_forecasts & {f["id"] for f in forecasts}
    assert all(f["model_version"] == run["model_id"] for f in forecasts)
    assert all(store.evaluation(id) is None for id in old_forecasts)
    assert store.list("decisions") == []
    assert engine.setting("selected_model") == run["model_id"]
    assert sorted(p.name for p in (tmp_path / "models").iterdir()) == [f"{run['model_id']}.json"]
    assert not (tmp_path / f"{first}_comparison.json").exists()
    assert (tmp_path / f"{second}_comparison.json").exists()
    # The no-change comparison still works on the surviving run.
    m = run["models"][0]["metrics"]
    assert m["horizons"][-1]["baseline_mae_usdt"] > 0
    assert engine.run_scores(second)["rows"]
    # Kept forecasts stay immutable.
    with pytest.raises(Exception):
        with store.connection() as db:
            db.execute("DELETE FROM forecasts")


def test_failed_comparison_keeps_the_previous_run_untouched(
    data, store, tmp_path, monkeypatch
):
    engine = _comparison_engine(store, tmp_path, monkeypatch)
    families = ["direct-ridge-log-return"]
    first = run_comparison(engine, families=families)["comparison_id"]
    before = (
        [r["id"] for r in store.list("runs")],
        [m["id"] for m in store.list("models")],
        sorted(f["id"] for f in store.list("forecasts")),
        sorted(p.name for p in (tmp_path / "models").iterdir()),
    )

    def broken(*args, **kwargs):
        raise ValueError("scoring broke")

    monkeypatch.setattr(engine, "score", broken)
    with pytest.raises(ValueError, match="scoring broke"):
        run_comparison(engine, families=families)
    after = (
        [r["id"] for r in store.list("runs")],
        [m["id"] for m in store.list("models")],
        sorted(f["id"] for f in store.list("forecasts")),
        sorted(p.name for p in (tmp_path / "models").iterdir()),
    )
    assert after == before and before[0] == [first]
