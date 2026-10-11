import { useEffect, useState } from "react";
import type { Detail, ForecastState, HistoryPage } from "../forecastTypes";
import { InspectDrawer } from "./LabVisuals";
import { C, RangeBar, fmt, kfmt, shortDate } from "./viz";

async function api<T>(path: string): Promise<T> {
  const r = await fetch("/api/forecasting" + path);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

const FILTERS = [
  ["", "All"],
  ["prediction", "Predictions"],
  ["comparison", "Model comparison"],
  ["frozen", "Frozen test run"],
  ["adaptive", "Adaptive test run"],
] as const;
const KIND: Record<string, string> = {
  prediction: "Prediction",
  comparison: "Comparison",
  frozen: "Frozen test",
  adaptive: "Adaptive test",
};
const PAGE = 15;

export function HistoryView({ state }: { state: ForecastState }) {
  const [mode, setMode] = useState("");
  const [runChoice, setRun] = useState("");
  // A filter on a run that a newer run has replaced falls back to all forecasts.
  const run = state.runs.some((r) => r.id === runChoice) ? runChoice : "";
  const [page, setPage] = useState(1);
  const [data, setData] = useState<HistoryPage | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Detail | null>(null);
  const count = state.forecasts.length;
  useEffect(() => {
    let stop = false;
    api<HistoryPage>(
      `/forecasts?page=${page}&page_size=${PAGE}` +
        (run ? "&run_id=" + encodeURIComponent(run) : "") +
        (mode ? "&mode=" + mode : ""),
    )
      .then((d) => !stop && (setData(d), setError("")))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [page, run, mode, count]);
  const rows = data?.rows || [];
  const values = rows.flatMap((r) => [r.day7_lower, r.day7_upper, ...(r.day7_actual != null ? [r.day7_actual] : [])]);
  const lo = values.length ? Math.min(...values) : 0,
    hi = values.length ? Math.max(...values) : 1;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const inspect = (id: string) =>
    api<Detail>(`/forecasts/${id}?history_days=30`)
      .then(setOpen)
      .catch((e) => setError(e.message));
  return (
    <main className="forecast-view v-page">
      <header className="v-header">
        <h1>Forecast history</h1>
        {FILTERS.map(([key, label]) => (
          <button
            key={key}
            className={`v-chip ${mode === key ? "on" : ""}`}
            aria-pressed={mode === key}
            onClick={() => {
              setMode(key);
              setPage(1);
            }}
          >
            {label}
          </button>
        ))}
        {state.runs.length > 1 && (
        <label className="v-pill">
          <span className="v-muted">Run</span>
          <select
            aria-label="Run"
            value={run}
            onChange={(e) => {
              setRun(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All runs</option>
            {state.runs.map((r) => (
              <option key={r.id} value={r.id}>
                {KIND[r.mode] || r.mode} · {shortDate(r.created_at, true)}
              </option>
            ))}
          </select>
        </label>
        )}
        <div className="v-grow" />
        <span className="v-muted small">Forecasts from the latest training run; a new run replaces them</span>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <section className="v-card flush" aria-label="Saved forecasts">
        <div className="v-hist-scroll">
          <div className="v-hist">
            <div className="v-hist-row head">
              <span>Made on</span>
              <span>Type</span>
              <span className="split">
                <span>Day-7 range · {kfmt(lo)}</span>
                <span>{kfmt(hi)}</span>
              </span>
              <span>Result</span>
              <span className="right">Miss</span>
            </div>
            {rows.map((r) => {
              const known = r.day7_actual != null;
              const inside = known && r.day7_actual! >= r.day7_lower && r.day7_actual! <= r.day7_upper;
              const missing = !known && r.evaluation_state === "unscorable_due_to_missing_data";
              return (
                <button
                  key={r.id}
                  className="v-hist-row"
                  aria-label={`Open forecast made ${shortDate(r.origin, true)}`}
                  onClick={() => void inspect(r.id)}
                  title={`${r.model_version} · day 7 ${shortDate(r.day7_target, true)} · most likely ${fmt(r.day7_median)} (80%: ${fmt(r.day7_lower)}–${fmt(r.day7_upper)})${known ? ` · actual ${fmt(r.day7_actual)}` : ""}`}
                >
                  <span className="v-num">{shortDate(r.origin, true)}</span>
                  <span className="kind" style={{ color: r.mode === "prediction" ? C.accent : C.muted }}>
                    {KIND[r.mode] || r.mode}
                  </span>
                  <RangeBar
                    lower={r.day7_lower}
                    upper={r.day7_upper}
                    median={r.day7_median}
                    lo={lo}
                    hi={hi}
                    marker={r.day7_actual}
                    markerColor={inside ? C.text : C.miss}
                  />
                  <span>
                    <span className={`v-result ${known ? (inside ? "ok" : "miss") : "wait"}`}>
                      {known ? (inside ? "Inside range" : "Outside") : missing ? "No data" : "Waiting"}
                    </span>
                  </span>
                  <span className="v-num right">{known ? fmt(r.day7_error) : "—"}</span>
                </button>
              );
            })}
            {data && !data.total && <div className="v-empty-row">No saved forecasts yet. Use Train &amp; Compare in the Forecast Lab.</div>}
          </div>
        </div>
        <div className="v-hist-foot">
          <span>
            <i className="box" style={{ background: "#1B5E6C" }} />
            80% range
          </span>
          <span>
            <i className="line" style={{ background: C.accent }} />
            Most likely
          </span>
          <span>
            <i className="line" style={{ background: C.text }} />
            What happened
          </span>
          <div className="v-grow" />
          <span>
            {data ? `${fmt(data.total)} forecasts · page ${page} of ${pages}` : "Loading…"}
          </span>
          <button className="v-btn small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Newer
          </button>
          <button className="v-btn small" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Older
          </button>
        </div>
      </section>
      {open && <InspectDrawer detail={open} onClose={() => setOpen(null)} />}
    </main>
  );
}
