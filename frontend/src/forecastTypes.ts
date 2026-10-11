export interface ForecastPoint {
  target: string;
  horizon_hours: number;
  median: number;
  lower: number;
  upper: number;
}
export interface Forecast {
  id: string;
  run_id: string;
  role: string;
  specialist_id: string;
  model_version: string;
  contract_version: string;
  origin: string;
  generated_at: string;
  latest_input_availability: string;
  latest_input_close: string;
  training_cutoff: string;
  dataset_version: string;
  configuration_id: string;
  origin_price: number;
  mode: string;
  status: string;
  points: ForecastPoint[];
  probabilities: { positive: number; negative: number; zero: number };
  quality_flags: string[];
  definitions: {
    central_estimate: string;
    interval: string;
    target: string;
    zero_return: string;
  };
  input_summary: {
    lookback_days: number;
    start: string;
    end: string;
    candle_count: number;
    feature_values: Record<string, number>;
  };
  baseline: {
    name: string;
    sample_count: number;
    latest_target: string;
    positive_probability: number;
  };
}
export interface Model {
  id: string;
  family: string;
  created_at: string;
  dataset_version: string;
  training_cutoff: string;
  configuration_id: string;
  configuration: { lookback_days: number; alpha: number };
  features: string[];
  fitting_period: { start: string; end_exclusive: string };
  selection_period: { start: string; end_exclusive: string };
  calibration_period: { start: string; end_exclusive: string };
  counts: { fitting: number; selection: number; calibration: number };
  selection_mae_usdt: number;
  probability_method: string;
  interval_method: string;
  development: boolean;
  selected?: boolean;
  uses_final_test_outcomes?: boolean;
  feature_definitions?: Record<string, string>;
}
export interface Score {
  target: string;
  horizon_hours: number;
  state: string;
  actual_price?: number;
  absolute_price_error?: number;
  interval_coverage?: boolean;
  interval_score?: number;
  absolute_return_error_percentage_points?: number;
  interval_width?: number;
  brier_score?: number;
  direction_accuracy?: boolean;
}
export interface Evaluation {
  state: string;
  clock: string;
  scored_count: number;
  points: Score[];
}
export interface Agents {
  source: "active_job" | "forecast" | "run" | "none";
  specialist: string;
  coordinator: string;
  publisher: string;
  evaluator: string;
  details: Record<string, number>;
}
export interface Detail {
  forecast: Forecast;
  model: Model;
  evaluation: Evaluation | null;
  history: { time: number; close: number }[];
  history_days: number;
  history_step_seconds: number;
  actuals: { time: number; close: number }[];
  agents: Agents;
}
export interface HistoryRow {
  id: string;
  origin: string;
  generated_at: string;
  run_id: string;
  mode: string;
  model_version: string;
  origin_price: number;
  day7_target: string;
  day7_median: number;
  day7_lower: number;
  day7_upper: number;
  implied_return: number;
  positive_probability: number;
  evaluation_state: string;
  scored_count: number;
  day7_actual?: number | null;
  day7_error?: number | null;
  quality_flags: string[];
}
export interface HistoryPage {
  total: number;
  page: number;
  page_size: number;
  rows: HistoryRow[];
}
export interface SavedForecast {
  id: string;
  origin: string;
  model_version: string;
  run_id: string;
  mode: string;
  role: string;
  generated_at: string;
}
export interface Metric {
  horizon_hours: number;
  sample_count: number;
  mae_usdt?: number;
  return_mae_percentage_points?: number;
  coverage?: number;
  width_usdt?: number;
  interval_score_usdt?: number;
  baseline_mae_usdt?: number;
  baseline_coverage?: number;
  baseline_interval_score_usdt?: number;
  mae_95pct_block_bootstrap?: number[] | null;
  pending_count: number;
  unscorable_count: number;
}
export interface Summary {
  specialist?: Summary;
  run_id: string;
  forecast_count: number;
  mode?: string;
  evaluation_state_counts: Record<string, number>;
  scorable_target_count: number;
  unscorable_target_count: number;
  pending_target_count: number;
  horizons: Metric[];
  weekly: {
    sample_count: number;
    direction_accuracy: number | null;
    brier_score: number | null;
    baseline_brier_score: number | null;
  };
  by_model: Record<
    string,
    {
      day7_sample_count: number;
      day7_mae_usdt: number | null;
      horizon_mae_usdt: Record<string, number | null>;
      horizon_sample_count: Record<string, number>;
    }
  >;
  probability_calibration: {
    lower: number;
    upper: number;
    sample_count: number;
    predicted_positive: number | null;
    actual_positive: number | null;
  }[];
  calibration_status: string;
  uncertainty_method: string;
  baseline: string;
}
export interface Run {
  id: string;
  created_at: string;
  mode: string;
  status: string;
  model_id: string;
  initial_model_id: string;
  start: string;
  end: string;
  clock: string;
  summary?: Summary;
  skipped_origins: { origin: string; agent?: string; reason: string }[];
  evaluation_label: string;
  development?: boolean | null;
  development_reason?: string | null;
  uses_final_test_outcomes?: boolean;
}
export interface Job {
  job_id: string;
  status: string;
  progress_percentage: number;
  current_step: string;
  error: string | null;
  agents: Record<string, string>;
  run_id?: string;
  result?: { forecast_id?: string; run_id?: string; model_id?: string };
}
export interface Decision {
  id: string;
  created_at: string;
  clock?: string;
  kind?: string;
  incumbent: string;
  candidate: string;
  promoted: boolean;
  reason: string;
  sample_count?: number;
  uses_final_test_outcomes?: boolean;
}
export interface ForecastState {
  models: Model[];
  selected_model: string | null;
  runs: Run[];
  forecasts: SavedForecast[];
  job: Job | null;
  decisions: Decision[];
  periods: Record<string, { start: string; end: string }>;
  promotion_policy: {
    cadence_days: number;
    comparison_days: number;
    minimum_daily_origins: number;
    mae_improvement_fraction: number;
    coverage_floor: number;
  };
}
// Read-only evidence view of one saved forecast (backend schema forecast-evidence/1).
export type RecordState = "recorded" | "empty" | "not_recorded" | "not_implemented" | "unavailable";
export interface StateNote {
  state: RecordState;
  reason?: string;
  error?: string;
}
export interface SourceRecord {
  source_id: string;
  kind: string;
  url: string | null;
  checksum_url: string | null;
  sha256: string | null;
  checksum_verified: boolean;
  published_at: string | null;
  retrieved_at: string | null;
  retrieved_after_origin: boolean;
  candles_used: number;
  first_candle_open: string;
  last_candle_close: string;
}
export interface MarketSources extends StateNote {
  venue?: string;
  symbol?: string;
  dataset_version?: string;
  archive_base?: string;
  window_start?: string;
  window_end?: string;
  candle_count?: number;
  latest_candle_close?: string;
  availability_rule?: string;
  publication_note?: string;
  records?: SourceRecord[];
}
export interface ForecastEvidence {
  news_evidence?: StateNote & {
    packet?: { id: string; origin: string; policy: string };
    features?: { id: string; names: string[]; values: number[] };
    articles?: { id: string; headline: string; url: string; published_at: string; effective_available_at: string; content_scope: string }[];
    classifications?: { id: string; model: string; question_version: string }[];
  };
  schema_version: string;
  forecast_id: string;
  specialist_forecast_id: string | null;
  forecast: {
    symbol: string;
    mode: string;
    run_id: string;
    producing_run_id: string | null;
    origin: string;
    generated_at: string;
    evidence_cutoff: string;
    latest_input_close: string;
    training_cutoff: string;
    origin_price: number;
    historical_origin: boolean;
    targets: { day: number; target: string; horizon_hours: number }[];
  };
  numerical: {
    state: RecordState;
    coordination: StateNote & { method: string | null; coordinator_version: string | null; weights: Record<string, number> | null };
    definitions: Forecast["definitions"] | null;
    points: ForecastPoint[];
    probabilities: Forecast["probabilities"] | null;
    baseline: { name: string; sample_count: number; latest_target: string; positive_probability: number } | null;
    quality_flags: string[];
  };
  outcomes: StateNote & {
    evaluation_state: string;
    clock: string | null;
    observed_through: string | null;
    counts: { known: number; pending: number; missing: number };
    points: { day: number; target: string; status: "known" | "pending" | "missing"; actual_price: number | null; reason: string | null }[];
  };
  sources: { market_data: MarketSources; research: StateNote };
  reasoning: StateNote & {
    forecast_state: RecordState;
    summary: string | null;
    findings: unknown[];
    arguments: { bull: unknown[]; bear: unknown[]; counterarguments: unknown[] };
    moderator: { findings: unknown[]; rejected_claims: unknown[]; unresolved_conflicts: unknown[] };
    agreement: unknown;
  };
  agents: { id: string; name: string; state: "active" | "planned" | "pending" | "not_recorded" | "experimental" | "unavailable" | "bypassed"; detail: string }[];
  versions: {
    contract_version: string | null;
    model_version: string;
    model_family: string | null;
    model_family_label: string | null;
    model_record: RecordState;
    dataset_version: string;
    configuration_id: string | null;
    coordinator_version: string | null;
    prompt_version: StateNote;
    memory_version: StateNote;
    ensemble_version: StateNote;
  };
  cost_latency: {
    inference_cost: StateNote;
    forecast_latency: StateNote;
    job: StateNote & { job_id?: string; started_at?: string; finished_at?: string; seconds?: number; scope?: string };
  };
  run: StateNote & { evaluation_label: string | null; development: boolean | null };
  trading: { state: "not_enabled" | string; label: string; reason: string };
}
