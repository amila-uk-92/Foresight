"""FastAPI backend application for Foresight."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
from backend.app.jobs import jobs
from backend.app.api.forecasts import router as forecasting_router


@asynccontextmanager
async def lifespan(app):
    jobs.recover()
    yield


from backend.app.api.datasets import router as datasets_router
from backend.app.api.import_jobs import router as import_router
from backend.app.api.markets import router as markets_router
from backend.app.api.news import router as news_router

app = FastAPI(
    lifespan=lifespan,
    title="Foresight",
    description="Local BTC price-volume forecasting and historical dataset explorer",
    version="1.0.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(datasets_router)
app.include_router(import_router)
app.include_router(forecasting_router)
app.include_router(markets_router)
app.include_router(news_router)


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "Foresight Backend", "version": "1.0.0"}


# Serve frontend build if dist folder exists
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend"
    )
