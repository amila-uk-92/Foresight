import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Detail, ForecastState, Metric } from "../forecastTypes";
import { InspectDrawer, ReplayStrip, SevenRanges, type ScoreRow } from "./LabVisuals";
import { LabChart, type ChartSeries } from "./LabChart";
import { EvidenceFailure, EvidenceView } from "./EvidencePanel";
import { NewsWorkbench } from "./NewsWorkbench";
import { useForecastEvidence } from "./evidenceApi";
import { Legend } from "./viz";

// Primary model is always blue and actual prices always white; extra models keep a fixed colour each.
const PRIMARY = "#4C9AFF";
const ACTUAL = "#F1F5FA";
const EXTRA = ["#F6B84A", "#B690FF", "#EC729D", "#78E4A1", "#FFA878", "#C6D45F", "#2DD4BF", "#E988EE", "#F87171", "#A8B3C2"];
const TABS = [
  ["next", "Next 7 Days"],
  ["actual", "Predicted vs Actual"],
  ["days", "Past Test Days"],
  ["accuracy", "Accuracy & Ranges"],
  ["numbers", "All Numbers"],
  ["evidence", "Evidence & Reasoning"],
] as const;
type Tab = (typeof TABS)[number][0];

const number = (n: number | null | undefined, d = 0) =>
  n == null || !Number.isFinite(n) ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const day = (s: string | number, year = true) =>
  new Date(typeof s === "number" ? s * 1000 : s).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    ...(year ? { year: "numeric" } : {}),
  });
const timestamp = (s: string) => Date.parse(s) / 1000;
const stored = (key: string, fallback: string) => {
  try {
    return localStorage.getItem("foresight.lab." + key) ?? fallback;
  } catch {
    return fallback;
  }
};
const remember = (key: string, value: string) => {
  try {
    localStorage.setItem("foresight.lab." + key, value);
  } catch {
    /* Storage unavailable: the choice is simply not kept. */
  }
};
async function request<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(
    "/api/forecasting" + path,
    body === undefined
      ? undefined
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}
type Point = { time: number; value: number; lower?: number; upper?: number; forecast_id?: string; origin?: string };
type Curve = { label: string; model_id: string; points: Point[] };
type Entry = {
  label: string;
  family: string;
  model_id: string;
  status: string;
  forecast_id?: string;
  lookback_days: number;
  metrics?: {
    horizons: Metric[];
    forecast_count: number;
    scorable_target_count: number;
    pending_target_count: number;
    unscorable_target_count: number;
    weekly: { brier_score: number | null };
  };
};
// Newer runs train a few families, pick one on validation and final-test only that winner.
type Candidate = {
  rank?: number;
  label: string;
  family: string;
  model_id: string;
  status: string;
  selected?: boolean;
  day7_mae_usdt?: number;
  baseline_day7_mae_usdt?: number;
  day7_skill_vs_no_change?: number;
  horizon_mae_usdt?: Record<string, number>;
};
type Selection = {
  start?: string;
  end?: string;
  sample_count?: number;
  baseline_day7_mae_usdt?: number;
  winner?: string;
  winner_beats_no_change?: boolean;
  candidates: Candidate[];
};
type Evidence = {
  run: {
    id: string;
    mode: string;
    status: string;
    origin: string;
    start: string;
    end: string;
    models: Entry[];
    evaluation_label: string;
    error?: string;
    validation_selection?: Selection;
  };
  lines: Curve[];
  actual: Point[];
  observed_through: string;
  horizon_hours: number;
};

// Compact checklist: one primary model, any others switched on for comparison.
function ModelsMenu({
  models,
  primary,
  extras,
  colorOf,
  onPrimary,
  onToggle,
  onOnlyPrimary,
}: {
  models: Entry[];
  primary: string;
  extras: string[];
  colorOf: (id: string) => string;
  onPrimary: (id: string) => void;
  onToggle: (id: string) => void;
  onOnlyPrimary: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div className="lab-models" ref={ref}>
      <button className="v-btn small" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}>
        Models · {1 + extras.length} of {models.length}
      </button>
      {open && (
        <div className="lab-models-menu" role="dialog" aria-label="Models">
          <div className="lab-models-head">
            <span>Primary</span>
            <span>Compare</span>
          </div>
          {models.map((m) => {
            const isPrimary = m.model_id === primary;
            return (
              <div key={m.model_id} className={`lab-models-row ${isPrimary ? "primary" : ""}`}>
                <input
                  type="radio"
                  name="lab-primary"
                  aria-label={`Make ${m.label} the primary model`}
                  checked={isPrimary}
                  onChange={() => onPrimary(m.model_id)}
                />
                <input
                  type="checkbox"
                  aria-label={`Show ${m.label}`}
                  checked={isPrimary || extras.includes(m.model_id)}
                  disabled={isPrimary}
                  onChange={() => onToggle(m.model_id)}
                />
                <i style={{ background: colorOf(m.model_id) }} />
                <span>{m.label}</span>
              </div>
            );
          })}
          <button className="v-btn small" onClick={onOnlyPrimary} disabled={!extras.length}>
            Show only the primary model
          </button>
        </div>
      )}
    </div>
  );
}

// The seven targets of one saved forecast, opened from a chart point or a test day.
function ForecastDrill({ detail, label, onClose }: { detail: Detail; label: string; onClose?: () => void }) {
  const ev = detail.evaluation?.points || [];
  const scored = ev.filter((e) => e.state === "evaluated").length;
  return (
    <aside className="lab-drill" aria-label="Selected forecast">
      <div className="lab-drill-head">
        <div>
          <strong>Forecast made {day(detail.forecast.origin)}</strong>
          <span className="v-muted small">
            {label} · {scored} of 7 days scored · start {number(detail.forecast.origin_price)} USDT
          </span>
        </div>
        {onClose && (
          <button className="v-btn small" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      <SevenRanges detail={detail} />
      <Legend
        items={[
          { color: "#1B5E6C", label: "80% range" },
          { color: "#2DD4E8", label: "Most likely", shape: "dot" },
          { color: ACTUAL, label: "Actual, inside" },
          { color: "#F08A4B", label: "Actual, outside" },
        ]}
      />
    </aside>
  );
}

export function ModelComparison({
  state,
  onRefresh,
  labMode = "price",
  onLabModeChange,
  onNavigateToNewsDataset,
}: {
  state: ForecastState;
  onRefresh: () => Promise<void>;
  labMode?: "price" | "news";
  onLabModeChange?: (mode: "price" | "news") => void;
  onNavigateToNewsDataset?: () => void;
}) {
  // One saved run at a time: a finished Train & Compare replaces the previous run.
  // While a new run is in progress, keep showing the last finished one.
  const runs = state.runs.filter((r) => r.mode === "comparison");
  const saved = runs.find((r) => r.status === "complete") || runs.find((r) => r.status !== "running");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [origin, setOrigin] = useState("");
  const [historyDays, setHistoryDays] = useState(() => Number(stored("historyDays", "30")) || 30);
  const [horizon, setHorizon] = useState(() => Number(stored("horizon", "168")) || 168);
  const [tab, setTab] = useState<Tab>(() => {
    const t = stored("tab", "next");
    return (TABS.some(([k]) => k === t) ? t : "next") as Tab;
  });
  const [primary, setPrimary] = useState(() => stored("primary", ""));
  const [extras, setExtras] = useState<string[]>([]);
  const [showRange, setShowRange] = useState(() => stored("range", "1") === "1");
  const [showActual, setShowActual] = useState(() => stored("actual", "1") === "1");
  const [forecastOnly, setForecastOnly] = useState(() => stored("forecastOnly", "0") === "1");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Detail | null>(null);
  const [inspecting, setInspecting] = useState<Detail | null>(null);
  const [scores, setScores] = useState<{ key: string; rows: ScoreRow[] }>({ key: "", rows: [] });
  useEffect(() => remember("historyDays", String(historyDays)), [historyDays]);
  useEffect(() => remember("horizon", String(horizon)), [horizon]);
  useEffect(() => remember("tab", tab), [tab]);
  useEffect(() => remember("range", showRange ? "1" : "0"), [showRange]);
  useEffect(() => remember("actual", showActual ? "1" : "0"), [showActual]);
  useEffect(() => remember("forecastOnly", forecastOnly ? "1" : "0"), [forecastOnly]);
  useEffect(() => {
    if (primary) remember("primary", primary);
  }, [primary]);
  const running = !!state.job && !["complete", "failed", "cancelled"].includes(state.job.status);
  const chosen = saved?.id || "";

  useEffect(() => {
    let stop = false;
    if (!chosen) return;
    request<Evidence>(`/comparisons/${chosen}?horizon=${horizon}`)
      .then((e) => !stop && setEvidence(e))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [chosen, horizon, state.job?.status, state.models.length]);
  const models = useMemo(() => evidence?.run.models || [], [evidence]);
  const primaryId = models.some((m) => m.model_id === primary) ? primary : models[0]?.model_id || "";
  const shown = useMemo(() => [primaryId, ...extras.filter((x) => x !== primaryId && models.some((m) => m.model_id === x))], [primaryId, extras, models]);
  const colorOf = useCallback(
    (id: string) => (id === primaryId ? PRIMARY : EXTRA[Math.max(0, models.findIndex((m) => m.model_id === id)) % EXTRA.length]),
    [primaryId, models],
  );
  const labelOf = useCallback((id: string) => models.find((m) => m.model_id === id)?.label || id, [models]);

  // Saved seven-day forecasts for the models on screen (fetched once per model and history range).
  const forecastKey = shown.map((id) => `${id}:${models.find((m) => m.model_id === id)?.forecast_id || ""}`).join(",") + `|${historyDays}`;
  useEffect(() => {
    let stop = false;
    const wanted = forecastKey
      .split("|")[0]
      .split(",")
      .map((s) => s.split(":"))
      .filter(([, f]) => f);
    if (!wanted.length) return;
    Promise.all(wanted.map(([id, f]) => request<Detail>(`/forecasts/${f}?history_days=${historyDays}`).then((d) => [id, d] as const)))
      .then((rows) => !stop && setDetails((prev) => ({ ...prev, ...Object.fromEntries(rows) })))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [forecastKey, historyDays]);
  const detailOf = useCallback(
    (id: string) => {
      const d = details[id];
      return d && d.history_days === historyDays && d.forecast.id === models.find((m) => m.model_id === id)?.forecast_id ? d : undefined;
    },
    [details, historyDays, models],
  );
  const primaryDetail = detailOf(primaryId);

  const scoreKey = chosen && primaryId ? `${chosen}:${primaryId}` : "";
  useEffect(() => {
    let stop = false;
    if (!scoreKey) return;
    const [run, model] = scoreKey.split(":");
    request<{ rows: ScoreRow[] }>(`/runs/${run}/scores?model_id=${encodeURIComponent(model)}`)
      .then((r) => !stop && setScores({ key: scoreKey, rows: r.rows }))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [scoreKey, state.job?.status]);
  const scoreRows = useMemo(() => (scores.key === scoreKey ? scores.rows : []), [scores, scoreKey]);
  // Past Test Days opens on the latest day whose seventh target is already known.
  const latestScored = useMemo(() => [...scoreRows].reverse().find((r) => r.points[6]?.error != null)?.forecast_id || "", [scoreRows]);
  const openId = selectedId || (tab === "days" ? latestScored : "");
  useEffect(() => {
    let stop = false;
    if (!openId) return;
    request<Detail>(`/forecasts/${openId}?history_days=7`)
      .then((d) => !stop && setSelected(d))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [openId]);
  const drill = openId && selected?.forecast.id === openId ? selected : null;

  const choosePrimary = (id: string) => {
    setPrimary(id);
    setExtras([]);
    setSelectedId("");
  };
  const toggle = (id: string) => setExtras((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]));

  // Next 7 Days: actual prices before the start (and after it only where stored), then saved predictions.
  // "Forecast only" drops the history before the start, keeping the start candle and any later actuals.
  const nextSeries = useMemo<ChartSeries[]>(() => {
    if (!primaryDetail) return [];
    const f = primaryDetail.forecast;
    const start = timestamp(f.origin);
    const step = primaryDetail.history_step_seconds || 3600;
    const actual = [
      ...primaryDetail.history.filter((p) => p.time <= start && (!forecastOnly || p.time === start)),
      ...primaryDetail.actuals.filter((p) => p.time > start),
    ].map((p) => ({ time: p.time, value: p.close }));
    const out: ChartSeries[] = showActual ? [{ id: "actual", label: "Actual", color: ACTUAL, points: actual, width: 2, step }] : [];
    const path = (d: Detail, key: "median" | "lower" | "upper") => [
      { time: timestamp(d.forecast.origin), value: d.forecast.origin_price },
      ...d.forecast.points.map((p) => ({ time: timestamp(p.target), value: p[key] })),
    ];
    for (const id of shown) {
      const d = id === primaryId ? primaryDetail : detailOf(id);
      if (!d) continue;
      out.push({ id, label: labelOf(id), color: colorOf(id), points: path(d, "median"), width: id === primaryId ? 3 : 2 });
      if (id === primaryId && showRange) {
        out.push({ id: "lower", label: "80% low", color: PRIMARY, points: path(d, "lower"), width: 1, dashed: true, quiet: true });
        out.push({ id: "upper", label: "80% high", color: PRIMARY, points: path(d, "upper"), width: 1, dashed: true, quiet: true });
      }
    }
    return out;
  }, [primaryDetail, detailOf, shown, showRange, showActual, forecastOnly, primaryId, colorOf, labelOf]);

  // Predicted vs Actual: predictions and actual closes placed on the date they were about.
  const actualSeries = useMemo<ChartSeries[]>(() => {
    if (!evidence) return [];
    const out: ChartSeries[] = showActual
      ? [{ id: "actual", label: "Actual", color: ACTUAL, points: evidence.actual.map((p) => ({ time: p.time, value: p.value })), width: 2, step: 86400 }]
      : [];
    for (const id of shown) {
      const line = evidence.lines.find((l) => l.model_id === id);
      if (!line) continue;
      out.push({ id, label: labelOf(id), color: colorOf(id), points: line.points.map((p) => ({ time: p.time, value: p.value })), width: id === primaryId ? 3 : 2, step: 86400 });
      if (id === primaryId && showRange && line.points.every((p) => p.lower != null && p.upper != null)) {
        out.push({ id: "lower", label: "80% low", color: PRIMARY, points: line.points.map((p) => ({ time: p.time, value: p.lower! })), width: 1, dashed: true, quiet: true, step: 86400 });
        out.push({ id: "upper", label: "80% high", color: PRIMARY, points: line.points.map((p) => ({ time: p.time, value: p.upper! })), width: 1, dashed: true, quiet: true, step: 86400 });
      }
    }
    return out;
  }, [evidence, shown, showRange, showActual, primaryId, colorOf, labelOf]);
  const pickActual = useCallback(
    (time: number) => {
      const q = evidence?.lines.find((l) => l.model_id === primaryId)?.points.find((p) => p.time === time);
      if (q?.forecast_id) setSelectedId(q.forecast_id);
    },
    [evidence, primaryId],
  );

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      let utc: string | null = null;
      if (origin) {
        const parsed = Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(origin) ? origin : origin + "Z");
        if (!Number.isFinite(parsed)) throw new Error("Use a valid UTC origin date");
        utc = new Date(parsed).toISOString();
      }
      await request("/comparisons", { origin: utc });
      setSelectedId("");
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const entry = models.find((m) => m.model_id === primaryId);
  // Evidence & Reasoning follows the forecast opened elsewhere, else the primary model's latest one.
  const evidenceId = selectedId || entry?.forecast_id || "";
  const evidenceDetail = selectedId ? drill : primaryDetail;
  const savedEvidence = useForecastEvidence(tab === "evidence" ? evidenceId : undefined);
  const metricAt = (m: Entry | undefined, h: number) => m?.metrics?.horizons.find((x) => x.horizon_hours === h);
  const pm = metricAt(entry, horizon);
  const p7 = metricAt(entry, 168);
  const maxError = Math.max(1, ...models.map((m) => metricAt(m, horizon)?.mae_usdt || 0), pm?.baseline_mae_usdt || 0);
  const w = models.map((m) => metricAt(m, horizon)?.mae_usdt);
  const best = models[w.indexOf(Math.min(...w.filter((x): x is number => x != null)))];
  const job = state.job;
  const horizonPicker = (
    <div className="v-seg small" role="group" aria-label="Days ahead">
      {[1, 2, 3, 4, 5, 6, 7].map((d) => (
        <button key={d} className={horizon === d * 24 ? "on" : ""} aria-pressed={horizon === d * 24} onClick={() => setHorizon(d * 24)}>
          {d}d
        </button>
      ))}
    </div>
  );
  // Each graph offers only models that have saved outputs for it.
  const offered = models.filter((m) =>
    tab === "next" ? !!m.forecast_id : (evidence?.lines.find((l) => l.model_id === m.model_id)?.points.length ?? 0) > 0,
  );
  const graphControls = (
    <>
      <label className="lab-toggle" title="Show or hide the real closing prices">
        <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
        Actual price
      </label>
      <label className="lab-toggle" title="80% range of the primary model">
        <input type="checkbox" checked={showRange} onChange={(e) => setShowRange(e.target.checked)} />
        Uncertainty range
      </label>
      <ModelsMenu
        models={offered}
        primary={primaryId}
        extras={extras.filter((x) => x !== primaryId)}
        colorOf={colorOf}
        onPrimary={choosePrimary}
        onToggle={toggle}
        onOnlyPrimary={() => setExtras([])}
      />
    </>
  );
  const seriesKey = (list: ChartSeries[]) => (
    <div className="lab-keys">
      {list
        .filter((s) => !s.quiet)
        .map((s) => (
          <span key={s.id}>
            <i style={{ background: s.color }} />
            {s.id === "actual" ? "Actual price" : s.id === primaryId ? `${s.label} (primary)` : s.label}
          </span>
        ))}
      {showRange && list.some((s) => s.id === "lower") && (
        <span>
          <i className="dash" style={{ borderColor: PRIMARY }} />
          80% range, {labelOf(primaryId)}
        </span>
      )}
    </div>
  );

  // Validation scores of every trained family (newer runs only); final test exists for the winner alone.
  const selection = evidence?.run.validation_selection?.candidates.some((c) => c.day7_mae_usdt != null) ? evidence.run.validation_selection : undefined;
  const validationMax = Math.max(1, ...(selection?.candidates.map((c) => c.horizon_mae_usdt?.[String(horizon)] || 0) || []), selection?.baseline_day7_mae_usdt || 0);
  const validation = selection && (
    <div>
      <h3>
        Validation pick, {selection.sample_count ?? 0} days{selection.start && selection.end && ` ${day(selection.start, false)} – ${day(selection.end)}`} · typical miss at {horizon / 24}d, USDT
        {horizon === 168 && " · grey line = “stays put”"}
      </h3>
      <div className="v-hbars">
        {selection.candidates.map((c) => {
          const v = c.horizon_mae_usdt?.[String(horizon)];
          return (
            <div key={c.family} className={`lab-hbar ${c.selected ? "on" : ""}`}>
              <span>
                {c.label}
                {c.selected && <em> · chosen</em>}
              </span>
              <span className="track">
                <i style={{ width: `${(100 * (v || 0)) / validationMax}%`, background: c.selected ? PRIMARY : "#53677E" }} />
                {horizon === 168 && selection.baseline_day7_mae_usdt != null && <em style={{ left: `${(100 * selection.baseline_day7_mae_usdt) / validationMax}%` }} />}
              </span>
              <b className="v-num">{number(v)}</b>
            </div>
          );
        })}
      </div>
      <p className="v-sub">
        {selection.winner_beats_no_change === false
          ? "The chosen model did not beat “stays put” at day 7 on validation."
          : selection.winner_beats_no_change
            ? "The chosen model beat “stays put” at day 7 on validation."
            : ""}{" "}
        Only the chosen model is scored on the final test months.
      </p>
    </div>
  );

  let body: ReactNode = null;
  if (evidence && tab === "next") {
    const f = primaryDetail?.forecast;
    const p = f?.points[6];
    const ev = primaryDetail?.evaluation?.points || [];
    const known = primaryDetail ? primaryDetail.actuals.filter((a) => a.time > timestamp(primaryDetail.forecast.origin)).length : 0;
    body = !primaryDetail || !f || !p ? (
      <p className="v-sub lab-wait">Loading the saved forecast…</p>
    ) : (
      <>
        <div className="lab-info">
          <span>
            <b style={{ color: PRIMARY }}>{labelOf(primaryId)}</b> most likely on {day(p.target, false)}:{" "}
            <b className="v-num">{number(p.median)}</b> USDT ({p.median >= f.origin_price ? "+" : ""}
            {number((p.median / f.origin_price - 1) * 100, 1)}%)
          </span>
          <span>
            80% range <b className="v-num">{number(p.lower)}–{number(p.upper)}</b>
          </span>
          <span>
            Rise chance <b className="v-num">{number(f.probabilities.positive * 100)}%</b>
          </span>
          <span>
            Outcomes in data <b className="v-num">{ev.filter((e) => e.state === "evaluated").length} of 7</b>
            {known === 0 && " (after the last candle)"}
          </span>
          <span>
            Day-7 miss <b className="v-num">{number(p7?.mae_usdt)}</b> vs “stays put” <b className="v-num">{number(p7?.baseline_mae_usdt)}</b>
          </span>
          <button className="lab-agents" onClick={() => setInspecting(primaryDetail)} title="Inspect this saved forecast (read-only)">
            {(["specialist", "coordinator", "publisher", "evaluator"] as const).map((k) => (
              <i key={k} className={`v-dot ${/^(Ready|Complete|Saved|Approved)$/.test(primaryDetail.agents[k]) ? "ok" : /^(Pending|Waiting|Partial)$/.test(primaryDetail.agents[k]) ? "idle" : "bad"}`} title={`${k}: ${primaryDetail.agents[k]}`} />
            ))}
            Inspect
          </button>
        </div>
        {seriesKey(nextSeries)}
        <LabChart
          series={nextSeries}
          fitKey={`next:${f.id}:${forecastOnly ? "only" : historyDays}`}
          divider={{ time: timestamp(f.origin), label: `Forecast start · ${day(f.origin)} ${f.origin.slice(11, 16)} UTC` }}
        />
      </>
    );
  } else if (evidence && tab === "actual") {
    body = (
      <>
        <div className="lab-info">
          <span>
            What each model said <b>{horizon / 24} day{horizon > 24 ? "s" : ""}</b> before each date, against the real close
          </span>
          <span>
            Scored <b className="v-num">{pm?.sample_count ?? 0}</b> · not known yet <b className="v-num">{pm?.pending_count ?? 0}</b> · forecasts{" "}
            <b className="v-num">{entry?.metrics?.forecast_count ?? 0}</b>
          </span>
          <span>
            {labelOf(primaryId)} miss <b className="v-num">{number(pm?.mae_usdt)}</b> vs “stays put” <b className="v-num">{number(pm?.baseline_mae_usdt)}</b> USDT
          </span>
          <span className="v-muted">Click the primary line to open that forecast.</span>
        </div>
        {seriesKey(actualSeries)}
        <div className={`lab-with-drill ${drill ? "open" : ""}`}>
          <LabChart series={actualSeries} fitKey={`actual:${chosen}:${horizon}`} onPick={pickActual} />
          {drill && <ForecastDrill detail={drill} label={labelOf(primaryId)} onClose={() => setSelectedId("")} />}
        </div>
      </>
    );
  } else if (evidence && tab === "days") {
    const sevenScored = scoreRows.filter((r) => r.points[6].error != null && r.points[6].baseline_error != null);
    const closer = sevenScored.filter((r) => r.points[6].error! <= r.points[6].baseline_error!).length;
    body = (
      <>
        <div className="lab-info">
          <span>
            <b style={{ color: PRIMARY }}>{labelOf(primaryId)}</b> · {scoreRows.length} test days, {day(evidence.run.start, false)} – {day(timestamp(evidence.run.end) - 3600, true)}
          </span>
          <span>
            Closer than “stays put” at day 7 on <b className="v-num">{closer}</b> of <b className="v-num">{sevenScored.length}</b> scored days
          </span>
          <span className="v-muted">Click a day to see all seven of its targets.</span>
        </div>
        <ReplayStrip rows={scoreRows} selected={openId} onSelect={setSelectedId} start={evidence.run.start} end={evidence.run.end} />
        {drill ? (
          <ForecastDrill detail={drill} label={labelOf(primaryId)} />
        ) : (
          <p className="v-sub lab-wait">No day selected.</p>
        )}
      </>
    );
  } else if (evidence && tab === "accuracy") {
    body = (
      <>
        <div className="lab-info">
          <span>
            {models.length === 1 ? "The final-tested model" : `All ${models.length} models`} at <b>{horizon / 24} day{horizon > 24 ? "s" : ""}</b> ahead · primary in blue
          </span>
          <span>
            Smallest miss: <b>{best?.label || "—"}</b> ({number(metricAt(best, horizon)?.mae_usdt)}) · “stays put” <b className="v-num">{number(pm?.baseline_mae_usdt)}</b>
          </span>
          {horizonPicker}
        </div>
        <div className="lab-accuracy">
          <div>
            <h3>Typical miss, USDT · shorter is better · grey line = “stays put”</h3>
            <div className="v-hbars">
              {models.map((m) => {
                const h = metricAt(m, horizon);
                return (
                  <button key={m.model_id} className={m.model_id === primaryId ? "on" : ""} onClick={() => choosePrimary(m.model_id)} title={`Make ${m.label} the primary model`}>
                    <span>{m.label}</span>
                    <span className="track">
                      <i style={{ width: `${(100 * (h?.mae_usdt || 0)) / maxError}%`, background: m.model_id === primaryId ? PRIMARY : "#53677E" }} />
                      {pm?.baseline_mae_usdt != null && <em style={{ left: `${(100 * pm.baseline_mae_usdt) / maxError}%` }} />}
                    </span>
                    <b className="v-num">{number(h?.mae_usdt)}</b>
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <h3>Real prices inside the 80% range · dashed line = 80% target</h3>
            <div className="v-hbars">
              {models.map((m) => {
                const h = metricAt(m, horizon);
                return (
                  <button key={m.model_id} className={m.model_id === primaryId ? "on" : ""} onClick={() => choosePrimary(m.model_id)} title={`Make ${m.label} the primary model`}>
                    <span>{m.label}</span>
                    <span className="track">
                      <i style={{ width: `${100 * (h?.coverage || 0)}%`, background: m.model_id === primaryId ? PRIMARY : "#53677E" }} />
                      <em className="target" style={{ left: "80%" }} />
                    </span>
                    <b className="v-num">{h?.coverage == null ? "—" : `${number(100 * h.coverage)}%`}</b>
                  </button>
                );
              })}
            </div>
          </div>
          {validation}
        </div>
        <p className="v-note">{evidence.run.evaluation_label}</p>
      </>
    );
  } else if (tab === "evidence") {
    const actions = (
      <>
        {selectedId ? (
          <button className="v-btn small" onClick={() => setSelectedId("")}>
            Show the latest forecast
          </button>
        ) : (
          <span className="v-muted">Open a past day to see its evidence.</span>
        )}
        {evidenceDetail && (
          <button className="lab-agents" onClick={() => setInspecting(evidenceDetail)} title="Inspect this saved forecast (read-only)">
            Inspect
          </button>
        )}
      </>
    );
    const provenance = !evidenceId ? (
      <p className="v-sub lab-wait">{labelOf(primaryId)} has no saved forecast to show evidence for.</p>
    ) : savedEvidence.load.status === "ok" ? (
      <EvidenceView e={savedEvidence.load.data} label={labelOf(savedEvidence.load.data.versions.model_version)} actions={actions} />
    ) : (
      <EvidenceFailure load={savedEvidence.load} onRetry={savedEvidence.retry} />
    );
    body = provenance;
  } else if (evidence && tab === "numbers") {
    body = (
      <>
        <div className="lab-info">
          <span>
            Measured at <b>{horizon / 24} day{horizon > 24 ? "s" : ""}</b> ahead · outcomes known through {day(evidence.observed_through)}
          </span>
          {horizonPicker}
        </div>
        <div className="lab-table">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Forecasts</th>
                <th>Scored</th>
                <th>Not known yet</th>
                <th>Missing in data</th>
                <th>MAE USDT</th>
                <th>“Stays put” MAE</th>
                <th>Coverage</th>
                <th>Width USDT</th>
                <th>Interval score</th>
                <th>Direction Brier</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => {
                const h = metricAt(m, horizon);
                return (
                  <tr key={m.model_id} className={m.model_id === primaryId ? "primary" : ""}>
                    <td>{m.label}</td>
                    <td>{m.metrics?.forecast_count ?? 0}</td>
                    <td>{h?.sample_count ?? 0}</td>
                    <td>{h?.pending_count ?? 0}</td>
                    <td>{h?.unscorable_count ?? 0}</td>
                    <td>{number(h?.mae_usdt)}</td>
                    <td>{number(h?.baseline_mae_usdt)}</td>
                    <td>{h?.coverage == null ? "—" : `${number(100 * h.coverage, 1)}%`}</td>
                    <td>{number(h?.width_usdt)}</td>
                    <td>{number(h?.interval_score_usdt)}</td>
                    <td>{number(m.metrics?.weekly.brier_score, 3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {selection && (
            <table className="comparison-table">
              <caption>
                Validation pick · {selection.sample_count ?? 0} shared daily origins
                {selection.start && selection.end && `, ${day(selection.start, false)} – ${day(selection.end)}`}
              </caption>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Model</th>
                  <th>{horizon / 24}-day MAE USDT</th>
                  <th>Day-7 MAE USDT</th>
                  <th>“Stays put” day-7 MAE</th>
                  <th>Day-7 skill vs “stays put”</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {selection.candidates.map((c) => (
                  <tr key={c.family} className={c.model_id === primaryId ? "primary" : ""}>
                    <td>{c.rank ?? "—"}</td>
                    <td>{c.label}</td>
                    <td>{number(c.horizon_mae_usdt?.[String(horizon)])}</td>
                    <td>{number(c.day7_mae_usdt)}</td>
                    <td>{number(c.baseline_day7_mae_usdt)}</td>
                    <td>{c.day7_skill_vs_no_change == null ? "—" : `${number(100 * c.day7_skill_vs_no_change, 1)}%`}</td>
                    <td>{c.selected ? "Chosen, final-tested" : c.status === "not_selected" ? "Not chosen, not kept" : c.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <p className="v-note">{evidence.run.evaluation_label}</p>
      </>
    );
  }

  return (
    <main className="forecast-view comparison-view v-page lab-page">
      <header className="v-header lab-toolbar">
        <h1>Forecast Lab</h1>
        {onLabModeChange && (
          <div className="v-top-tabs" role="tablist" aria-label="Forecast Lab mode">
            <button
              role="tab"
              aria-selected={labMode === "price"}
              className={labMode === "price" ? "on" : ""}
              onClick={() => onLabModeChange("price")}
            >
              Price &amp; Volume Models
            </button>
            <button
              role="tab"
              aria-selected={labMode === "news"}
              className={labMode === "news" ? "on" : ""}
              onClick={() => onLabModeChange("news")}
            >
              News &amp; Macro Models
            </button>
          </div>
        )}
        {labMode === "price" && (
          <>
            <span className="v-pill" title="Each Train & Compare replaces the previous run, its models and its predictions">
              <span className="v-muted">Trained</span>
              <b>{saved ? day(saved.created_at) : "Not yet"}</b>
            </span>
            <label className="v-pill">
              <span className="v-muted">Forecast origin</span>
              <input aria-label="Forecast origin (UTC)" placeholder="Latest candle" value={origin} onChange={(e) => setOrigin(e.target.value)} />
            </label>
            <button className="v-primary" disabled={busy || running} onClick={() => void start()}>
              Train &amp; Compare Models
            </button>
            <div className="lab-job" role="status">
              {job && running ? (
                <>
                  <span className="lab-job-bar">
                    <i style={{ width: `${job.progress_percentage}%` }} />
                  </span>
                  <span className="lab-job-text" title={job.current_step}>
                    {number(job.progress_percentage)}% · {job.current_step}
                  </span>
                  <button className="v-btn small" onClick={() => void request(`/jobs/${job.job_id}/cancel`, {}).then(onRefresh)}>
                    Cancel
                  </button>
                </>
              ) : job ? (
                <span className={`lab-job-text ${job.status === "failed" ? "bad" : ""}`} title={job.error || job.current_step}>
                  <i className={`v-dot ${job.status === "complete" ? "ok" : job.status === "failed" ? "bad" : "idle"}`} />
                  {job.status === "complete" ? job.current_step : `${job.status[0].toUpperCase()}${job.status.slice(1)}${job.error ? ": " + job.error : ""}`}
                </span>
              ) : (
                <span className="lab-job-text v-muted">No training run yet</span>
              )}
            </div>
          </>
        )}
      </header>
      {labMode === "news" ? (
        <NewsWorkbench mode="forecast" onNavigateToDataset={onNavigateToNewsDataset} />
      ) : (
        <>
          {(error || evidence?.run.error) && (
            <div className="error" role="alert">
              {error || evidence?.run.error}
            </div>
          )}
          {!evidence && tab !== "evidence" ? (
            <section className="v-card v-empty">
              <h2>Compare real models</h2>
              <p className="v-sub">
                Train &amp; Compare trains the configured model families on the same data, picks one on the validation months, tests it on the held-out months, then predicts the next seven days. Each run replaces the previous one, so only one trained model and one set of predictions are kept.
              </p>
            </section>
          ) : (
            <section className="v-card lab-ws" aria-label="Forecast workspace">
              <div className="lab-ws-head">
                <div className="lab-tabs" role="tablist" aria-label="Forecast views">
                  {TABS.map(([k, label]) => (
                    <button key={k} id={`forecast-tab-${k}`} role="tab" aria-controls={`forecast-panel-${k}`} aria-selected={tab === k} tabIndex={tab === k ? 0 : -1} className={tab === k ? "on" : ""} onClick={() => setTab(k)} onKeyDown={e => {
                      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                      e.preventDefault();
                      const i = TABS.findIndex(([id]) => id === k);
                      const next = e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length;
                      setTab(TABS[next][0]);
                      (e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next])?.focus();
                    }}>
                      {label}
                    </button>
                  ))}
                </div>
                <div className="lab-ws-controls">
                  {tab === "next" && (
                    <label className="lab-toggle" title="Hide the price history before the forecast start">
                      <input type="checkbox" checked={forecastOnly} onChange={(e) => setForecastOnly(e.target.checked)} />
                      Forecast only
                    </label>
                  )}
                  {tab === "next" && !forecastOnly && (
                    <div className="v-seg small" role="group" aria-label="History shown">
                      {[7, 30, 90, 180, 365].map((d) => (
                        <button key={d} className={historyDays === d ? "on" : ""} aria-pressed={historyDays === d} onClick={() => setHistoryDays(d)}>
                          {d === 365 ? "1y" : `${d}d`}
                        </button>
                      ))}
                    </div>
                  )}
                  {tab === "actual" && horizonPicker}
                  {(tab === "next" || tab === "actual") && graphControls}
                </div>
              </div>
              <div id={`forecast-panel-${tab}`} aria-labelledby={`forecast-tab-${tab}`} className={`lab-ws-body tab-${tab}`} role="tabpanel">
                {body}
              </div>
            </section>
          )}
          {inspecting && (
            <InspectDrawer detail={inspecting} label={`${labelOf(inspecting.forecast.model_version)} · Price & Volume Specialist`} onClose={() => setInspecting(null)} />
          )}
        </>
      )}
    </main>
  );
}
