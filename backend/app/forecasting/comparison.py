"""Configured-family development comparison: winner chosen on validation, final test once."""

import hashlib
import inspect
import json
import uuid
import numpy as np
from backend.app.config import REPORTS_DIR, COMPARISON_FAMILIES
from backend.app.storage import now, atomic_json
from backend.app.forecasting.specialist import train, stamp, iso, raw
from backend.app.forecasting.evaluator import aggregate
from backend.app.forecasting.estimators import FAMILIES, fit as estimator_fit, make

SELECTION_METRIC = "day7_mae_usdt"


def configured_families(families=None):
    """Validated, de-duplicated family list for a comparison (config default)."""
    chosen = list(dict.fromkeys(families or COMPARISON_FAMILIES))
    unknown = [f for f in chosen if f not in FAMILIES]
    if unknown:
        raise ValueError(
            f"Unknown model family: {', '.join(unknown)}. Choose from {', '.join(FAMILIES)}"
        )
    if not chosen:
        raise ValueError("Choose at least one model family to compare")
    return chosen


def validation_errors(data, model):
    """Absolute price errors per daily origin on the model's calibration window.

    That window is the later part of validation: no family fitted on it or chose
    its look-back on it, and every target matures before final test starts. The
    point forecast is the fitted estimator's output alone, because the residual
    median shift is itself estimated on this window.
    """
    period = model["calibration_period"]
    origins, x, y, prices = data.examples(
        model["configuration"]["lookback_days"],
        stamp(period["start"]),
        stamp(period["end_exclusive"]),
    )
    if not len(origins):
        return {}
    actual = prices[:, None] * np.exp(y)
    predicted = prices[:, None] * np.exp(raw(model["parameters"], x))
    return {
        int(o): (np.abs(actual[k] - predicted[k]), np.abs(actual[k] - prices[k]))
        for k, o in enumerate(origins)
    }


def select_on_validation(errors_by_family):
    """Score every family on the same validation origins and pick the lowest day-7 MAE."""
    shared = sorted(set.intersection(*(set(e) for e in errors_by_family.values())))
    if len(shared) < 30:
        raise ValueError(
            "Insufficient shared validation evidence (minimum 30 daily origins)"
        )
    any_errors = next(iter(errors_by_family.values()))
    baseline = np.array([any_errors[o][1] for o in shared])
    rows = []
    for family, errors in errors_by_family.items():
        model = np.array([errors[o][0] for o in shared])
        rows.append(
            dict(
                family=family,
                label=FAMILIES[family],
                sample_count=len(shared),
                horizon_mae_usdt={
                    str(24 * (h + 1)): float(model[:, h].mean())
                    for h in range(model.shape[1])
                },
                day7_mae_usdt=float(model[:, -1].mean()),
                baseline_day7_mae_usdt=float(baseline[:, -1].mean()),
                day7_skill_vs_no_change=float(
                    1 - model[:, -1].mean() / baseline[:, -1].mean()
                ),
            )
        )
    rows.sort(key=lambda r: r[SELECTION_METRIC])
    for rank, r in enumerate(rows, 1):
        r.update(rank=rank, selected=rank == 1)
    return dict(
        start=iso(shared[0]),
        end=iso(shared[-1]),
        sample_count=len(shared),
        baseline_day7_mae_usdt=rows[0]["baseline_day7_mae_usdt"],
        winner=rows[0]["family"],
        winner_beats_no_change=rows[0]["day7_mae_usdt"]
        < rows[0]["baseline_day7_mae_usdt"],
        candidates=rows,
    )


def run_comparison(engine, origin=None, job_id=None, families=None):
    """Train & Compare. A finished comparison replaces every earlier run and model."""
    with engine.replacing_previous_run(job_id) as outcome:
        result = _run_comparison(engine, origin, job_id, families)
        outcome["run_id"] = result["comparison_id"]
    return result


def _run_comparison(engine, origin=None, job_id=None, families=None):
    check = lambda: engine.jobs.check(job_id) if job_id else None
    families = configured_families(families)
    n = len(families)

    def progress(label, pct):
        check()
        if job_id:
            engine.jobs.update(job_id, current_step=label, progress_percentage=pct)

    progress("Verifying shared Bitcoin dataset", 1)
    data = engine.load_data()
    splits = engine.market.splits
    start = int(splits["final_test"]["start"].timestamp())
    end = min(int(splits["final_test"]["end"].timestamp()), int(data.times[-1]))
    t = stamp(origin) if origin else int(data.times[-1])
    # Validate origin before training or publishing anything.
    if (
        not np.isfinite(t)
        or t < start
        or t > data.times[-1]
        or int(t) not in data.indices
    ):
        raise ValueError(
            "Choose an exact completed hourly origin after calibration, within the dataset"
        )
    data.input(t, 180)
    origins = data.calendar.origins(start, end)
    eligible, skipped = [], []
    for o in origins:
        try:
            data.input(o, 180)
            eligible.append(o)
        except ValueError as e:
            skipped.append({"origin": iso(o), "reason": str(e)})
    if not eligible:
        raise ValueError("No shared eligible backtest origins")
    run = dict(
        id=uuid.uuid4().hex,
        created_at=now(),
        mode="comparison",
        status="running",
        symbol=engine.market.symbol,
        dataset_version=data.version,
        origin=iso(t),
        start=iso(start),
        end=iso(end),
        clock=iso(end),
        families=families,
        # Only models scored on final test appear here (the validation winner).
        models=[],
        validation_selection=dict(
            metric=SELECTION_METRIC,
            method="Lowest seven-day price MAE on the later validation window, shared daily origins; "
            "no-change baseline on the same origins. Final test is scored for the winner only.",
            candidates=[],
        ),
        skipped_origins=skipped,
        development=True,
        evaluation_label="Development comparison: winner chosen on validation and only the winner is scored on final test, "
        "but final-test outcomes were inspected by earlier runs; confirm any winner on fresh unseen data",
        protocol_id=hashlib.sha256(
            (
                json.dumps(families)
                + inspect.getsource(make)
                + inspect.getsource(estimator_fit)
                + inspect.getsource(train)
                + inspect.getsource(validation_errors)
                + inspect.getsource(select_on_validation)
            ).encode()
        ).hexdigest(),
        model_id="",
        initial_model_id="",
    )
    engine.store.put("runs", run)
    if job_id:
        engine.jobs.update(job_id, run_id=run["id"])
    try:
        trained, errors = {}, {}
        for i, family in enumerate(families):
            label = FAMILIES[family]
            progress(f"Training {i+1}/{n} · {label}", 2 + 60 * i / n)
            model = train(
                data,
                engine.store,
                check,
                lambda msg, p: progress(f"{label} · {msg}", 2 + 60 * (i + p / 100) / n),
                family=family,
            )
            trained[family] = model
            errors[family] = validation_errors(data, model)
            run["validation_selection"]["candidates"].append(
                dict(
                    family=family,
                    label=label,
                    model_id=model["id"],
                    lookback_days=model["configuration"]["lookback_days"],
                    status="trained",
                )
            )
            engine.store.put("runs", run)
        progress("Choosing the winner on validation", 63)
        selection = select_on_validation(errors)
        for c in selection["candidates"]:
            m = trained[c["family"]]
            c.update(
                model_id=m["id"],
                lookback_days=m["configuration"]["lookback_days"],
                status="selected" if c["selected"] else "not_selected",
            )
        run["validation_selection"].update(selection)
        model = trained[selection["winner"]]
        label = FAMILIES[selection["winner"]]
        row = dict(
            family=selection["winner"],
            label=label,
            model_id=model["id"],
            status="backtesting",
            lookback_days=model["configuration"]["lookback_days"],
            selected_on_validation=True,
        )
        run["models"].append(row)
        engine.store.put("runs", run)
        for j, o in enumerate(eligible):
            check()
            f = engine.publish(data, model, o, run["id"], "comparison")
            # Frozen model was fitted before test starts; score only observed exact outcomes.
            engine.score(data, f, end)
            if j % 15 == 0:
                progress(
                    f"{label} · backtest {j+1}/{len(eligible)}",
                    64 + 33 * j / len(eligible),
                )
        current = engine.predict(iso(t), model["id"], check)
        engine.score(data, current, end)
        row.update(
            status="complete",
            forecast_id=current["id"],
            metrics=aggregate(engine.store, run["id"], model_id=model["id"]),
        )
        run.update(status="complete", model_id=model["id"], initial_model_id=model["id"])
        engine.store.put("runs", run)
        atomic_json(REPORTS_DIR / f"{run['id']}_comparison.json", run)
        progress(
            f"{n} families trained; {label} chosen on validation, final-tested and saved; earlier runs replaced",
            100,
        )
        return {"comparison_id": run["id"]}
    except BaseException as e:
        run.update(status="interrupted", error=str(e))
        engine.store.put("runs", run)
        raise


def evidence(engine, run_id, horizon=168):
    if horizon not in range(24, 169, 24):
        raise ValueError("Choose a daily horizon between 24 and 168 hours")
    run = engine.store.get("runs", run_id)
    data = engine.load_data(run["dataset_version"])
    forecasts = [
        f
        for f in engine.store.list("forecasts")
        if f["run_id"] == run_id and f["role"] == "coordinated"
    ]
    clock = stamp(run.get("clock", run["end"]))
    actual = {}
    lines = []
    for row in run.get("models", []):
        fs = sorted(
            [f for f in forecasts if f["model_version"] == row["model_id"]],
            key=lambda f: f["origin"],
        )
        points = []
        for f in fs:
            p = f["points"][horizon // 24 - 1]
            target = int(stamp(p["target"]))
            points.append(
                dict(
                    time=target,
                    value=p["median"],
                    origin=f["origin"],
                    forecast_id=f["id"],
                    lower=p["lower"],
                    upper=p["upper"],
                )
            )
            if target <= clock and target in data.indices:
                actual[target] = float(data.close[data.indices[target]])
        lines.append(
            dict(
                label=row.get("label", row["model_id"]),
                model_id=row["model_id"],
                family=row.get("family", "direct-ridge-log-return"),
                points=points,
            )
        )
    if not lines and forecasts:
        # Existing single-model runs also get a visual summary without recomputation.
        for mid in sorted({f["model_version"] for f in forecasts}):
            m = engine.store.get("models", mid)
            fs = sorted(
                [f for f in forecasts if f["model_version"] == mid],
                key=lambda f: f["origin"],
            )
            points = []
            for f in fs:
                p = f["points"][horizon // 24 - 1]
                target = int(stamp(p["target"]))
                points.append(
                    dict(
                        time=target,
                        value=p["median"],
                        origin=f["origin"],
                        forecast_id=f["id"],
                        lower=p["lower"],
                        upper=p["upper"],
                    )
                )
                if target <= clock and target in data.indices:
                    actual[target] = float(data.close[data.indices[target]])
            lines.append(
                dict(
                    label=FAMILIES.get(m["family"], m["family"]),
                    model_id=mid,
                    family=m["family"],
                    points=points,
                )
            )
    return dict(
        run=run,
        horizon_hours=horizon,
        actual=[dict(time=t, value=v) for t, v in sorted(actual.items())],
        lines=lines,
        observed_through=iso(clock),
    )
