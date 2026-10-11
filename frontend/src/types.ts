export interface Candle {
  time: number; // Unix seconds
  timestamp?: string; // ISO string
  timestamp_ms?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number; // Base volume
  quote_volume: number; // Quote volume in USDT
  close_time?: string;
  trade_count?: number;
  taker_buy_base_volume?: number;
  taker_buy_quote_volume?: number;
  split: 'training' | 'validation' | 'final_test';
  source_file?: string;
}

export interface SplitInfo {
  key: string;
  name: string;
  label: string;
  date_label: string;
  duration_months: number;
  start: string;
  end: string;
  expected_count: number;
  actual_count: number;
  percentage: number;
  color: string;
  note?: string;
}

export interface QualityReport {
  symbol: string;
  status: 'verified' | 'warnings' | 'awaiting_import' | 'failed' | 'ready';
  is_verified: boolean;
  total_expected: number;
  total_actual: number;
  completeness_percentage: number;
  missing_hours_count: number;
  missing_intervals?: Array<{ start: string; end: string; hours: string | number }>;
  duplicate_count: number;
  conflicting_duplicate_count: number;
  invalid_ohlc_count: number;
  negative_volume_count: number;
  non_positive_price_count: number;
  timestamp_alignment_valid: boolean;
  coverage_start: string | null;
  coverage_end: string | null;
  cross_market_aligned: boolean | null;
  issues: Array<{ category: string; description: string; count: number }>;
  generated_at: string;
}

export interface DatasetMetadata {
  symbol: string;
  source: string;
  interval: string;
  date_coverage: string;
  timezone: string;
  total_period: string;
  total_candles: number;
  expected_candles: number;
  splits: {
    training: SplitInfo;
    validation: SplitInfo;
    final_test: SplitInfo;
  };
  quality: QualityReport;
  base_asset: string;
  quote_asset: string;
}

export interface TableResponse {
  total_rows: number;
  page: number;
  page_size: number;
  total_pages: number;
  rows: Candle[];
}

export interface ImportStatus {
  job_id: string;
  symbol: string;
  status: 'normalizing' | 'running' | 'idle' | 'pending' | 'downloading' | 'parsing' | 'validating' | 'saving' | 'complete' | 'cancelled' | 'failed';
  progress_percentage: number;
  current_step: string;
  total_files: number;
  completed_files: number;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}
