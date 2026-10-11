"""Thin adapters for durable news workflows. Mutations never run on navigation."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from backend.app.jobs import jobs
from backend.app.news.service import NewsService
from backend.app.news.contracts import ImportRequest, PacketRequest, ClassifyRequest, LabelRequest, ForecastExperimentRequest
from backend.app.forecasting.data import MarketData

router = APIRouter(prefix="/api/news", tags=["news"])
service = NewsService(jobs.store, jobs)


def call(fn):
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def start(kind, symbol, config, work):
    try:
        return jobs.start(kind, lambda id: work(lambda: jobs.check(id), lambda step, pct, **meta: jobs.update(id, current_step=step, progress_percentage=pct, **meta)), symbol=symbol, config=config)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/status")
def status():
    return service.status()


@router.get("/coverage")
def coverage(symbol: str = "BTCUSDT"):
    return call(lambda: service.coverage(symbol))


@router.get("/records/{kind}")
def records(kind: str, symbol: str | None = None, provider: str | None = None, q: str | None = Query(None, max_length=200), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    if kind not in {"article", "packet", "classification", "classification_experiment", "classification_evaluation", "forecast_manifest", "forecast_checkpoint", "forecast_experiment", "provider_response", "label"}:
        raise HTTPException(404, "Unknown news record type")
    rows = service.records.list(kind)
    if symbol:
        rows = [r for r in rows if r.get("symbol", symbol) == symbol]
    if provider:
        rows = [r for r in rows if r.get("provider") == provider]
    if q:
        rows = [r for r in rows if q.lower() in (r.get("headline", "") + " " + r.get("text", "")).lower()]
    return {"total": len(rows), "page": page, "items": rows[(page - 1) * page_size:page * page_size]}


@router.get("/records/{kind}/{id}")
def record(kind: str, id: str):
    if kind not in {"article", "packet", "features", "classification", "classification_experiment", "classification_evaluation", "forecast_manifest", "forecast_experiment", "forecast_checkpoint", "incumbent_snapshot", "provider_response", "label"}:
        raise HTTPException(404, "Unknown news record type")
    try:
        return service.records.get(kind, id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/import")
def import_news(req: ImportRequest):
    if sum(len(a.text) + len(a.headline) for a in req.articles) > 2_000_000:
        raise HTTPException(413, "Import at most 2MB per batch")
    return start("news-import", "NEWS", {"provider": req.provider, "count": len(req.articles)}, lambda check, progress: service.ingest(req.articles, req.provider, check, progress))


class CollectionRequest(BaseModel):
    source: str = "federal-reserve"


@router.post("/collect")
def collect(req: CollectionRequest):
    return start("news-collect", "NEWS", req.model_dump(), lambda check, progress: service.collect(req.source, check, progress))


@router.post("/packets")
def packet(req: PacketRequest):
    return call(lambda: service.packet(**req.model_dump()))


@router.post("/classifications/preview")
def preview(req: ClassifyRequest):
    return call(lambda: service.preview(req.packet_id, req.classifier, req.max_articles))


@router.post("/classifications")
def classify(req: ClassifyRequest):
    return start("news-classify", "NEWS", req.model_dump(), lambda check, progress: service.classify(**req.model_dump(), check=check, progress=progress))


@router.post("/labels")
def label(req: LabelRequest):
    return call(lambda: service.label(req.model_dump()))


class EvaluationRequest(BaseModel):
    packet_id: str
    classifier: Literal["jev", "openai"] = "jev"


@router.post("/classification-evaluations")
def evaluation(req: EvaluationRequest):
    return call(lambda: service.classification_evaluation(req.packet_id, req.classifier))


@router.get("/jobs/{id}")
def job(id: str):
    result = jobs.get(id)
    if not result or not result["kind"].startswith("news-"):
        raise HTTPException(404, "News job not found")
    return result


@router.get("/latest-job")
def latest_job():
    with jobs.store.connection() as db:
        row = db.execute("SELECT payload FROM jobs WHERE kind LIKE 'news-%' ORDER BY created DESC LIMIT 1").fetchone()
    return __import__("json").loads(row["payload"]) if row else None


@router.get("/jobs/{id}/retained")
def retained(id: str):
    j = job(id)
    manifest = j.get("manifest_id")
    return {"job_id": id, "manifest_id": manifest, "state": j["status"], "checkpoints": [c for c in service.records.list("forecast_checkpoint") if c["manifest_id"] == manifest], "note": "Retained outputs are partial research artifacts, not a completed comparison"}


@router.post("/jobs/{id}/cancel")
def cancel(id: str):
    job(id)
    return call(lambda: jobs.cancel(id))


@router.post("/forecast-experiments/preview")
def forecast_preview(req: ForecastExperimentRequest):
    def work():
        from backend.app.news.forecasting import VARIANTS, GATES
        from backend.app.markets import get_market
        market = get_market(req.symbol)
        return {"configuration": req.model_dump(), "variants": list(VARIANTS), "promotion_policy": GATES,
                "splits": market.summary()["splits"], "coverage": service.coverage(req.symbol), "article_count": len(service.records.list("article")),
                "external_ai_calls": 0, "notice": "Uses saved classifications only; no promotion. Missing chronological coverage blocks news variants."}
    return call(work)


@router.post("/forecast-experiments")
def forecast_experiment(req: ForecastExperimentRequest):
    def work(check, progress):
        from backend.app.news.forecasting import experiment
        return experiment(service, MarketData.load(symbol=req.symbol), req.model_dump(), check, progress)
    return start("news-forecast", req.symbol, req.model_dump(), work)


@router.get("/forecast-experiments/{id}/view")
def experiment_view(id: str, origin_index: int = Query(-1, ge=-1), horizon: int = Query(7, ge=1, le=7)):
    """One snapshot read, one common origin index; never overlay unrelated dates."""
    def work():
        run = service.records.get("forecast_experiment", id)
        saved = {v: [service.store.get("forecasts", fid) for fid in x["forecast_ids"]] for v, x in run["variants"].items()}
        origins = sorted({f["origin"] for rows in saved.values() for f in rows})
        if origin_index >= len(origins) and origins:
            raise ValueError("Origin index outside saved experiment")
        focus = origins[origin_index] if origins else None
        if not origins:
            return {"origins": [], "details": {}, "series": {}}
        first = next(f for rows in saved.values() for f in rows)
        data = MarketData.load(first["dataset_version"], first["symbol"])
        from backend.app.forecasting.specialist import stamp
        actual = lambda target: float(data.close[data.indices[int(stamp(target))]]) if int(stamp(target)) in data.indices else None
        details, series = {}, {}
        for variant, rows in saved.items():
            series[variant] = []
            for f in rows:
                p = f["points"][horizon - 1]
                series[variant].append({"origin": f["origin"], "origin_index": origins.index(f["origin"]), **p, "actual": actual(p["target"])})
                if f["origin"] == focus:
                    details[variant] = {"forecast": f, "actual": [{"time": f["origin"], "value": f["origin_price"]}] + [{"time": p["target"], "value": actual(p["target"])} for p in f["points"] if actual(p["target"]) is not None]}
        return {"origins": origins, "details": details, "series": series, "origin": focus, "quote_currency": first["quote_currency"]}
    return call(work)


class NewsPredictionRequest(BaseModel):
    model_id: str
    origin: str | None = None


@router.post("/predict")
def predict(req: NewsPredictionRequest):
    from backend.app.news.forecasting import predict_saved
    return call(lambda: predict_saved(service, req.model_id, req.origin))


@router.get("/models/{id}")
def model_metadata(id: str):
    def work():
        m = service.store.get("models", id)
        if not m.get("news_experiment"):
            raise ValueError("Not a news experiment model")
        return {k: v for k, v in m.items() if k not in {"parameters", "residuals"}}
    return call(work)


@router.get("/forecasts/{id}")
def forecast(id: str):
    def work():
        f = service.store.get("forecasts", id)
        if not f.get("research_variant"):
            raise ValueError("Not a news experiment forecast")
        data = MarketData.load(f["dataset_version"], f["symbol"])
        return {"forecast": f, "evaluation": evaluate_readonly(data, f), "model": service.store.get("models", f["model_version"]),
                "actual": [{"time": p["target"], "value": float(data.close[data.indices[int(__import__('datetime').datetime.fromisoformat(p["target"]).timestamp())]])} for p in f["points"] if int(__import__('datetime').datetime.fromisoformat(p["target"]).timestamp()) in data.indices]}
    return call(work)


def evaluate_readonly(data, f):
    from backend.app.forecasting.evaluator import evaluate
    return evaluate(data, f, float(data.times[-1]))
