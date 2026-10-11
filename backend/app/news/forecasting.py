"""Frozen numerical news experiments. Never promote or replace an incumbent."""
import uuid
import json
import time
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pandas as pd
from backend.app.storage import now, atomic_json
from backend.app.news.store import digest
from backend.app.news.service import window_start
from backend.app.forecasting import specialist as numerical
from backend.app.forecasting.contracts import register_specialist_market, coordinate
from backend.app.forecasting.publisher import Publisher
from backend.app.forecasting.evaluator import evaluate

VARIANTS = {"price_only": (None, False), "price_keywords": ("keywords", False), "price_jev": ("jev", False), "news_jev": ("jev", True), "price_openai": ("openai", False), "news_openai": ("openai", True)}
GATES = {"day7_min_improvement_fraction": 0.01, "paired_95pct_upper_below_zero": True,
         "other_horizon_max_regression_fraction": 0.02, "minimum_complete_origins": 60,
         "coverage_80pct_bounds": [0.7, 0.9], "interval_and_brier_no_worse": True,
         "untouched_forward_confirmation_required": True}


def implementation_revision():
    return digest({p.name: p.read_text() for p in [Path(__file__), Path(__file__).with_name("service.py"), Path(__file__).with_name("classifiers.py"), Path(__file__).with_name("openai_classifier.py"), Path(numerical.__file__)]})


class FeatureData:
    """Existing market interface with immutable, causally aligned research features."""
    def __init__(self, data, variant, rows, names):
        self.base, self.variant, self.rows = data, variant, rows
        classifier, standalone = VARIANTS[variant]
        self.market = replace(data.market, specialist="news-macro" if standalone else "price-volume-news" if classifier else data.market.specialist)
        register_specialist_market(self.market.specialist, self.market.symbol)
        self.calendar, self.horizons, self.version = data.calendar, data.horizons, data.version
        self.frame, self.times, self.close, self.available, self.indices, self.quality = data.frame, data.times, data.close, data.available, data.indices, data.quality
        self.end = data.end
        self.feature_names = (names if standalone else data.feature_names + names) if classifier else data.feature_names
        self.feature_set = SimpleNamespace(name=variant + "/1", names=self.feature_names, definitions={k: "Numerical as-of " + k for k in self.feature_names})

    def input(self, origin, days):
        i, x = self.base.input(origin, days)
        classifier, standalone = VARIANTS[self.variant]
        if classifier:
            row = self.rows.get(int(origin), {}).get(classifier)
            if not row or not row["eligible"]:
                raise ValueError("Insufficient point-in-time news coverage or classifications at origin")
            x = np.array(row["values"]) if standalone else np.r_[x, row["values"]]
        return i, x

    def examples(self, days, start, end):
        ts, xs, ys, prices = self.base.examples(days, start, end)
        out = []
        for i, t in enumerate(ts):
            try:
                _, x = self.input(t, days)
                out.append((i, x))
            except ValueError:
                pass
        idx = [i for i, _ in out]
        return ts[idx], np.array([x for _, x in out]).reshape((-1, len(self.feature_names))), ys[idx], prices[idx]


def paired_interval(values, block=7):
    if len(values) < 14:
        return None
    rng = np.random.default_rng(20261011)
    a = np.array(values)
    sampled = []
    for _ in range(400):
        starts = rng.integers(len(a), size=(len(a) + block - 1) // block)
        indices = np.concatenate([(s + np.arange(block)) % len(a) for s in starts])[:len(a)]
        sampled.append(float(a[indices].mean()))
    return np.quantile(sampled, [0.025, 0.975]).tolist()


def metrics(data, forecasts, evaluations):
    horizons = []
    for step in range(data.horizons):
        rows = [e["points"][step] for e in evaluations if e["points"][step]["state"] == "evaluated"]
        avg = lambda key: float(np.mean([r[key] for r in rows])) if rows else None
        horizons.append({"step": step + 1, "horizon_hours": data.calendar.horizon_hours(step + 1), "sample_count": len(rows),
            "mae": avg("absolute_price_error"), "return_error_percentage_points": avg("absolute_return_error_percentage_points"),
            "coverage": avg("interval_coverage"), "width": avg("interval_width"), "interval_score": avg("interval_score"),
            "baseline_mae": float(np.mean([r["baseline"]["absolute_price_error"] for r in rows])) if rows else None,
            "brier": avg("brier_score") if step == 6 else None,
            "direction_accuracy": avg("direction_accuracy") if step == 6 else None,
            "baseline_brier": float(np.mean([r["baseline_brier_score"] for r in rows])) if step == 6 and rows else None})
    week = [(f, e["points"][-1]) for f, e in zip(forecasts, evaluations) if e["points"][-1]["state"] == "evaluated"]
    bins = []
    if len(week) >= 30:
        for lo in np.arange(0, 1, .2):
            selected = [(f, e) for f, e in week if lo <= f["probabilities"]["positive"] < lo + .2 or lo > .7 and f["probabilities"]["positive"] == 1]
            bins.append({"lower": float(lo), "upper": float(lo + .2), "count": len(selected),
                         "predicted": float(np.mean([f["probabilities"]["positive"] for f, _ in selected])) if selected else None,
                         "observed": float(np.mean([e["positive_outcome"] for _, e in selected])) if selected else None})
    return {"horizons": horizons, "all_horizon_mae": float(np.mean([h["mae"] for h in horizons if h["mae"] is not None])) if any(h["mae"] is not None for h in horizons) else None,
            "probability_calibration": bins}


def train_model(data, service, variant, features, names, config, check, progress):
    started = time.perf_counter()
    config = {**config, "implementation_revision": implementation_revision()}
    wrapped = FeatureData(data, variant, features, names)
    train = data.market.splits["training"]
    val = data.market.splits["validation"]
    mid = (pd.Timestamp(val["start"]) + pd.DateOffset(months=max(1, val["duration_months"] // 2))).timestamp()
    fitting = wrapped.examples(config["lookback_days"], train["start"].timestamp(), train["end"].timestamp())
    selection = wrapped.examples(config["lookback_days"], val["start"].timestamp(), mid)
    calibration = wrapped.examples(config["lookback_days"], mid, val["end"].timestamp())
    if min(len(x[0]) for x in (fitting, selection, calibration)) < config["minimum_origins"]:
        raise ValueError("Insufficient chronological training/selection/calibration news origins; minimum " + str(config["minimum_origins"]))
    candidates = []
    for alpha in (1., 10., 100.):
        check()
        parameters = numerical.fit(fitting[1], fitting[2], alpha)
        pred = numerical.raw(parameters, selection[1])
        error = float(np.mean(np.abs(selection[3] * (np.exp(pred[:, -1]) - np.exp(selection[2][:, -1])))))
        candidates.append((error, alpha, parameters))
    error, alpha, parameters = min(candidates, key=lambda x: x[0])
    residuals = calibration[2] - numerical.raw(parameters, calibration[1])
    id = "news-model-" + uuid.uuid4().hex[:12]
    model = {"id": id, "created_at": now(), "contract_version": "1.0", "specialist_id": wrapped.market.specialist,
             "symbol": data.market.symbol, "news_experiment": True, "feature_set": wrapped.feature_set.name,
             "family": "direct-ridge-log-return", "features": wrapped.feature_names, "feature_definitions": wrapped.feature_set.definitions,
             "dataset_version": data.version, "training_cutoff": numerical.iso(val["end"].timestamp()),
             "fitting_period": {"start": train["start"].isoformat(), "end_exclusive": train["end"].isoformat()},
             "selection_period": {"start": val["start"].isoformat(), "end_exclusive": numerical.iso(mid)},
             "calibration_period": {"start": numerical.iso(mid), "end_exclusive": val["end"].isoformat()},
             "counts": {k: len(v[0]) for k, v in zip(("fitting", "selection", "calibration"), (fitting, selection, calibration))},
             "configuration": {**config, "variant": variant, "alpha": alpha}, "parameters": parameters, "residuals": residuals.tolist(),
             "selection_day7_mae": error, "candidate_selection": [{"alpha": a, "day7_mae": e} for e, a, _ in candidates],
             "development": True, "configuration_id": digest({**config, "variant": variant, "alpha": alpha}),
             "feature_manifest": {str(t): r[VARIANTS[variant][0]]["id"] for t, r in features.items() if t < val["end"].timestamp() and VARIANTS[variant][0] in r} if VARIANTS[variant][0] else {},
             "probability_method": "Chronological residual return distribution; not article confidence",
             "training_duration_seconds": time.perf_counter() - started,
             "interval_method": "Pointwise chronological residual 10th/90th quantiles"}
    path = service.records.root / "models" / (id + ".json")
    model["artifact_path"] = str(path)
    model["artifact_sha256"] = digest({k: v for k, v in model.items() if k not in {"artifact_path", "artifact_sha256"}})
    atomic_json(path, model)
    service.store.put("models", model, immutable=True)
    progress("Trained " + variant, 55)
    return model, wrapped


def experiment(service, data, config, check=lambda: None, progress=lambda *a, **kw: None):
    from backend.app.forecasting.service import Engine
    id = "news-run-" + uuid.uuid4().hex
    snapshot = sorted(a["id"] for a in service.records.list("article"))
    incumbent_id = Engine(service.store, market=data.market.symbol).setting("selected_model")
    incumbent_snapshot = None
    if incumbent_id:
        # A legacy price training run may replace its predecessor later. Keep
        # this experiment's reference outputs independently immutable.
        reference_model = service.store.get("models", incumbent_id)
        with service.store.connection() as db:
            existing = db.execute("SELECT payload FROM forecasts WHERE model_id=? AND role='coordinated'", (incumbent_id,)).fetchall()
        incumbent_snapshot = service.records.put("incumbent_snapshot", {"symbol": data.market.symbol, "model": reference_model, "forecasts": [json.loads(r["payload"]) for r in existing], "notice": "Frozen saved reference outputs; not a retrained or promoted model"})
    config = {**config, "dataset_version": data.version, "article_snapshot": snapshot, "promotion_policy": GATES,
              "implementation_revision": implementation_revision(),
              "incumbent_model_id": incumbent_id,
              "incumbent_snapshot_id": incumbent_snapshot["id"] if incumbent_snapshot else None,
              "cadence": data.calendar.kind, "variants": list(VARIANTS), "candidate_alphas": [1., 10., 100.], "mode": "frozen",
              "evaluation_label": "Historical development; already inspected outcomes; never untouched confirmation"}
    manifest = service.records.put("forecast_manifest", {"id": id, "schema_version": "news-forecast-manifest/1", **config})
    progress("Declared news experiment", 0, manifest_id=id)
    rows, names = {}, None
    origin_times = data.calendar.origins(data.market.splits["training"]["start"].timestamp(), data.end + 1)
    for j, t in enumerate(origin_times):
        check()
        packet = service.packet(data.market.symbol, numerical.iso(t), config["evidence_lookback_days"], config["policy"], snapshot)
        features = {name: service.features(packet, name) for name in ("keywords", "jev", "openai")}
        rows[int(t)] = features
        names = features["keywords"]["names"]
        if j % 50 == 0:
            progress("Preparing origin-aligned news features", 40 * (j + 1) / max(1, len(origin_times)))
    variants, errors = {}, {}
    test = data.market.splits["final_test"]
    intended = data.calendar.origins(test["start"].timestamp(), test["end"].timestamp())
    for variant in VARIANTS:
        check()
        try:
            model, wrapped = train_model(data, service, variant, rows, names or [], config, check, progress)
            service.records.put("forecast_checkpoint", {"manifest_id": id, "symbol": data.market.symbol, "variant": variant, "model_id": model["id"], "state": "trained", "forecast_id": None})
            forecasts, scores, failed = [], [], []
            for t in intended:
                check()
                try:
                    f = publish(service, wrapped, model, t, id)
                    e = evaluate(data, f, float(data.times[-1]))
                    service.store.evaluation(f["id"], e)
                    service.store.evaluation(f["specialist_forecast_id"], {**e, "forecast_id": f["specialist_forecast_id"]})
                    forecasts.append(f)
                    scores.append(e)
                    service.records.put("forecast_checkpoint", {"manifest_id": id, "symbol": data.market.symbol, "variant": variant, "model_id": model["id"], "state": "forecast_saved", "forecast_id": f["id"], "origin": f["origin"]})
                except ValueError as error:
                    failed.append({"origin": numerical.iso(t), "reason": str(error)})
            variants[variant] = {"model_id": model["id"], "forecast_ids": [f["id"] for f in forecasts], "unavailable": failed,
                                 "full_origin_metrics": metrics(data, forecasts, scores), "configuration": model["configuration"],
                                 "training_duration_seconds": model["training_duration_seconds"],
                                 "forecast_duration_seconds": sum(f.get("numerical_duration_seconds", 0) for f in forecasts),
                                 "external_ai_calls_during_training_or_prediction": 0}
        except ValueError as e:
            errors[variant] = str(e)
    complete = {v: {service.store.get("forecasts", fid)["origin"]: fid for fid in x["forecast_ids"] if service.store.evaluation(fid)["scored_count"] == data.horizons} for v, x in variants.items()}
    common = sorted(set.intersection(*(set(x) for x in complete.values()))) if len(complete) > 1 else []
    incumbent = {}
    if incumbent_id:
        incumbent_model = incumbent_snapshot["model"]
        if numerical.stamp(incumbent_model["training_cutoff"]) <= test["start"].timestamp():
            incumbent = {f["origin"]: f for f in incumbent_snapshot["forecasts"] if f["dataset_version"] == data.version and test["start"].timestamp() <= numerical.stamp(f["origin"]) < test["end"].timestamp() and evaluate(data, f, data.end)["scored_count"] == data.horizons}
    if incumbent:
        common = sorted(set(common) & set(incumbent))
    incumbent_fs = [incumbent[t] for t in common] if incumbent else []
    incumbent_es = [evaluate(data, f, data.end) for f in incumbent_fs]
    incumbent_metrics = metrics(data, incumbent_fs, incumbent_es)
    for variant, values in variants.items():
        fs = [service.store.get("forecasts", complete[variant][t]) for t in common]
        es = [service.store.evaluation(f["id"]) for f in fs]
        values["matched_metrics"] = metrics(data, fs, es)
        if variant != "price_only" and "price_only" in complete and common:
            error = [e["points"][-1]["absolute_price_error"] for e in es]
            ref = [service.store.evaluation(complete["price_only"][t])["points"][-1]["absolute_price_error"] for t in common]
            values["paired_day7_mae_difference"] = float(np.mean(np.array(error) - ref))
            values["paired_95pct_block_interval"] = paired_interval(np.array(error) - ref, data.horizons)
            signed = [f["points"][-1]["median"] - e["points"][-1]["actual_price"] for f, e in zip(fs, es)]
            reference_signed = [service.store.get("forecasts", complete["price_only"][t])["points"][-1]["median"] - service.store.evaluation(complete["price_only"][t])["points"][-1]["actual_price"] for t in common]
            values["residual_correlation_with_price_only"] = float(np.corrcoef(signed, reference_signed)[0, 1]) if np.std(signed) and np.std(reference_signed) else None
        if variant != "price_only" and incumbent_fs:
            differences = [e["points"][-1]["absolute_price_error"] - old["points"][-1]["absolute_price_error"] for e, old in zip(es, incumbent_es)]
            interval = paired_interval(differences, data.horizons)
            values["paired_95pct_difference_vs_incumbent"] = interval
            current, reference = values["matched_metrics"]["horizons"], incumbent_metrics["horizons"]
            gates = {
                "minimum_complete_origins": len(common) >= GATES["minimum_complete_origins"],
                "day7_improves_incumbent_and_no_change": current[-1]["mae"] <= .99 * min(reference[-1]["mae"], current[-1]["baseline_mae"]),
                "paired_interval_below_zero": bool(interval and interval[1] < 0),
                "other_horizons_no_more_than_2pct_worse": all(a["mae"] <= 1.02 * b["mae"] for a, b in zip(current[:-1],reference[:-1])),
                "coverage_70_to_90pct": all(.7 <= h["coverage"] <= .9 for h in current),
                "proper_interval_score_no_worse": all(a["interval_score"] <= b["interval_score"] for a, b in zip(current,reference)),
                "brier_no_worse": current[-1]["brier"] <= reference[-1]["brier"],
                "untouched_forward_confirmation": False,
            }
            values["promotion_gate_results"] = gates
        else:
            values["promotion_gate_results"] = {"state": "insufficient_matched_evidence"}
    result = {"id": id, "schema_version": "news-forecast-experiment/1", "manifest_id": manifest["id"], "symbol": data.market.symbol,
              "state": "partial" if errors or any(x["unavailable"] for x in variants.values()) else "complete", "variants": variants, "errors": errors, "intended_origins": len(intended),
              "unavailable_variant_origins": {v: len(intended) for v in errors}, "incumbent": {"model_id": incumbent_id, "eligible_saved_origins": len(incumbent), "matched_metrics": incumbent_metrics},
              "matched_complete_origins": common, "promotion": {"state": "not_promoted", "reason": "Experimental; untouched forward confirmation and all predeclared gates required; incumbent unchanged"},
              "evaluation_label": config["evaluation_label"], "trading": "not_enabled"}
    return service.records.put("forecast_experiment", result)


def publish(service, wrapped, model, origin, run_id):
    started = time.perf_counter()
    f = numerical.predict(wrapped, model, origin, run_id, "news-development")
    f["numerical_duration_seconds"] = time.perf_counter() - started
    f["quality_flags"].append("Experimental news pipeline; historical LLM memorization and source attestation limitations")
    classifier = VARIANTS[wrapped.variant][0]
    if classifier:
        feature = wrapped.rows[int(origin)][classifier]
        f["news_evidence"] = {"packet_id": feature["packet_id"], "features_id": feature["id"], "classifier": classifier, "variant": wrapped.variant}
    f["research_variant"] = wrapped.variant
    return Publisher(service.store).publish(f, coordinate(f))


def predict_saved(service, model_id, origin=None):
    from backend.app.forecasting.data import MarketData
    model = service.store.get("models", model_id)
    if not model.get("news_experiment"):
        raise ValueError("Select a saved news experiment model")
    check_model = {k: v for k, v in model.items() if k not in {"artifact_path", "artifact_sha256"}}
    if digest(check_model) != model["artifact_sha256"]:
        raise ValueError("Model artifact integrity mismatch")
    try:
        artifact = json.loads(Path(model["artifact_path"]).read_text())
    except (OSError, ValueError) as error:
        raise ValueError("Saved model artifact unavailable") from error
    if artifact != model:
        raise ValueError("Saved model artifact integrity mismatch")
    if model["configuration"].get("implementation_revision") != implementation_revision():
        raise ValueError("News implementation changed; create a new declared experiment for prediction")
    data = MarketData.load(model["dataset_version"], model["symbol"])
    t = numerical.stamp(origin) if origin else int(data.times[-1])
    if not data.calendar.is_origin(t):
        raise ValueError("Choose a scheduled completed market origin")
    variant = model["configuration"]["variant"]
    classifier = VARIANTS[variant][0]
    rows, names = {}, []
    if classifier:
        config = model["configuration"]
        # Saved prediction needs the same earlier, matured baseline sample as
        # replay. Prepare only past-origin cached features, never call an AI here.
        for previous in data.calendar.origins(t - config["lookback_days"] * 86400, t + 1):
            packet = service.packet(model["symbol"], numerical.iso(previous), config["evidence_lookback_days"], config["policy"])
            feature = service.features(packet, classifier)
            rows[int(previous)] = {classifier: feature}
        feature = rows[int(t)][classifier]
        names = feature["names"]
        if feature["classifier_identity"] != next((service.records.get("features", fid)["classifier_identity"] for fid in model["feature_manifest"].values()), feature["classifier_identity"]):
            raise ValueError("Classifier/profile version changed; use a new declared experiment")
    wrapped = FeatureData(data, variant, rows, names)
    return publish(service, wrapped, model, t, "news-prediction-" + model_id)
