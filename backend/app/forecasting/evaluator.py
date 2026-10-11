"""Exact-target scoring with replay-clock maturity and overlap-aware summaries."""

import numpy as np
from backend.app.forecasting.specialist import stamp, iso


AGENT_EVALUATION_STATES = {
    "pending": "Pending",
    "partially_evaluated": "Partial",
    "fully_evaluated": "Complete",
    "unscorable_due_to_missing_data": "Unscorable",
}


def interval_score(actual, lower, upper):
    return (upper - lower) + 10 * max(lower - actual, 0) + 10 * max(actual - upper, 0)


def score_point(actual, price, point):
    return dict(
        actual_price=float(actual),
        absolute_price_error=abs(actual - point["median"]),
        absolute_return_error_percentage_points=100
        * abs((actual - point["median"]) / price),
        interval_coverage=point["lower"] <= actual <= point["upper"],
        interval_width=point["upper"] - point["lower"],
        interval_score=interval_score(actual, point["lower"], point["upper"]),
    )


def evaluate(data, forecast, clock):
    if data.version != forecast["dataset_version"]:
        raise ValueError("Evaluation requires the published dataset version")
    points = []
    for j, p in enumerate(forecast["points"]):
        target = stamp(p["target"])
        item = {
            "target": p["target"],
            "horizon_hours": p["horizon_hours"],
            "state": "pending",
        }
        if target <= clock:
            i = data.indices.get(int(target))
            if i is None:
                item["state"] = "unscorable"
            else:
                item.update(
                    state="evaluated",
                    **score_point(float(data.close[i]), forecast["origin_price"], p)
                )
                item["baseline"] = score_point(
                    float(data.close[i]),
                    forecast["origin_price"],
                    forecast["baseline"]["points"][j],
                )
                if j == 6:
                    positive = bool(data.close[i] > forecast["origin_price"])
                    direction = (
                        1
                        if data.close[i] > forecast["origin_price"]
                        else (-1 if data.close[i] < forecast["origin_price"] else 0)
                    )
                    probs = forecast["probabilities"]
                    predicted = max(
                        (1, -1, 0),
                        key=lambda d: probs[
                            {1: "positive", -1: "negative", 0: "zero"}[d]
                        ],
                    )
                    item.update(
                        actual_direction=direction,
                        positive_outcome=positive,
                        direction_accuracy=predicted == direction,
                        brier_score=(probs["positive"] - float(positive)) ** 2,
                        baseline_brier_score=(
                            forecast["baseline"]["positive_probability"]
                            - float(positive)
                        )
                        ** 2,
                    )
        points.append(item)
    n = sum(p["state"] == "evaluated" for p in points)
    state = "fully_evaluated" if n == 7 else ("partially_evaluated" if n else "pending")
    if any(p["state"] == "unscorable" for p in points) and not any(
        p["state"] == "pending" for p in points
    ):
        state = "unscorable_due_to_missing_data"
    return dict(
        forecast_id=forecast["id"],
        clock=iso(clock),
        state=state,
        scored_count=n,
        points=points,
    )


def aggregate(store, run_id, role="coordinated", model_id=None):
    forecasts = [
        f
        for f in store.list("forecasts")
        if f["run_id"] == run_id
        and f["role"] == role
        and (model_id is None or f["model_version"] == model_id)
    ]
    horizons = []
    week = []
    evaluations = {f["id"]: store.evaluation(f["id"]) for f in forecasts}
    state_counts = {k: 0 for k in AGENT_EVALUATION_STATES}
    for ev in evaluations.values():
        state_counts[(ev or {}).get("state", "pending")] += 1
    by_model_horizons = {}
    for h in range(1, 8):
        rows = []
        counts = {"evaluated": 0, "pending": 0, "unscorable": 0}
        for f in sorted(forecasts, key=lambda f: f["origin"]):
            ev = evaluations[f["id"]]
            point_state = ev["points"][h - 1]["state"] if ev else "pending"
            counts[point_state] += 1
            if point_state == "evaluated":
                rows.append(ev["points"][h - 1])
                by_model_horizons.setdefault(f["model_version"], {}).setdefault(
                    h, []
                ).append(ev["points"][h - 1]["absolute_price_error"])
                if h == 7:
                    week.append((f, ev["points"][h - 1]))
        if not rows:
            horizons.append(
                {
                    "horizon_hours": h * 24,
                    "sample_count": 0,
                    "pending_count": counts["pending"],
                    "unscorable_count": counts["unscorable"],
                }
            )
            continue
        errors = np.array([r["absolute_price_error"] for r in rows])
        ci = None
        if len(errors) >= 14:
            rng = np.random.default_rng(20261010)
            # Daily origins have overlapping seven-day targets: moving blocks of 7.
            means = []
            for _ in range(400):
                starts = rng.integers(0, len(errors), size=(len(errors) + 6) // 7)
                sample = np.concatenate(
                    [errors[(s + np.arange(7)) % len(errors)] for s in starts]
                )[: len(errors)]
                means.append(sample.mean())
            ci = np.quantile(means, [0.025, 0.975]).tolist()
        avg = lambda k: float(np.mean([r[k] for r in rows]))
        bavg = lambda k: float(np.mean([r["baseline"][k] for r in rows]))
        horizons.append(
            dict(
                horizon_hours=h * 24,
                sample_count=len(rows),
                mae_usdt=avg("absolute_price_error"),
                return_mae_percentage_points=avg(
                    "absolute_return_error_percentage_points"
                ),
                coverage=avg("interval_coverage"),
                width_usdt=avg("interval_width"),
                interval_score_usdt=avg("interval_score"),
                baseline_mae_usdt=bavg("absolute_price_error"),
                baseline_coverage=bavg("interval_coverage"),
                baseline_interval_score_usdt=bavg("interval_score"),
                mae_95pct_block_bootstrap=ci,
                pending_count=counts["pending"],
                unscorable_count=counts["unscorable"],
            )
        )
    calibration = []
    if len(week) >= 30:
        for lo in np.arange(0, 1, 0.2):
            selected = [
                (f, p)
                for f, p in week
                if lo <= f["probabilities"]["positive"] < lo + 0.2
                or (lo > 0.7 and f["probabilities"]["positive"] == 1)
            ]
            calibration.append(
                dict(
                    lower=float(lo),
                    upper=float(lo + 0.2),
                    sample_count=len(selected),
                    predicted_positive=(
                        float(
                            np.mean(
                                [f["probabilities"]["positive"] for f, _ in selected]
                            )
                        )
                        if selected
                        else None
                    ),
                    actual_positive=(
                        float(np.mean([p["positive_outcome"] for _, p in selected]))
                        if selected
                        else None
                    ),
                )
            )
    by_model = {}
    for model_id in {f["model_version"] for f in forecasts}:
        selected = [p for f, p in week if f["model_version"] == model_id]
        by_model[model_id] = {
            "horizon_mae_usdt": {
                str(h * 24): (
                    float(np.mean(by_model_horizons[model_id][h]))
                    if by_model_horizons.get(model_id, {}).get(h)
                    else None
                )
                for h in range(1, 8)
            },
            "horizon_sample_count": {
                str(h * 24): len(by_model_horizons.get(model_id, {}).get(h, []))
                for h in range(1, 8)
            },
            "day7_sample_count": len(selected),
            "day7_mae_usdt": (
                float(np.mean([p["absolute_price_error"] for p in selected]))
                if selected
                else None
            ),
        }
    return dict(
        run_id=run_id,
        forecast_count=len(forecasts),
        evaluation_state_counts=state_counts,
        scorable_target_count=sum(h["sample_count"] for h in horizons),
        unscorable_target_count=sum(h["unscorable_count"] for h in horizons),
        pending_target_count=sum(h["pending_count"] for h in horizons),
        horizons=horizons,
        by_model=by_model,
        weekly={
            "sample_count": len(week),
            "direction_accuracy": (
                float(np.mean([p["direction_accuracy"] for _, p in week]))
                if week
                else None
            ),
            "brier_score": (
                float(np.mean([p["brier_score"] for _, p in week])) if week else None
            ),
            "baseline_brier_score": (
                float(np.mean([p["baseline_brier_score"] for _, p in week]))
                if week
                else None
            ),
        },
        probability_calibration=calibration,
        calibration_status=(
            "Available"
            if calibration
            else "Insufficient evidence: at least 30 matured weekly outcomes required"
        ),
        uncertainty_method="95% moving-block bootstrap for MAE, block length 7 daily origins; descriptive, not proof of superiority",
        baseline="No-change price, earlier historical-frequency direction, earlier empirical log-return pointwise intervals",
    )
