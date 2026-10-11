"""Forecast API: thin adapters over numerical services and SQLite persistence."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from backend.app.jobs import jobs
from backend.app.forecasting.service import Engine, PROMOTION_POLICY
from backend.app.forecasting.specialist import stamp
from backend.app.forecasting.data import MarketData
from backend.app.forecasting.evaluator import aggregate

router = APIRouter(prefix="/api/forecasting", tags=["forecasting"])
engine = Engine()


class TrainRequest(BaseModel):
    mode: Literal["frozen", "adaptive"] = "frozen"
    lookbacks: list[Literal[30, 90, 180]] = Field(
        default_factory=lambda: [30, 90, 180], min_length=1
    )
    alphas: list[float] = Field(
        default_factory=lambda: [1.0, 10.0, 100.0], min_length=1
    )


class TrainPredictRequest(TrainRequest):
    origin: str | None = None


class PredictionRequest(BaseModel):
    model_id: str | None = None
    origin: str | None = None


class EvaluationRequest(BaseModel):
    clock: str


class RetrainRequest(BaseModel):
    model_id: str
    cutoff: str


class ComparisonRequest(BaseModel):
    origin: str | None = None
    # Optional override of the configured family list (FORESIGHT_COMPARISON_FAMILIES).
    families: list[str] | None = None


@router.post("/comparisons")
def compare(req: ComparisonRequest):
    from backend.app.forecasting.comparison import run_comparison, configured_families

    try:
        families = configured_families(req.families)
        return jobs.start(
            "forecasting",
            lambda id: run_comparison(engine, req.origin, id, families),
            config={
                "experiment": "family-comparison",
                "origin": req.origin,
                "families": families,
            },
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/comparisons")
def comparisons():
    return [
        {k: v for k, v in r.items() if k != "models"}
        for r in engine.store.list("runs")
        if r["mode"] == "comparison"
    ]


@router.get("/comparisons/{id}")
def comparison_detail(id: str, horizon: int = 168):
    from backend.app.forecasting.comparison import evidence

    try:
        return evidence(engine, id, horizon)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/state")
def state():
    store = engine.store
    metadata = engine.models()
    forecasts = [
        {
            k: f[k]
            for k in (
                "id",
                "origin",
                "model_version",
                "run_id",
                "mode",
                "role",
                "generated_at",
            )
        }
        for f in store.list("forecasts")
        if f["role"] == "coordinated"
    ]
    return dict(
        models=metadata,
        selected_model=engine.setting("selected_model"),
        runs=engine.runs(),
        forecasts=forecasts,
        job=jobs.get(kind="forecasting"),
        decisions=store.list("decisions"),
        promotion_policy=PROMOTION_POLICY,
        periods={
            k: {"start": v["start"].isoformat(), "end": v["end"].isoformat()}
            for k, v in engine.market.splits.items()
        },
    )


@router.post("/train")
def train(req: TrainRequest):
    config = req.model_dump()
    if any(a <= 0 or not __import__("math").isfinite(a) for a in req.alphas):
        raise HTTPException(422, "Positive finite ridge penalties required")
    try:
        return jobs.start(
            "forecasting", lambda id: engine.train_backtest(config, id), config=config
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/train-and-predict")
def train_and_predict(req: TrainPredictRequest):
    config = req.model_dump(exclude={"origin"})
    if any(a <= 0 or not __import__("math").isfinite(a) for a in req.alphas):
        raise HTTPException(422, "Positive finite ridge penalties required")
    try:
        return jobs.start(
            "forecasting",
            lambda id: engine.train_and_predict(config, id, req.origin),
            config=req.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/predict")
def predict(req: PredictionRequest):
    def work(id):
        jobs.update(
            id,
            current_step="Predicting and publishing",
            agents={
                "specialist": "Predicting",
                "coordinator": "Validating",
                "publisher": "Saving",
                "evaluator": "Pending",
            },
        )
        f = engine.predict(req.origin, req.model_id, lambda: jobs.check(id))
        jobs.update(
            id,
            agents={
                "specialist": "Ready",
                "coordinator": "Complete",
                "publisher": "Saved",
                "evaluator": "Pending",
            },
        )
        return {"forecast_id": f["id"], "model_id": f["model_version"]}

    try:
        return jobs.start("forecasting", work, config=req.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/forecasts")
def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    run_id: str | None = None,
    mode: Literal["frozen", "adaptive", "prediction"] | None = None,
    model_id: str | None = None,
):
    return engine.history(page, page_size, run_id, mode, model_id)


@router.get("/forecasts/{id}")
def detail(id: str, history_days: int = Query(30)):
    try:
        result = engine.detail(id, history_days)
        result["model"] = {k: v for k, v in result["model"].items() if k not in ("parameters", "residuals")}
        return result
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e)) from e


@router.get("/forecasts/{id}/agents")
def forecast_agents(id: str):
    try:
        return engine.agent_status(forecast_id=id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/forecasts/{id}/evidence")
def forecast_evidence(id: str):
    """Read-only evidence view (schema forecast-evidence/1) built from stored records only."""
    from backend.app.forecasting.evidence import forecast_evidence as build

    try:
        return build(engine, id)
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e)) from e


@router.post("/forecasts/{id}/evaluate")
def evaluate(id: str, req: EvaluationRequest):
    try:
        return engine.evaluate_at(id, req.clock)
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 400, str(e)) from e


@router.get("/models")
def models():
    return engine.models()


@router.get("/models/{id}")
def model(id: str):
    try:
        return next(m for m in engine.models() if m["id"] == id)
    except StopIteration:
        raise HTTPException(404, "Model not found")


@router.get("/runs")
def runs():
    return engine.runs()


@router.get("/runs/{id}")
def run(id: str):
    try:
        return engine.store.get("runs", id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/runs/{id}/origins")
def run_origins(id: str):
    try:
        return engine.run_origins(id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/runs/{id}/scores")
def run_scores(id: str, model_id: str | None = None):
    try:
        return engine.run_scores(id, model_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/runs/{id}/agents")
def run_agents(id: str):
    try:
        engine.store.get("runs", id)
        return engine.agent_status(run_id=id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/agents")
def agents():
    return engine.agent_status()


@router.get("/jobs/{id}")
def job(id: str):
    result = jobs.get(id)
    if not result or result.get("kind") != "forecasting":
        raise HTTPException(404, "Job not found")
    return result


@router.get("/runs/{id}/metrics")
def metrics(id: str, model_id: str | None = None):
    try:
        run = engine.store.get("runs", id)
        result = aggregate(engine.store, id, model_id=model_id)
        result["mode"] = run["mode"]
        result["specialist"] = aggregate(
            engine.store, id, "specialist", model_id=model_id
        )
        # Separate specialist metrics are genuinely calculated from their own records.
        specialist = []
        for f in engine.store.list("forecasts", id):
            specialist.append(engine.store.evaluation(f["specialist_forecast_id"]))
        result["specialist_scored_count"] = sum(
            e["scored_count"] for e in specialist if e
        )
        result["coordinated_scored_count"] = sum(
            (engine.store.evaluation(f["id"]) or {}).get("scored_count", 0)
            for f in engine.store.list("forecasts", id)
        )
        return result
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/models/{id}/select")
def select(id: str):
    try:
        return engine.rollback(id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/retrain")
def retrain(req: RetrainRequest):
    try:
        return jobs.start(
            "forecasting",
            lambda id: engine.retrain(req.model_id, req.cutoff, id),
            config=req.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/jobs/{id}/cancel")
def cancel(id: str):
    try:
        return jobs.cancel(id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/forecasts/{id}/inputs")
def inputs(
    id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)
):
    try:
        f = engine.store.get("forecasts", id)
        data = MarketData.load(f["dataset_version"], f["symbol"])
        origin = stamp(f["origin"])
        days = f["input_summary"]["lookback_days"]
        frame = data.frame[
            (data.times >= origin - days * 86400) & (data.times <= origin)
        ]
        cols = [
            "open_time",
            "close_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
            "source_file",
        ]
        return {
            "total": len(frame),
            "page": page,
            "rows": frame.iloc[(page - 1) * page_size : page * page_size][cols].to_dict(
                orient="records"
            ),
        }
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
