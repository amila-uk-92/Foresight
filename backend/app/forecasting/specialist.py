"""Seven direct ridge log-return models with chronological empirical calibration."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from backend.app.config import DATA_DIR
from backend.app.markets import get_market, primary_market
from backend.app.storage import now, atomic_json
from backend.app.forecasting.contracts import validate


def iso(t):
    return datetime.fromtimestamp(float(t), timezone.utc).isoformat()


def stamp(s):
    return datetime.fromisoformat(s).timestamp()


def fit(x, y, alpha):
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-10] = 1
    z = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    penalty = np.eye(z.shape[1]) * alpha
    penalty[0, 0] = 0
    coef = np.linalg.solve(z.T @ z + penalty, z.T @ y)
    return dict(mean=mean.tolist(), scale=scale.tolist(), coef=coef.tolist())


def raw(model, x):
    if "estimator_blob" in model:
        from backend.app.forecasting.estimators import predict as numerical_predict

        return numerical_predict(model, x)
    z = (x - np.array(model["mean"])) / np.array(model["scale"])
    return np.column_stack([np.ones(len(z)), z]) @ np.array(model["coef"])


def distribution(model, x):
    pred = raw(model["parameters"], np.atleast_2d(x))
    residual = np.array(model["residuals"])
    q = np.quantile(residual, [0.1, 0.5, 0.9], axis=0)
    return pred + q[1], pred + q[0], pred + q[2]


def loss(model, cases):
    _, x, y, prices = cases
    med, low, high = distribution(model, x)
    actual = prices[:, None] * np.exp(y)
    m, l, u = [prices[:, None] * np.exp(a) for a in (med, low, high)]
    mae = float(np.mean(np.abs(actual - m)))
    score = (u - l) + 10 * np.maximum(l - actual, 0) + 10 * np.maximum(actual - u, 0)
    return {
        "sample_count": len(x),
        "mae_usdt": mae,
        "interval_score_usdt": float(score.mean()),
        "coverage": float(((actual >= l) & (actual <= u)).mean()),
    }


def train(
    data,
    store,
    check=lambda: None,
    progress=lambda *a: None,
    cutoff=None,
    lookbacks=(30, 90, 180),
    alphas=(1.0, 10.0, 100.0),
    family="direct-ridge-log-return",
):
    if family != "direct-ridge-log-return":
        from backend.app.forecasting.estimators import FAMILIES, fit as numerical_fit

        if family not in FAMILIES:
            raise ValueError("Unknown model family")
        alphas = (1.0,)
    splits = data.market.splits
    start = splits["training"]["start"].timestamp()
    train_end = splits["training"]["end"].timestamp()
    val_end = splits["validation"]["end"].timestamp()
    if cutoff is None:
        selection_start = train_end
        selection_end = (
            pd.Timestamp(splits["validation"]["start"])
            + pd.DateOffset(months=max(1, splits["validation"]["duration_months"] // 2))
        ).timestamp()
        calibration_start = selection_end
        calibration_end = val_end
    else:
        # Last 120 days are a strict earlier holdout, ending at simulated cutoff.
        calibration_end = cutoff
        calibration_start = cutoff - 60 * 86400
        selection_end = calibration_start
        selection_start = cutoff - 120 * 86400
        train_end = selection_start
    candidates = []
    for days in lookbacks:
        check()
        fitting = data.examples(days, start, train_end)
        selection = data.examples(days, selection_start, selection_end)
        calibration = data.examples(days, calibration_start, calibration_end)
        if min(len(fitting[0]), len(selection[0]), len(calibration[0])) < 30:
            continue
        for alpha in alphas:
            check()
            parameters = (
                fit(fitting[1], fitting[2], alpha)
                if family == "direct-ridge-log-return"
                else numerical_fit(fitting[1], fitting[2], family)
            )
            pred = raw(parameters, selection[1])
            metric = float(
                np.mean(
                    np.abs(
                        selection[3][:, None] * (np.exp(pred) - np.exp(selection[2]))
                    )
                )
            )
            candidates.append(
                (metric, days, alpha, parameters, fitting, selection, calibration)
            )
        progress(
            f"Compared {days}-day look-back",
            20 + 20 * len(candidates) / (len(lookbacks) * len(alphas)),
        )
    if not candidates:
        raise ValueError(
            "Insufficient chronological training, selection or calibration evidence (minimum 30 daily origins per holdout)"
        )
    metric, days, alpha, parameters, fitting, selection, calibration = min(
        candidates, key=lambda c: c[0]
    )
    residuals = calibration[2] - raw(parameters, calibration[1])
    id = "pv-" + uuid.uuid4().hex[:12]
    config = {
        "family": family,
        "lookback_days": days,
        "alpha": alpha,
        "cadence": "daily 00:00 UTC",
        "lookback_candidates": list(lookbacks),
        "alpha_candidates": list(alphas),
        "feature_version": "1.0",
    }
    config_id = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[
        :20
    ]
    model = dict(
        id=id,
        created_at=now(),
        contract_version="1.0",
        specialist_id=data.market.specialist,
        symbol=data.market.symbol,
        feature_set=data.feature_set.name,
        family=config["family"],
        configuration=config,
        configuration_id=config_id,
        features=data.feature_names,
        feature_definitions=data.feature_set.definitions,
        dataset_version=data.version,
        training_cutoff=iso(calibration_end),
        fitting_period={"start": iso(start), "end_exclusive": iso(train_end)},
        selection_period={
            "start": iso(selection_start),
            "end_exclusive": iso(selection_end),
        },
        calibration_period={
            "start": iso(calibration_start),
            "end_exclusive": iso(calibration_end),
        },
        fitting_latest_target=iso(
            data.calendar.horizon_target(fitting[0][-1], data.horizons)
        ),
        calibration_latest_target=iso(
            data.calendar.horizon_target(calibration[0][-1], data.horizons)
        ),
        counts={
            "fitting": len(fitting[0]),
            "selection": len(selection[0]),
            "calibration": len(calibration[0]),
        },
        parameters=parameters,
        residuals=residuals.tolist(),
        selection_mae_usdt=metric,
        candidate_selection=[
            {"lookback_days": c[1], "alpha": c[2], "mae_usdt": c[0]} for c in candidates
        ],
        development=cutoff is not None,
        probability_method="Empirical chronological calibration residual distribution; exact zero mass retained",
        interval_method="Horizon-specific chronological residual 10th/90th percentiles; pointwise, not simultaneous",
    )
    model["calibration_metrics"] = loss(model, calibration)
    path = DATA_DIR / "models" / f"{id}.json"
    model["artifact_path"] = str(path)
    check()
    atomic_json(path, model)
    store.put("models", model, immutable=True)
    return model


def model_market(model):
    """Market a stored model was trained for; models before markets were BTC."""
    return get_market(model["symbol"]) if model.get("symbol") else primary_market()


def uses_final_test_outcomes(model):
    """True when any training, selection or calibration target matured inside final test."""
    validation_end = model_market(model).splits["validation"]["end"]
    return stamp(model["training_cutoff"]) > validation_end.timestamp()


def predict(data, model, origin, run_id, mode="prediction"):
    if model["dataset_version"] != data.version:
        raise ValueError("Model and dataset version differ")
    if model_market(model).symbol != data.market.symbol:
        raise ValueError("Model and dataset market differ")
    if stamp(model["training_cutoff"]) > origin:
        raise ValueError("Model was not available at this historical origin")
    days = model["configuration"]["lookback_days"]
    market, calendar, steps = data.market, data.calendar, range(1, data.horizons + 1)
    i, x = data.input(origin, days)
    median, lower, upper = distribution(model, x)
    price = float(data.close[i])
    outputs = [price * np.exp(v[0]) for v in (median, lower, upper)]
    if not all(np.isfinite(v).all() for v in outputs):
        raise ValueError("Numerically invalid prediction")
    points = [
        dict(
            target=iso(calendar.horizon_target(origin, d)),
            horizon_hours=calendar.horizon_hours(d),
            median=float(outputs[0][d - 1]),
            lower=float(outputs[1][d - 1]),
            upper=float(outputs[2][d - 1]),
        )
        for d in steps
    ]
    simulated = (
        raw(model["parameters"], x[None, :])[0, -1]
        + np.array(model["residuals"])[:, -1]
    )
    probabilities = {
        "positive": float(np.mean(simulated > 0)),
        "negative": float(np.mean(simulated < 0)),
        "zero": float(np.mean(simulated == 0)),
    }
    # Baselines frozen at origin, never estimated from the later outcome.
    earlier = data.examples(days, origin - days * 86400, origin)
    if len(earlier[0]) < 10:
        raise ValueError("Insufficient earlier baseline evidence")
    returns = earlier[2]
    bq = np.quantile(returns, [0.1, 0.9], axis=0)
    flags = (
        ["Missing hourly candles retained; incomplete examples excluded"]
        if data.quality.get("missing_hours_count", 0)
        else []
    )
    if uses_final_test_outcomes(model):
        flags.append(
            "Model was fitted or calibrated with final-test-period outcomes; "
            "not an untouched final-test model"
        )
    f = dict(
        id=str(
            uuid.uuid5(
                uuid.NAMESPACE_URL, f'{run_id}:{model["id"]}:{origin}:specialist'
            )
        ),
        run_id=run_id,
        role="specialist",
        specialist_id=market.specialist,
        contract_version="1.0",
        model_version=model["id"],
        symbol=market.symbol,
        market=market.venue,
        quote_currency=market.quote_asset,
        origin=iso(origin),
        generated_at=now(),
        latest_input_availability=iso(origin),
        latest_input_close=iso(data.available[i]),
        dataset_version=data.version,
        training_cutoff=model["training_cutoff"],
        origin_price=price,
        points=points,
        probabilities=probabilities,
        configuration_id=model["configuration_id"],
        definitions={
            "central_estimate": "Median",
            "interval": "Pointwise 80% prediction intervals",
            "target": "Close of exact hourly candle ending at origin + horizon; origin uses candle ending at origin",
            "zero_return": "Exact zero predicted log-return is a separate probability mass; positive + negative + zero = 1",
        },
        quality_flags=flags,
        status="ready",
        mode=mode,
        input_summary={
            "lookback_days": days,
            "feature_values": dict(zip(data.feature_names, map(float, x))),
            "start": iso(origin - days * 86400),
            "end": iso(origin),
            "candle_count": calendar.lookback_bars(days),
            "lookback_hours": days * 24,
        },
        baseline={
            "name": "No-change median; earlier empirical log-return 10/90% intervals",
            "sample_count": len(returns),
            "latest_target": iso(calendar.horizon_target(earlier[0][-1], data.horizons)),
            "positive_probability": float(np.mean(returns[:, -1] > 0)),
            "points": [
                dict(
                    median=price,
                    lower=float(price * np.exp(bq[0, j])),
                    upper=float(price * np.exp(bq[1, j])),
                )
                for j in range(data.horizons)
            ],
        },
    )
    return validate(f)
