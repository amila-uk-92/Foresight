"""Read-only evidence view of one saved forecast (contract forecast-evidence/1).

Everything here is read from records that already exist: the immutable forecast
pair, its evaluation, the run and job that produced it, and the dataset snapshot
manifest. Nothing is generated, scored or written. Sections that no implemented
component produces are reported as such instead of being filled in:

- "recorded": stored records were found and are returned.
- "empty": the store exists and holds no items for this forecast.
- "not_recorded": this forecast has no such record (e.g. it predates reasoning).
- "not_implemented": no component that would produce the record exists yet.
- "unavailable": the record should exist but could not be read; ``error`` says why.

Numerical forecast data (``numerical``) and source/research evidence
(``sources``, ``reasoning``) are kept in separate sections.
"""

import json

from backend.app.forecasting import contracts, data as market_data
from backend.app.forecasting.estimators import FAMILIES
from backend.app.forecasting.evaluator import AGENT_EVALUATION_STATES
from backend.app.forecasting.specialist import iso, stamp

SCHEMA_VERSION = "forecast-evidence/1"

# Roles from the specification's reasoning table that no code implements yet.
# They are listed so the UI can say "Planned — not implemented", never as if they ran.
PLANNED_ROLES = [
    ("news-macro", "News & Macro analyst", "Extract dated, sourced events and forecast from them"),
    ("bull-researcher", "Bull researcher", "Argue the supporting case from cited evidence"),
    ("bear-researcher", "Bear researcher", "Argue the contradicting case from cited evidence"),
    ("moderator", "Moderator / evidence checker", "Validate citations, reject claims, list conflicts"),
    ("numerical-ensemble", "Multi-specialist numerical coordinator", "Combine several specialists with trained weights"),
    ("reflection", "Reflection / memory", "Propose testable changes from matured errors"),
    ("trader-risk", "Trader and risk engine", "Paper strategy proposals under hard risk limits"),
]

TRADING = {
    "state": "not_enabled",
    "label": "Trading not enabled",
    "reason": "No strategy or risk contract is implemented, so no forecast is trade-eligible.",
}


def _not(state, reason):
    return {"state": state, "reason": reason}


def _pair(store, forecast_id):
    """Return (coordinated, specialist) for either id of a published pair."""
    f = store.get("forecasts", forecast_id)
    if f["role"] == "coordinated":
        try:
            return f, store.get("forecasts", f["specialist_forecast_id"])
        except (KeyError, ValueError):
            return f, None
    with store.connection() as db:
        row = db.execute(
            "SELECT payload FROM forecasts WHERE run_id=? AND origin=? AND model_id=? AND role='coordinated'",
            (f["run_id"], f["origin"], f["model_version"]),
        ).fetchone()
    return (json.loads(row["payload"]) if row else None), f


def _producing_run(store, coordinated):
    """The run that produced this forecast; prediction forecasts are linked from their run's model list."""
    run_id = coordinated["run_id"]
    if not run_id.startswith("prediction-"):
        try:
            return store.get("runs", run_id)
        except ValueError:
            return None
    for run in store.list("runs"):
        models = run.get("models")
        if isinstance(models, list) and any(
            isinstance(m, dict) and m.get("forecast_id") == coordinated["id"] for m in models
        ):
            return run
    return None


def _job(engine, run):
    if not run:
        return _not("not_recorded", "No run record links this forecast to a job.")
    job = next(iter(engine._jobs_for_run(run["id"])), None)
    if not job or not job.get("started_at") or not job.get("finished_at"):
        return _not("not_recorded", "No finished job record for the producing run.")
    seconds = stamp(job["finished_at"]) - stamp(job["started_at"])
    return {
        "state": "recorded",
        "job_id": job["job_id"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "seconds": round(seconds, 3),
        "scope": "Wall-clock time of the whole job that produced this run (training, testing and prediction), not one forecast",
    }


def _outcomes(f, evaluation, coverage_end):
    points = []
    by_target = {p["target"]: p for p in (evaluation or {}).get("points", [])}
    for day, p in enumerate(f["points"], 1):
        e = by_target.get(p["target"], {})
        state = e.get("state", "pending")
        status = "known" if state == "evaluated" else "missing" if state == "unscorable" else "pending"
        points.append(
            {
                "day": day,
                "target": p["target"],
                "status": status,
                "actual_price": e.get("actual_price") if status == "known" else None,
                "reason": (
                    None
                    if status == "known"
                    else "Target hour missing in the dataset"
                    if status == "missing"
                    else "Target is after the last stored candle"
                    if coverage_end and stamp(p["target"]) > stamp(coverage_end)
                    else "Not scored yet at the evaluation clock"
                ),
            }
        )
    counts = {k: sum(p["status"] == k for p in points) for k in ("known", "pending", "missing")}
    return {
        "state": "recorded" if evaluation else "not_recorded",
        "evaluation_state": AGENT_EVALUATION_STATES.get((evaluation or {}).get("state", "pending"), "Pending"),
        "clock": (evaluation or {}).get("clock"),
        "observed_through": coverage_end,
        "counts": counts,
        "points": points,
    }


def _market_sources(f):
    """Dataset snapshot and the archive files behind the look-back window the model read."""
    try:
        data = market_data.MarketData.load(f["dataset_version"], f["symbol"])
    except (ValueError, OSError) as e:
        return {"state": "unavailable", "error": str(e)}, None
    folder = market_data.DATA_DIR / "versions" / f["dataset_version"]
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    files = {x["filename"]: x for x in manifest.get("files", []) if isinstance(x, dict)}
    summary = f.get("input_summary") or {}
    origin = stamp(f["origin"])
    start = stamp(summary["start"]) if summary.get("start") else origin - summary.get("lookback_days", 30) * 86400
    frame = data.frame[(data.times >= start) & (data.times <= origin)]
    used = frame.groupby("source_file", sort=True).size().to_dict() if "source_file" in frame else {}
    records = []
    for name, count in used.items():
        entry = files.get(name, {})
        retrieved = entry.get("downloaded_at")
        records.append(
            {
                "source_id": name,
                "kind": "Exchange price archive (hourly candles)",
                "url": entry.get("url"),
                "checksum_url": entry.get("checksum_url"),
                "sha256": entry.get("actual_sha256"),
                "checksum_verified": bool(entry.get("checksum_verified")),
                "published_at": None,
                "retrieved_at": retrieved,
                "retrieved_after_origin": bool(retrieved and stamp(retrieved) > origin),
                "candles_used": int(count),
                "first_candle_open": iso(float(frame[frame["source_file"] == name]["open_time_unix"].min())),
                "last_candle_close": frame[frame["source_file"] == name]["close_time"].max(),
            }
        )
    # End of the last stored candle: outcomes after this are not in the data yet.
    coverage_end = iso(float(data.times.max())) if len(data.times) else None
    return (
        {
            "state": "recorded" if records else "empty",
            "venue": f.get("market"),
            "symbol": f["symbol"],
            "dataset_version": f["dataset_version"],
            "archive_base": manifest.get("archive_url_base"),
            "window_start": iso(start),
            "window_end": f["origin"],
            "candle_count": int(len(frame)),
            "latest_candle_close": f.get("latest_input_close"),
            "availability_rule": "A candle is usable once its close time has passed; the latest one used closed before the forecast origin.",
            "publication_note": "The exchange archive does not record publication times; retrieval times are when Foresight downloaded the files.",
            "records": records,
        },
        coverage_end,
    )


def forecast_evidence(engine, forecast_id):
    store = engine.store
    coordinated, specialist = _pair(store, forecast_id)
    f = coordinated or specialist
    run = _producing_run(store, f) if coordinated else None
    model = None
    try:
        model = store.get("models", f["model_version"])
    except ValueError:
        pass
    sources, coverage_end = _market_sources(f)
    evaluation = store.evaluation(f["id"])
    registered = sorted(contracts.REGISTRY)
    # A registered numerical news model is not a generative research/debate agent.
    reasoning_agents = []
    weights = (coordinated or {}).get("weights")
    roles = [
        {
            "id": "price-volume",
            "name": "Price & Volume specialist",
            "state": "active" if specialist else "not_recorded",
            "detail": "Produced the numerical forecast from hourly price and volume candles.",
        },
        {
            "id": "coordinator",
            "name": "Coordinator",
            "state": "active" if coordinated else "not_recorded",
            "detail": (coordinated or {}).get("coordination") or "No coordinated record.",
        },
        {"id": "publisher", "name": "Publisher", "state": "active" if coordinated else "not_recorded", "detail": "Saved the immutable forecast pair."},
        {
            "id": "evaluator",
            "name": "Evaluator",
            "state": "active" if evaluation else "pending",
            "detail": "Scores stored outcomes against the no-change baseline." if evaluation else "No outcomes scored yet.",
        },
    ] + [
        {"id": i, "name": n, "state": "planned", "detail": d}
        for i, n, d in PLANNED_ROLES
        if i not in reasoning_agents
    ]
    for role in roles:
        if role["id"] == "news-macro":
            role.update(state="experimental", detail="News collection, bounded classification and numerical forecasting modules exist; this forecast has no linked news input")
    not_impl = "No reasoning or research agent is implemented, so nothing was recorded for any forecast."
    reasoning_state = "not_implemented" if not reasoning_agents else "not_recorded"
    reasoning = {
        "state": reasoning_state,
        "forecast_state": "not_recorded",
        "reason": not_impl if not reasoning_agents else "This forecast has no stored reasoning record.",
        "summary": None,
        "findings": [],
        "arguments": {"bull": [], "bear": [], "counterarguments": []},
        "moderator": {"findings": [], "rejected_claims": [], "unresolved_conflicts": []},
        "agreement": None,
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "forecast_id": f["id"],
        "specialist_forecast_id": (specialist or {}).get("id"),
        "forecast": {
            "symbol": f["symbol"],
            "mode": f.get("mode"),
            "run_id": f["run_id"],
            "producing_run_id": (run or {}).get("id"),
            "origin": f["origin"],
            "generated_at": f["generated_at"],
            "evidence_cutoff": f["latest_input_availability"],
            "latest_input_close": f.get("latest_input_close"),
            "training_cutoff": f["training_cutoff"],
            "origin_price": f["origin_price"],
            "historical_origin": stamp(f["generated_at"]) - stamp(f["origin"]) > 86400,
            "targets": [
                {"day": d, "target": p["target"], "horizon_hours": p["horizon_hours"]}
                for d, p in enumerate(f["points"], 1)
            ],
        },
        "numerical": {
            "state": "recorded",
            "coordination": {
                "state": "recorded" if coordinated else "not_recorded",
                "method": (coordinated or {}).get("coordination"),
                "coordinator_version": (coordinated or {}).get("coordinator_version"),
                "weights": weights,
            },
            "definitions": f.get("definitions"),
            "points": [{k: p[k] for k in ("target", "horizon_hours", "median", "lower", "upper")} for p in f["points"]],
            "probabilities": f.get("probabilities"),
            "baseline": {k: v for k, v in (f.get("baseline") or {}).items() if k != "points"} or None,
            "quality_flags": f.get("quality_flags", []),
        },
        "outcomes": _outcomes(f, evaluation, coverage_end),
        "sources": {
            "market_data": sources,
            "research": _not("not_recorded", "No news evidence recorded for this forecast. News collected later is not retroactively attached."),
        },
        "reasoning": reasoning,
        "agents": roles,
        "versions": {
            "contract_version": f.get("contract_version"),
            "model_version": f["model_version"],
            "model_family": (model or {}).get("family"),
            "model_family_label": FAMILIES.get((model or {}).get("family"), (model or {}).get("family")),
            "model_record": "recorded" if model else "not_recorded",
            "dataset_version": f["dataset_version"],
            "configuration_id": f.get("configuration_id"),
            "coordinator_version": (coordinated or {}).get("coordinator_version"),
            "prompt_version": _not("not_implemented", "No prompts are used."),
            "memory_version": _not("not_implemented", "No memory component exists."),
            "ensemble_version": _not("not_implemented", "Single specialist; no ensemble."),
        },
        "cost_latency": {
            "inference_cost": _not("not_recorded", "Local numerical model; no monetary inference cost is recorded."),
            "forecast_latency": _not("not_recorded", "Per-forecast latency is not recorded."),
            "job": _job(engine, run),
        },
        "run": {
            "state": "recorded" if run else "not_recorded",
            "evaluation_label": (run or {}).get("evaluation_label"),
            "development": (run or {}).get("development"),
        },
        "trading": TRADING,
    }
    if f.get("news_evidence"):
        from backend.app.news.service import NewsService
        news = NewsService(store)
        try:
            link = f["news_evidence"]
            packet = news.records.get("packet", link["packet_id"])
            features = news.records.get("features", link["features_id"])
            classifications = [news.records.get("classification", id) for id in features["classification_ids"]]
            articles = [news.records.get("article", id) for id in packet["article_ids"]]
            result["news_evidence"] = {"state": "recorded", "packet": packet, "features": features, "articles": articles, "classifications": classifications}
            result["sources"]["research"] = {"state": "recorded", "reason": "Saved point-in-time news packet actually used by this forecast"}
            result["agents"][0].update(id=f["specialist_id"], name=f["specialist_id"], detail="Produced this numerical forecast using its saved feature contract")
            if f["specialist_id"] == "news-macro":
                result["agents"] = [r for j, r in enumerate(result["agents"]) if j == 0 or r["id"] != "news-macro"]
            result["versions"]["prompt_version"] = {"state": "recorded", "reason": ", ".join(sorted({c["question_version"] for c in classifications})) or "No classification prompts recorded"}
            result["cost_latency"]["news_extraction"] = {"state": "recorded", "saved_extraction_cost_usd": sum(c.get("cost_usd", 0) for c in classifications), "note": "Stored classification costs may be reused across forecasts; not a new charge per prediction"}
        except ValueError as error:
            result["news_evidence"] = {"state": "unavailable", "error": str(error)}
    return result
