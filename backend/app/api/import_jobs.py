"""Import HTTP adapter. Durable jobs share the same worker services as CLI."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.app.markets import get_market, primary_market, source_for
from backend.app.processor import DatasetProcessor
from backend.app.jobs import jobs, Cancelled

router = APIRouter(prefix="/api/import", tags=["import"])


class StartImportRequest(BaseModel):
    symbol: str = primary_market().symbol
    import_both: bool = False


def import_symbols(symbol, import_both=False):
    """``import_both`` means the primary market plus its cross-market partner."""
    if not import_both:
        return [symbol]
    primary = primary_market()
    return [primary.symbol] + ([primary.cross_market] if primary.cross_market else [])


def import_pipeline(id, symbol, import_both=False):
    symbols = import_symbols(symbol, import_both)
    for symbol_index, sym in enumerate(symbols):
        jobs.check(id)
        market = get_market(sym)
        downloader = source_for(market).downloader(market)

        def download_progress(info):
            try:
                jobs.check(id)
            except Cancelled:
                downloader.request_cancellation()
            jobs.update(
                id,
                status="downloading",
                current_step=f'Downloading {sym}: {info["current_file"]}',
                progress_percentage=(100 * symbol_index + info["percent"] * 0.5)
                / len(symbols),
                completed_files=symbol_index * info["total_files"]
                + info["completed_files"],
                total_files=info["total_files"] * len(symbols),
            )

        async def download():
            task = asyncio.create_task(
                downloader.download_all(progress_callback=download_progress)
            )
            while not task.done():
                if jobs.events[id].is_set():
                    downloader.request_cancellation()
                await asyncio.sleep(0.2)
            return await task

        result = asyncio.run(download())
        jobs.check(id)
        if result["verified"] != result["total"]:
            raise ValueError(
                f"{sym}: not all required archives verified; retry import to resume"
            )

        def process_progress(info):
            jobs.check(id)
            jobs.update(
                id,
                status=info["status"] if info["status"] != "complete" else "saving",
                current_step=f'{sym}: {info["current_file"]}',
                progress_percentage=(100 * symbol_index + 50 + info["percent"] * 0.5)
                / len(symbols),
            )

        DatasetProcessor(sym).process_and_save(
            progress_callback=process_progress,
            cancellation_check=lambda: jobs.check(id),
        )
    return {"symbols": symbols}


@router.post("/start")
def start_import(req: StartImportRequest):
    sym = req.symbol.upper()
    if get_market(sym, None) is None:
        raise HTTPException(400, "Unsupported symbol")
    try:
        return jobs.start(
            "import", lambda id: import_pipeline(id, sym, req.import_both), sym
        )
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/status")
def status():
    return jobs.get(kind="import")


@router.get("/status/{id}")
def job(id: str):
    result = jobs.get(id)
    if not result:
        raise HTTPException(404, "Job not found")
    return result


@router.post("/cancel/{id}")
def cancel(id: str):
    try:
        return jobs.cancel(id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
