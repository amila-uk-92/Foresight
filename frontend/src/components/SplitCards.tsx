import type { DatasetMetadata } from "../types";
// Compact split filter: one chip per period plus "All history".
export function SplitCards({
  splits,
  activeSplitFilter,
  onSelectSplit,
}: {
  splits: DatasetMetadata["splits"];
  activeSplitFilter: string | null;
  onSelectSplit: (split: string | null) => void;
}) {
  return (
    <div className="split-chips" role="group" aria-label="Chart period">
      <button
        className={`split-chip ${activeSplitFilter === null ? "selected" : ""}`}
        aria-pressed={activeSplitFilter === null}
        onClick={() => onSelectSplit(null)}
      >
        All history
      </button>
      {Object.values(splits).map((s) => (
        <button
          key={s.key}
          className={`split-chip ${s.key} ${activeSplitFilter === s.key ? "selected" : ""}`}
          aria-pressed={activeSplitFilter === s.key}
          title={`${s.label}: ${s.date_label} · ${s.duration_months} months · ${s.actual_count.toLocaleString()} / ${s.expected_count.toLocaleString()} hourly candles${s.note ? " · " + s.note : ""}`}
          onClick={() =>
            onSelectSplit(activeSplitFilter === s.key ? null : s.key)
          }
          style={{ ["--split-color" as string]: s.color }}
        >
          <i aria-hidden="true" />
          <strong>{s.label.charAt(0) + s.label.slice(1).toLowerCase()}</strong>
          <span>{s.date_label}</span>
          <small>{s.percentage.toFixed(1)}%</small>
        </button>
      ))}
    </div>
  );
}
