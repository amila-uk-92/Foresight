"""Pydantic models for Foresight."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class CandleData(BaseModel):
    timestamp: str  # ISO UTC format
    timestamp_ms: int # Millisecond timestamp for chart
    time: int # Unix seconds for TradingView Lightweight Charts
    open: float
    high: float
    low: float
    close: float
    volume: float  # Traded quantity in the market's volume unit (BTC for BTCUSDT)
    quote_volume: float # Volume in the quote currency (USDT for BTCUSDT)
    close_time: str
    trade_count: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float
    split: str  # 'training', 'validation', 'final_test'
    source_file: str

class SplitSummary(BaseModel):
    key: str
    name: str
    label: str
    date_label: str
    duration_months: int
    start: str
    end: str
    expected_count: int
    actual_count: int
    percentage: float
    note: Optional[str] = None
    color: str

class QualityIssue(BaseModel):
    category: str
    description: str
    count: int = 1
    sample: Optional[Dict[str, Any]] = None

class QualityReport(BaseModel):
    symbol: str
    status: str  # 'verified', 'warnings', 'awaiting_import', 'failed'
    is_verified: bool
    total_expected: int
    total_actual: int
    completeness_percentage: float
    missing_hours_count: int
    missing_intervals: List[Dict[str, str]] = []
    duplicate_count: int
    conflicting_duplicate_count: int
    invalid_ohlc_count: int
    negative_volume_count: int
    non_positive_price_count: int
    timestamp_alignment_valid: bool
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    cross_market_aligned: Optional[bool] = None
    issues: List[QualityIssue] = []
    generated_at: str

class ManifestFileEntry(BaseModel):
    filename: str
    url: str
    checksum_url: str
    expected_sha256: str
    actual_sha256: Optional[str] = None
    checksum_verified: bool = False
    size_bytes: int = 0
    downloaded_at: Optional[str] = None
    status: str  # 'verified', 'failed', 'missing', 'pending'

class SourceManifest(BaseModel):
    symbol: str
    archive_url_base: str
    total_files: int
    verified_files: int
    failed_files: int
    generated_at: str
    files: List[ManifestFileEntry] = []

class DatasetMetadata(BaseModel):
    symbol: str
    source: str
    interval: str
    date_coverage: str
    timezone: str
    total_period: str
    total_candles: int
    expected_candles: int
    splits: Dict[str, SplitSummary]
    quality: QualityReport
    base_asset: str
    quote_asset: str

class TableResponse(BaseModel):
    total_rows: int
    page: int
    page_size: int
    total_pages: int
    rows: List[CandleData]

class ImportStatusResponse(BaseModel):
    job_id: str
    symbol: str
    status: str  # 'idle', 'downloading', 'parsing', 'validating', 'complete', 'cancelled', 'failed'
    progress_percentage: float
    current_step: str
    total_files: int
    completed_files: int
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
