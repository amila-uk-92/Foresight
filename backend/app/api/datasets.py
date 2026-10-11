"""Dataset metadata, candles, table inspection, quality report, and CSV export API endpoints."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import io

from backend.app.config import MANIFESTS_DIR
from backend.app.markets import get_market, markets
from backend.app.processor import DatasetProcessor
from backend.app.splits import calculate_split_summaries
from backend.app.models import DatasetMetadata, CandleData, TableResponse, QualityReport

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", summary="Get inventory of all supported datasets")
def get_datasets_inventory():
    """Return overview inventory of supported datasets and their current local state."""
    inventory = []
    for market in markets():
        sym = market.symbol
        proc = DatasetProcessor(sym)
        df = proc.load_processed()
        report = proc.load_quality_report()

        has_data = df is not None and not df.empty
        status = (
            report.get("status", "awaiting_import")
            if report
            else ("ready" if has_data else "awaiting_import")
        )
        is_verified = report.get("is_verified", False) if report else False
        total_rows = len(df) if has_data else 0

        inventory.append(
            {
                "symbol": sym,
                "display_name": market.display_name,
                "base_asset": market.base_asset,
                "quote_asset": market.quote_asset,
                "is_primary": market.is_primary,
                "has_data": has_data,
                "status": status,
                "is_verified": is_verified,
                "candle_count": total_rows,
                "expected_count": market.expected_candles,
                "interval": market.interval,
                "source": market.venue,
                "timezone": market.timezone,
                "asset_class": market.asset_class,
            }
        )
    return {"datasets": inventory}


@router.get("/{symbol}/metadata", response_model=DatasetMetadata)
def get_dataset_metadata(symbol: str):
    """Return comprehensive metadata, split distributions, and quality status for a symbol."""
    sym = symbol.upper()
    market = get_market(sym, None)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Unsupported symbol '{symbol}'")
    expected = market.expected_candles

    proc = DatasetProcessor(sym)
    df = proc.load_processed()
    report_data = proc.load_quality_report()

    if df is None or df.empty:
        # Return awaiting import structure
        empty_splits = calculate_split_summaries(pd.DataFrame(), market.splits)
        quality_empty = QualityReport(
            symbol=sym,
            status="awaiting_import",
            is_verified=False,
            total_expected=expected,
            total_actual=0,
            completeness_percentage=0.0,
            missing_hours_count=expected,
            duplicate_count=0,
            conflicting_duplicate_count=0,
            invalid_ohlc_count=0,
            negative_volume_count=0,
            non_positive_price_count=0,
            timestamp_alignment_valid=False,
            coverage_start=None,
            coverage_end=None,
            cross_market_aligned=None,
            issues=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return _metadata(market, 0, empty_splits, quality_empty)

    splits_data = calculate_split_summaries(df, market.splits)

    # Revalidate older bundles instead of inferring quality from row counts alone.
    from backend.app.validator import validate_dataset

    quality_obj = QualityReport(**validate_dataset(df, sym, market=market))

    return _metadata(market, len(df), splits_data, quality_obj)


def _metadata(market, total_candles, splits, quality):
    return DatasetMetadata(
        symbol=market.symbol,
        source=market.venue,
        interval=market.interval_label,
        date_coverage=market.date_coverage,
        timezone=market.timezone,
        total_period=f"{market.total_months} months",
        total_candles=total_candles,
        expected_candles=market.expected_candles,
        splits=splits,
        quality=quality,
        base_asset=market.base_asset,
        quote_asset=market.quote_asset,
    )


@router.get("/{symbol}/candles")
def get_dataset_candles(
    symbol: str,
    split: Optional[str] = Query(
        None,
        description="Optional split filter ('training', 'validation', 'final_test')",
    ),
    start_time: Optional[int] = Query(
        None, description="Optional start unix timestamp"
    ),
    end_time: Optional[int] = Query(None, description="Optional end unix timestamp"),
):
    """Return lightweight candle and volume points for chart plotting."""
    sym = symbol.upper()
    proc = DatasetProcessor(sym)
    df = proc.load_processed()

    if df is None or df.empty:
        return {"symbol": sym, "candles": [], "total": 0}

    filtered = df
    if split:
        filtered = filtered[filtered["split"] == split]
    if start_time is not None:
        filtered = filtered[filtered["open_time_unix"] >= start_time]
    if end_time is not None:
        filtered = filtered[filtered["open_time_unix"] < end_time]

    # Convert to chart format
    # Lightweight Charts requires: time (unix seconds), open, high, low, close, and volume
    candles = []
    for row in filtered[
        [
            "open_time_unix",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "split",
        ]
    ].itertuples(index=False):
        candles.append(
            {
                "time": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "quote_volume": row[6],
                "split": row[7],
            }
        )

    return {"symbol": sym, "total": len(candles), "candles": candles}


@router.get("/{symbol}/table", response_model=TableResponse)
def get_dataset_table(
    symbol: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    split: Optional[str] = Query(None, description="Filter by split"),
    order: str = Query(
        "asc", pattern="^(asc|desc)$", description="Sort order by timestamp"
    ),
):
    """Return paginated rows for Candle Inspector table."""
    sym = symbol.upper()
    proc = DatasetProcessor(sym)
    df = proc.load_processed()

    if df is None or df.empty:
        return TableResponse(
            total_rows=0, page=page, page_size=page_size, total_pages=0, rows=[]
        )

    filtered = df
    if split and split != "all":
        filtered = filtered[filtered["split"] == split]

    if order == "desc":
        filtered = filtered.sort_values(by="open_time_unix", ascending=False)
    else:
        filtered = filtered.sort_values(by="open_time_unix", ascending=True)

    total_rows = len(filtered)
    total_pages = (total_rows + page_size - 1) // page_size if total_rows > 0 else 0

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)
    page_df = filtered.iloc[start_idx:end_idx]

    rows = []
    for _, r in page_df.iterrows():
        rows.append(
            CandleData(
                timestamp=r["open_time"],
                timestamp_ms=int(r["open_time_ms"]),
                time=int(r["open_time_unix"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
                quote_volume=float(r["quote_volume"]),
                close_time=r["close_time"],
                trade_count=int(r["trade_count"]),
                taker_buy_base_volume=float(r["taker_buy_base_volume"]),
                taker_buy_quote_volume=float(r["taker_buy_quote_volume"]),
                split=r["split"],
                source_file=r["source_file"],
            )
        )

    return TableResponse(
        total_rows=total_rows,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        rows=rows,
    )


@router.get("/{symbol}/quality")
def get_dataset_quality_report(symbol: str):
    """Get raw quality report JSON for symbol."""
    sym = symbol.upper()
    proc = DatasetProcessor(sym)
    from backend.app.validator import validate_dataset

    frame = proc.load_processed()
    report = validate_dataset(frame, sym) if frame is not None else None
    if not report:
        raise HTTPException(
            status_code=404, detail=f"No quality report found for {sym}"
        )
    return report


@router.get("/{symbol}/manifest")
def get_dataset_manifest(symbol: str):
    """Get source manifest JSON for symbol."""
    sym = symbol.upper()
    manifest_path = MANIFESTS_DIR / f"{sym}_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"No manifest found for {sym}")
    import json

    return json.loads(manifest_path.read_text())


@router.get("/{symbol}/export")
def export_dataset_csv(
    symbol: str,
    split: Optional[str] = Query(
        None,
        description="Optional split filter ('training', 'validation', 'final_test')",
    ),
):
    """Stream filtered dataset as downloadable CSV."""
    sym = symbol.upper()
    proc = DatasetProcessor(sym)
    df = proc.load_processed()

    if df is None or df.empty:
        raise HTTPException(
            status_code=404, detail=f"No processed data available to export for {sym}"
        )

    filtered = df
    if split and split != "all":
        filtered = filtered[filtered["split"] == split]

    stream = io.StringIO()
    filtered.to_csv(stream, index=False)
    stream.seek(0)

    market = get_market(sym, None)
    interval = market.interval if market else "1h"
    filename = f"{sym}_{interval}_export{f'_{split}' if split else ''}.csv"
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
