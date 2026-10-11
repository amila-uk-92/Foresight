import type { DatasetMetadata } from "../types";
interface Props {
  metadata: DatasetMetadata;
  showSplitRegions: boolean;
  setShowSplitRegions: (v: boolean) => void;
  showVolume: boolean;
  setShowVolume: (v: boolean) => void;
  onImportClick: () => void;
  isImporting: boolean;
  importProgress?: number;
}
export function DatasetDetails({
  metadata: m,
  showSplitRegions,
  setShowSplitRegions,
  showVolume,
  setShowVolume,
  onImportClick,
  isImporting,
  importProgress,
}: Props) {
  const q = m.quality;
  return (
    <aside className="dataset-details">
      <h2>Dataset details</h2>
      <dl>
        <dt>Symbol</dt>
        <dd>
          {m.base_asset}/{m.quote_asset}
        </dd>
        <dt>Data source</dt>
        <dd>{m.source}</dd>
        <dt>Interval / timezone</dt>
        <dd>
          {m.interval} · {m.timezone}
        </dd>
        <dt>Actual coverage</dt>
        <dd>
          {q.coverage_start?.slice(0, 10) || "—"} →{" "}
          {q.coverage_end?.slice(0, 10) || "—"}
        </dd>
        <dt>Total candles</dt>
        <dd>
          {m.total_candles.toLocaleString()} /{" "}
          {m.expected_candles.toLocaleString()}
        </dd>
      </dl>
      <section>
        <h3>Chronological splits</h3>
        {Object.values(m.splits).map((s) => (
          <div className="split-detail" key={s.key}>
            <span style={{ color: s.color }}>● {s.name}</span>
            <p>{s.date_label}</p>
            <small>
              {s.actual_count.toLocaleString()} rows · {s.duration_months}{" "}
              months
            </small>
          </div>
        ))}
      </section>
      <section>
        <h3>Quality report</h3>
        <p className={q.is_verified ? "good" : "warning"}>
          {q.status.replaceAll("_", " ")} ·{" "}
          {q.completeness_percentage.toFixed(3)}% coverage
        </p>
        <dl>
          <dt>Missing hours</dt>
          <dd>{q.missing_hours_count}</dd>
          <dt>Duplicates / conflicts</dt>
          <dd>
            {q.duplicate_count} / {q.conflicting_duplicate_count}
          </dd>
          <dt>Invalid OHLC</dt>
          <dd>{q.invalid_ohlc_count}</dd>
          <dt>Invalid prices</dt>
          <dd>{q.non_positive_price_count}</dd>
          <dt>Invalid volume / trades</dt>
          <dd>{q.negative_volume_count}</dd>
          <dt>Hourly alignment</dt>
          <dd>
            {q.timestamp_alignment_valid ? "Valid" : "Invalid / unavailable"}
          </dd>
        </dl>
        {q.issues.map((i, index) => (
          <p className="quality-issue" key={index}>
            {i.description}
          </p>
        ))}
      </section>
      <section>
        <h3>Display</h3>
        <label className="toggle-row">
          <span>Split regions</span>
          <input
            type="checkbox"
            checked={showSplitRegions}
            onChange={(e) => setShowSplitRegions(e.target.checked)}
          />
        </label>
        <label className="toggle-row">
          <span>Quote volume (USDT)</span>
          <input
            type="checkbox"
            checked={showVolume}
            onChange={(e) => setShowVolume(e.target.checked)}
          />
        </label>
        <p className="subtitle">
          Missing hours stay missing. No forward filling.
        </p>
      </section>
      <button className="primary" onClick={onImportClick}>
        {isImporting
          ? `Importing · ${Math.round(importProgress || 0)}%`
          : "Import / verify archives"}
      </button>
    </aside>
  );
}
