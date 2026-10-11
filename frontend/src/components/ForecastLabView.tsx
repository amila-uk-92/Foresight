import { useCallback, useEffect, useState } from "react";
import { ModelComparison } from "./ModelComparison";
import { EvaluationView } from "./EvaluationView";
import { HistoryView } from "./HistoryView";
import type { ForecastState, Job } from "../forecastTypes";

const utcTimestamp = (value: string) =>
  Date.parse(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + "Z");
const date = (s: string) =>
  new Date(s).toLocaleString("en-GB", {
    timeZone: "UTC",
    dateStyle: "medium",
    timeStyle: "short",
  }) + " UTC";
const terminal = (j: Job | null) =>
  !j || ["complete", "failed", "cancelled"].includes(j.status);
async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(
    "/api/forecasting" + path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

// Polls the saved forecasting state and routes to the Lab, Evaluation, History or Settings page.
export function ForecastLabView({
  view = "forecast_lab",
  labMode = "price",
  onLabModeChange,
  onNavigateToNewsDataset,
}: {
  view?: string;
  labMode?: "price" | "news";
  onLabModeChange?: (mode: "price" | "news") => void;
  onBackToDataset?: () => void;
  onNavigateToNewsDataset?: () => void;
}) {
  const [state, setState] = useState<ForecastState | null>(null);
  const [error, setError] = useState("");
  const [apiDown, setApiDown] = useState(false);
  const [origin, setOrigin] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setState(await api<ForecastState>("/state"));
      setApiDown(false);
    } catch (e) {
      // A failed poll means the local backend is unreachable, not a forecast error.
      setApiDown(true);
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    const first = setTimeout(() => void refresh(), 0);
    const t = setInterval(() => void refresh(), 1500);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);
  const action = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (!state)
    return (
      <main className="forecast-view v-page">
        <section className="v-card v-empty">
          <h2>{apiDown ? "Backend unavailable" : "Loading saved state…"}</h2>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="v-btn" onClick={() => void refresh()}>
            Retry connection
          </button>
        </section>
      </main>
    );
  const banner = apiDown && (
    <div className="error v-banner" role="alert">
      Backend unavailable. Saved results are unchanged; retrying every 1.5
      seconds.
    </div>
  );
  if (view === "forecast_lab")
    return (
      <>
        {banner}
        <ModelComparison
          state={state}
          onRefresh={refresh}
          labMode={labMode}
          onLabModeChange={onLabModeChange}
          onNavigateToNewsDataset={onNavigateToNewsDataset}
        />
      </>
    );
  if (view === "evaluation")
    return (
      <>
        {banner}
        <EvaluationView state={state} />
      </>
    );
  if (view === "history")
    return (
      <>
        {banner}
        <HistoryView state={state} />
      </>
    );
  const running = !terminal(state.job);
  const selectedModel = state.models.find((m) => m.id === state.selected_model);
  return (
    <main className="forecast-view v-page">
      {banner}
      <header className="v-header">
        <h1>Settings</h1>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <section className="v-card settings-panel">
        <h2>Model lifecycle</h2>
        <p className="v-sub">
          Training: 36 months. Selection and calibration: separate chronological
          validation subdivisions. Final test: June–September 2026.
        </p>
        <p className="v-sub">
          Adaptive candidates: every 30 days. Independent earlier comparison: 45
          days, minimum 30 eligible daily origins. Promote only with ≥1% MAE
          improvement, no worse interval score than incumbent/baseline, no worse
          MAE than no-change, and coverage ≥70%.
        </p>
        <label className="v-pill">
          <span className="v-muted">Retraining cutoff (UTC)</span>
          <input
            type="text"
            placeholder="YYYY-MM-DDTHH:mm"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
          />
        </label>
        <button
          className="v-btn"
          disabled={!selectedModel || !origin || running || busy}
          onClick={() =>
            void action(() =>
              api("/retrain", {
                model_id: state.selected_model,
                cutoff: new Date(utcTimestamp(origin)).toISOString(),
              }),
            )
          }
        >
          Train candidate &amp; compare
        </button>
        {state.job && (
          <p className="v-sub" role="status">
            {state.job.current_step} · {Math.round(state.job.progress_percentage)}%
          </p>
        )}
        <h3>{state.models.length > 1 ? "Models / rollback" : "Saved model"}</h3>
        {state.models.map((m) => (
          <div className="history-row" key={m.id}>
            <span>
              {m.id} · {m.family} · cutoff {date(m.training_cutoff)}
              {m.id === state.selected_model ? " · selected" : ""}
            </span>
            {state.models.length > 1 && (
              <button
                className="v-btn small"
                disabled={running || busy}
                onClick={() =>
                  void action(() => api("/models/" + m.id + "/select", {}))
                }
              >
                Select / rollback
              </button>
            )}
          </div>
        ))}
        <h3>Recorded decisions</h3>
        {state.decisions.length ? (
          state.decisions.map((d) => (
            <div className="history-row" key={d.id}>
              {date(d.created_at)} · {d.reason} · {d.candidate}{" "}
              {d.sample_count != null && `· n=${d.sample_count}`}
            </div>
          ))
        ) : (
          <p className="v-sub">No promotion or rollback decisions recorded.</p>
        )}
      </section>
    </main>
  );
}
