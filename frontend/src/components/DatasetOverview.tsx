import type { Candle, DatasetMetadata } from "../types";
import { Badge, C, Card, Donut, Ring, fmt, shortDate } from "./viz";

const SPLIT_COLORS: Record<string, string> = {
  training: C.accent,
  validation: C.validation,
  final_test: C.test,
};
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

export function DatasetHeader({
  symbol,
  onSymbolChange,
  metadata,
  onImport,
  importLabel,
  datasetMode = "price",
  onDatasetModeChange,
}: {
  symbol: string;
  onSymbolChange: (s: string) => void;
  metadata: DatasetMetadata | null;
  onImport: () => void;
  importLabel: string;
  datasetMode?: "price" | "news";
  onDatasetModeChange?: (mode: "price" | "news") => void;
}) {
  const q = metadata?.quality;
  const loaded = !!metadata && metadata.total_candles > 0;
  return (
    <header className="v-header">
      <h1>Dataset</h1>
      {onDatasetModeChange && (
        <div className="v-top-tabs" role="tablist" aria-label="Dataset type">
          <button
            role="tab"
            aria-selected={datasetMode === "price"}
            className={datasetMode === "price" ? "on" : ""}
            onClick={() => onDatasetModeChange("price")}
          >
            Price &amp; Volume Data
          </button>
          <button
            role="tab"
            aria-selected={datasetMode === "news"}
            className={datasetMode === "news" ? "on" : ""}
            onClick={() => onDatasetModeChange("news")}
          >
            News &amp; Macro Dataset
          </button>
        </div>
      )}
      <label className="v-select">
        <span className="coin" aria-hidden="true">
          {symbol.startsWith("ETH") ? "Ξ" : "₿"}
        </span>
        <select aria-label="Symbol" value={symbol} onChange={(e) => onSymbolChange(e.target.value)}>
          <option value="BTCUSDT">BTC / USDT</option>
          <option value="ETHUSDT">ETH / USDT</option>
        </select>
      </label>
      <span className="v-muted" title={metadata?.date_coverage}>
        {datasetMode === "price" ? "Binance Spot · 1 hour · UTC" : "Point-in-time News & Macro Evidence · UTC"}
      </span>
      <div className="v-grow" />
      {datasetMode === "price" && q && (
        <div className="v-health">
          <Ring
            value={loaded ? q.completeness_percentage / 100 : 0}
            color={q.is_verified ? C.good : loaded ? C.good : C.warn}
            label={`Dataset ${fmt(q.completeness_percentage, 3)} percent complete`}
          />
          <strong>{loaded ? `${fmt(q.completeness_percentage, 3)}% complete` : "Awaiting import"}</strong>
          {loaded && q.missing_hours_count > 0 && (
            <Badge tone="warn">
              {q.missing_hours_count} missing hour{q.missing_hours_count === 1 ? "" : "s"}
            </Badge>
          )}
          {loaded && q.is_verified && <Badge tone="good">Verified</Badge>}
        </div>
      )}
      {datasetMode === "price" && (
        <button className="v-btn" onClick={onImport}>
          {importLabel}
        </button>
      )}
    </header>
  );
}

export function PriceSummary({ candles, filter }: { candles: Candle[]; filter: string | null }) {
  const first = candles.find((c) => c.close > 0);
  const last = candles.at(-1);
  if (!first || !last) return <div className="v-price" />;
  const change = last.close / first.close - 1;
  return (
    <div className="v-price">
      <span className="v-num big">{fmt(last.close)}</span>
      <span className="v-muted">USDT · last close {shortDate(last.time, true)}</span>
      <span className={`v-num ${change >= 0 ? "up" : "down"}`}>
        {change >= 0 ? "▲ +" : "▼ "}
        {fmt(change * 100, 0)}% since {filter ? "period start" : shortDate(first.time, true)}
      </span>
    </div>
  );
}

export function SplitChips({
  splits,
  active,
  onSelect,
}: {
  splits: DatasetMetadata["splits"];
  active: string | null;
  onSelect: (s: string | null) => void;
}) {
  return (
    <div className="v-chips" role="group" aria-label="Chart period">
      <button className={`v-chip ${active === null ? "on" : ""}`} aria-pressed={active === null} onClick={() => onSelect(null)}>
        All history
      </button>
      {Object.values(splits).map((s) => (
        <button
          key={s.key}
          className={`v-chip ${active === s.key ? "on" : ""}`}
          aria-pressed={active === s.key}
          title={`${s.date_label} · ${s.actual_count.toLocaleString()} of ${s.expected_count.toLocaleString()} hourly candles${s.note ? " · " + s.note : ""}`}
          onClick={() => onSelect(active === s.key ? null : s.key)}
        >
          <i style={{ background: SPLIT_COLORS[s.key] }} />
          {s.name}
        </button>
      ))}
    </div>
  );
}

export function SplitRibbon({ splits }: { splits: DatasetMetadata["splits"] }) {
  const short = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", { timeZone: "UTC", month: "short", year: "2-digit" });
  // End dates are exclusive, so label the last included month.
  const lastMonth = (iso: string) => short(new Date(Date.parse(iso) - 3600e3).toISOString());
  const years: number[] = [];
  const s = new Date(splits.training.start).getUTCFullYear(),
    e = new Date(splits.final_test.end).getUTCFullYear();
  for (let y = s + 1; y <= e; y++) years.push(y);
  return (
    <>
      <div className="v-ribbon" aria-label="Chronological split">
        {Object.values(splits).map((sp) => (
          <div key={sp.key} className={sp.key} style={{ flex: `${sp.percentage} 1 0` }} title={`${sp.name}: ${sp.date_label}`}>
            <span>
              {sp.key === "final_test" ? "Test" : sp.name} · {sp.duration_months} mo
            </span>
            {sp.percentage > 30 && (
              <span className="v-num">
                {short(sp.start)} → {lastMonth(sp.end)}
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="v-ticks">
        {years.map((y) => (
          <span key={y}>{y}</span>
        ))}
      </div>
    </>
  );
}

export function DatasetTiles({ metadata: m }: { metadata: DatasetMetadata }) {
  const q = m.quality;
  const start = new Date(m.splits.training.start);
  const end = Date.parse(m.splits.final_test.end);
  // Missing hours per month, from the stored quality report's exact gap list.
  const missingByMonth: Record<string, number> = {};
  for (const gap of q.missing_intervals || []) {
    for (let t = Date.parse(gap.start); t < Date.parse(gap.end); t += 3600e3) {
      const d = new Date(t);
      const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
      missingByMonth[key] = (missingByMonth[key] || 0) + 1;
    }
  }
  const rows: { label: string; cells: { cls: string; title: string }[] }[] = [];
  const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
  let row: (typeof rows)[number] | null = null;
  let index = 0;
  while (cursor.getTime() < end) {
    if (index % 12 === 0) {
      const y = cursor.getUTCFullYear() % 100;
      row = { label: `${y}–${y + 1}`, cells: [] };
      rows.push(row);
    }
    const t = cursor.getTime();
    const split =
      t < Date.parse(m.splits.validation.start)
        ? "training"
        : t < Date.parse(m.splits.final_test.start)
          ? "validation"
          : "final_test";
    const next = Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1);
    const hours = (next - t) / 3600e3;
    const missing = missingByMonth[`${cursor.getUTCFullYear()}-${cursor.getUTCMonth()}`] || 0;
    const name = cursor.toLocaleDateString("en-GB", { timeZone: "UTC", month: "short", year: "numeric" });
    row!.cells.push({
      cls: `${split}${missing ? " gap" : ""}`,
      title: missing ? `${name}: ${hours - missing} of ${hours} hours` : `${name}: all ${hours} hours present`,
    });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    index++;
  }
  const heads = Array.from({ length: 12 }, (_, i) => MONTHS[(start.getUTCMonth() + i) % 12]);
  const checks = [
    { label: "Missing hours", n: q.missing_hours_count },
    { label: "Duplicates", n: q.duplicate_count + q.conflicting_duplicate_count },
    { label: "Invalid OHLC", n: q.invalid_ohlc_count },
    { label: "Invalid prices", n: q.non_positive_price_count },
    { label: "Invalid volume", n: q.negative_volume_count },
    { label: "Hourly alignment", n: q.timestamp_alignment_valid ? 0 : 1 },
  ];
  const clean = checks.filter((c) => !c.n).length;
  const splits = Object.values(m.splits);
  const years = Math.round(splits.reduce((a, s) => a + s.duration_months, 0) / 12);
  const roles: Record<string, string> = { training: "learn", validation: "tune", final_test: "test, held out" };
  return (
    <div className="v-grid3">
      <Card title="Every month, every hour" aside={<span className="v-muted small">{index} months</span>} label="Monthly completeness">
        <div className="v-months" style={{ gridTemplateColumns: `56px repeat(12, minmax(0, 1fr))` }}>
          <span />
          {heads.map((h, i) => (
            <span key={i} className="head">
              {h}
            </span>
          ))}
          {rows.map((r) => [
            <span key={r.label} className="v-num year">
              {r.label}
            </span>,
            ...r.cells.map((c, i) => <div key={r.label + i} className={`v-cell ${c.cls}`} title={c.title} />),
          ])}
        </div>
        <div className="v-legend">
          <span>
            <i className="box" style={{ background: C.accent, opacity: 0.78 }} />
            Complete
          </span>
          <span>
            <i className="box gapkey" />
            Has a gap
          </span>
        </div>
      </Card>
      <Card
        title="Quality checks"
        aside={<span className={`small ${clean === 6 ? "good" : "warn"}`}>{clean} of 6 clean</span>}
        label="Quality checks"
      >
        <div className="v-checks">
          {checks.map((c) => (
            <div key={c.label} title={c.n ? `${c.n} found` : "None found"}>
              <span className={`v-check ${c.n ? "warn" : "ok"}`}>
                {c.n ? (
                  c.n > 99 ? "99+" : c.n
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                    <path d="M5 12l5 5 9-10" />
                  </svg>
                )}
              </span>
              <span>{c.label}</span>
            </div>
          ))}
        </div>
        <p className="v-sub">Missing hours stay missing. Nothing is forward-filled.</p>
      </Card>
      <Card title={`${fmt(m.total_candles)} hourly candles`} label="Split sizes">
        <div className="v-donut-row">
          <Donut
            parts={splits.map((s) => ({ value: s.actual_count, color: SPLIT_COLORS[s.key] }))}
            center={`${years} yrs`}
            caption="of hourly data"
            label={splits.map((s) => `${s.name} ${fmt(s.percentage, 1)} percent`).join(", ")}
          />
          <div className="v-donut-key">
            {splits.map((s) => (
              <div key={s.key}>
                <i style={{ background: SPLIT_COLORS[s.key] }} />
                <span className="v-num">{fmt(s.percentage)}%</span>
                <span className="v-muted">{roles[s.key]}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
