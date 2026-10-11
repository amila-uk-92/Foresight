import { useEffect, useMemo, useState } from "react";
import type { ForecastState, Summary } from "../forecastTypes";
import { TickRow, type ScoreRow } from "./LabVisuals";
import { Badge, C, Card, Donut, Gauge, Legend, PairBars, TwoLines, fmt, shortDate } from "./viz";
import { Dock } from "./Dock";

async function api<T>(path: string): Promise<T> {
  const r = await fetch("/api/forecasting" + path);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}
const KINDS = [
  ["comparison", "Model comparison"],
  ["frozen", "Frozen · one model"],
  ["adaptive", "Adaptive · retrains monthly"],
] as const;

// Consecutive origin dates as short ranges: "1–3 Jun, 18–21 Aug".
function dateRuns(origins: string[]) {
  const out: string[] = [];
  let first = "",
    prev = 0;
  const flush = () => {
    if (!first) return;
    const a = new Date(first);
    const b = new Date(prev);
    const month = (d: Date) => d.toLocaleDateString("en-GB", { timeZone: "UTC", month: "short" });
    out.push(
      a.getTime() === b.getTime()
        ? `${a.getUTCDate()} ${month(a)}`
        : month(a) === month(b)
          ? `${a.getUTCDate()}–${b.getUTCDate()} ${month(b)}`
          : `${a.getUTCDate()} ${month(a)} – ${b.getUTCDate()} ${month(b)}`,
    );
  };
  for (const o of origins) {
    const t = Date.parse(o);
    if (first && t - prev <= 86400e3) prev = t;
    else {
      flush();
      first = o;
      prev = t;
    }
  }
  flush();
  return out;
}

export function EvaluationView({ state }: { state: ForecastState }) {
  const runs = state.runs.filter((r) => r.status === "complete");
  const kinds = KINDS.filter(([k]) => runs.some((r) => r.mode === k));
  const [kind, setKind] = useState("");
  const activeKind = kind && kinds.some(([k]) => k === kind) ? kind : kinds[0]?.[0] || "";
  const ofKind = runs.filter((r) => r.mode === activeKind);
  const [runChoice, setRunChoice] = useState("");
  const runId = ofKind.some((r) => r.id === runChoice) ? runChoice : ofKind[0]?.id || "";
  const run = runs.find((r) => r.id === runId);
  const [model, setModel] = useState("");
  const [summary, setSummary] = useState<{ key: string; value: Summary } | null>(null);
  const [scores, setScores] = useState<{ key: string; rows: ScoreRow[] } | null>(null);
  const [error, setError] = useState("");
  const [role, setRole] = useState("coordinated");
  // Comparison runs hold the chosen model; the others hold one (or a chain of retrained ones).
  const comparisonModels = useMemo(
    () => (run as unknown as { models?: { model_id: string; label: string }[] })?.models || [],
    [run],
  );
  const modelId =
    activeKind === "comparison"
      ? comparisonModels.some((m) => m.model_id === model)
        ? model
        : comparisonModels[0]?.model_id || ""
      : "";
  const key = runId ? `${runId}:${modelId}` : "";
  useEffect(() => {
    let stop = false;
    if (!key) return;
    const [id, m] = key.split(":");
    const q = m ? "?model_id=" + encodeURIComponent(m) : "";
    Promise.all([api<Summary>(`/runs/${id}/metrics${q}`), api<{ rows: ScoreRow[] }>(`/runs/${id}/scores${q}`)])
      .then(([s, sc]) => {
        if (stop) return;
        setSummary({ key, value: s });
        setScores({ key, rows: sc.rows });
        setError("");
      })
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [key]);
  const loaded = summary?.key === key ? summary.value : null;
  const s = loaded && role === "specialist" ? loaded.specialist || loaded : loaded;
  const rows = scores?.key === key ? scores.rows : [];
  const h = s?.horizons || [];
  const d7 = h[6];
  const missVerdict =
    d7?.mae_usdt == null || d7.baseline_mae_usdt == null
      ? null
      : d7.mae_usdt < d7.baseline_mae_usdt * 0.99
        ? (["good", "Better than “stays put”"] as const)
        : d7.mae_usdt > d7.baseline_mae_usdt * 1.01
          ? (["miss", "Worse than “stays put”"] as const)
          : (["warn", "Same as “stays put”"] as const);
  const cov = d7?.coverage;
  const covVerdict =
    cov == null
      ? null
      : Math.abs(cov - 0.8) <= 0.05
        ? (["good", "On target"] as const)
        : cov < 0.8
          ? (["miss", "Too narrow"] as const)
          : (["warn", "Wider than needed"] as const);
  const dir = s?.weekly.direction_accuracy ?? null;
  const day7 = rows.map((r) => r.points[6]);
  const scored7 = day7.filter((p) => p.error != null && p.baseline_error != null);
  const closer = scored7.filter((p) => p.error! <= p.baseline_error!).length;
  const allMiss = rows.filter((r) => r.points.filter((p) => p.covered === false).length >= 6).map((r) => r.origin);
  const decisions = state.decisions
    .filter((d) => (d as unknown as { run_id?: string }).run_id === runId)
    .sort((a, b) => (a.clock || "").localeCompare(b.clock || ""));
  const switched = decisions.filter((d) => d.promoted).length;
  const maxMae = Math.max(1, ...h.flatMap((x) => [x.mae_usdt || 0, x.baseline_mae_usdt || 0])) * 1.05;
  const cal = (s?.probability_calibration || []).filter((c) => c.sample_count > 0 && c.predicted_positive != null && c.actual_positive != null);
  const calMax = Math.max(1, ...cal.map((c) => c.sample_count));
  const scoredN = s?.scorable_target_count ?? 0,
    pendingN = s?.pending_target_count ?? 0,
    missingN = s?.unscorable_target_count ?? 0;
  const numbers = s && (
    <div className="v-card v-details">
      <table className="comparison-table">
        <thead>
          <tr>
            <th>Days ahead</th>
            <th>n</th>
            <th>MAE USDT</th>
            <th>95% range of MAE</th>
            <th>Return error pp</th>
            <th>Coverage</th>
            <th>Width USDT</th>
            <th>Interval score</th>
            <th>No-change MAE</th>
            <th>No-change score</th>
          </tr>
        </thead>
        <tbody>
          {h.map((x) => (
            <tr key={x.horizon_hours}>
              <td>{x.horizon_hours / 24}</td>
              <td>{x.sample_count}</td>
              <td>{fmt(x.mae_usdt)}</td>
              <td>{x.mae_95pct_block_bootstrap?.map((v) => fmt(v)).join("–") || "—"}</td>
              <td>{fmt(x.return_mae_percentage_points, 2)}</td>
              <td>{x.coverage == null ? "—" : fmt(x.coverage * 100, 1) + "%"}</td>
              <td>{fmt(x.width_usdt)}</td>
              <td>{fmt(x.interval_score_usdt)}</td>
              <td>{fmt(x.baseline_mae_usdt)}</td>
              <td>{fmt(x.baseline_interval_score_usdt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="v-sub">
        Brier score {fmt(s.weekly.brier_score, 3)} vs frequency baseline {fmt(s.weekly.baseline_brier_score, 3)}. {s.uncertainty_method} {s.baseline}
      </p>
    </div>
  );
  return (
    <main className="forecast-view v-page">
      <header className="v-header">
        <h1>How good is it?</h1>
        {kinds.length > 0 && (
          <div className="v-seg" role="tablist" aria-label="Test run">
            {kinds.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={activeKind === k} className={activeKind === k ? "on" : ""} onClick={() => setKind(k)}>
                {label}
              </button>
            ))}
          </div>
        )}
        {run && (
          <span className="v-muted small">
            {s?.forecast_count ?? "…"} test days, {shortDate(run.start)} – {shortDate(new Date(Date.parse(run.end) - 3600e3).toISOString(), true)}
          </span>
        )}
        <div className="v-grow" />
        {ofKind.length > 1 && (
          <label className="v-pill">
            <span className="v-muted">Run</span>
            <select aria-label="Replay run" value={runId} onChange={(e) => setRunChoice(e.target.value)}>
              {ofKind.map((r) => (
                <option key={r.id} value={r.id}>
                  {shortDate(r.created_at, true)} {new Date(r.created_at).toISOString().slice(11, 16)}
                </option>
              ))}
            </select>
          </label>
        )}
        {activeKind === "comparison" && comparisonModels.length > 0 && (
          <label className="v-pill">
            <span className="v-muted">Model</span>
            <select aria-label="Model" value={modelId} onChange={(e) => setModel(e.target.value)}>
              {comparisonModels.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="v-pill">
          <span className="v-muted">Output</span>
          <select aria-label="Component" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="coordinated">Published</option>
            <option value="specialist">Specialist</option>
          </select>
        </label>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!runs.length ? (
        <section className="v-card v-empty">
          <h2>Nothing tested yet</h2>
          <p className="v-sub">Use Train &amp; Compare in the Forecast Lab. Results appear here once a test run is saved.</p>
        </section>
      ) : !s ? (
        <section className="v-card v-empty">
          <h2>Loading results…</h2>
        </section>
      ) : (
        <div className="v-stage eval-stage">
          <div className="v-grid3 eval-verdicts">
            <Card
              title="Typical miss"
              aside={missVerdict && <Badge tone={missVerdict[0]}>{missVerdict[1]}</Badge>}
              sub="USDT, by days ahead · model vs no-change"
              label="Typical miss"
            >
              <PairBars
                model={h.map((x) => x.mae_usdt)}
                baseline={h.map((x) => x.baseline_mae_usdt)}
                max={maxMae}
                label={`Typical miss from day 1 to day 7: model ${h.map((x) => fmt(x.mae_usdt)).join(", ")}; no-change ${h.map((x) => fmt(x.baseline_mae_usdt)).join(", ")}`}
              />
              <Legend
                items={[
                  { color: C.accent, label: "Model" },
                  { color: C.base, label: "“Stays put”" },
                ]}
              />
            </Card>
            <Card
              title="Do the ranges hold?"
              aside={covVerdict && <Badge tone={covVerdict[0]}>{covVerdict[1]}</Badge>}
              sub="Share of real prices inside the 80% range"
              label="Range reliability"
            >
              <PairBars
                model={h.map((x) => x.coverage)}
                baseline={h.map((x) => x.baseline_coverage)}
                color={C.good}
                max={1}
                target={0.8}
                label={`Coverage from day 1 to day 7: ${h.map((x) => fmt((x.coverage || 0) * 100)).join(", ")} percent`}
              />
              <Legend
                items={[
                  { color: C.good, label: "Model" },
                  { color: C.base, label: "“Stays put” range" },
                ]}
              />
            </Card>
            <Card
              title="Up or down, right?"
              aside={dir == null ? null : dir >= 0.55 ? <Badge tone="good">Useful</Badge> : <Badge tone="idle">Coin flip</Badge>}
              sub={`Day-7 direction calls, ${s.weekly.sample_count} scored days`}
              label="Direction"
            >
              <Gauge value={dir} label={`${fmt((dir || 0) * 100)} percent of direction calls right`} />
            </Card>
          </div>
          <Dock
            id="eval-main"
            label="Every forecast"
            className="eval-dock-main"
            panes={[
          rows.length > 0 && {
            id: "hits",
            label: "Range hits",
            content: (
            <Card
              title="Did the real price land in the range?"
              aside={
                <Legend
                  items={[
                    { color: C.accent, label: "Inside" },
                    { color: C.miss, label: "Outside" },
                    { color: C.idle, label: "Not known yet" },
                  ]}
                />
              }
              label="Every forecast, every day ahead"
            >
              <div className="v-heat">
                {[0, 1, 2, 3, 4, 5, 6].map((i) => [
                  <span key={"l" + i} className="v-num">
                    day {i + 1}
                  </span>,
                  <div key={"r" + i} className="v-heat-row" style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}>
                    {rows.map((r) => {
                      const p = r.points[i];
                      return (
                        <div
                          key={r.forecast_id}
                          className={`hm ${p.covered === true ? "h1" : p.covered === false ? "h0" : "hp"}`}
                          title={`Made ${shortDate(r.origin, true)}, day ${i + 1}: ${
                            p.covered == null
                              ? p.state === "unscorable"
                                ? "target hour missing"
                                : "not known yet"
                              : `${p.covered ? "inside" : "outside"} (actual ${fmt(p.actual)}, range ${fmt(p.lower)}–${fmt(p.upper)})`
                          }`}
                        />
                      );
                    })}
                  </div>,
                ])}
                <span />
                <TickRow start={rows[0].origin} end={new Date(Date.parse(rows[rows.length - 1].origin) + 86400e3).toISOString()} />
              </div>
              {allMiss.length > 0 && (
                <p className="v-sub">
                  Orange columns are sudden moves: forecasts made {dateRuns(allMiss).join(", ")} missed at six or seven of the seven days.
                </p>
              )}
            </Card>
            ),
          },
          scored7.length > 0 && {
            id: "miss",
            label: "Day-7 miss over time",
            content: (
            <Card
              title="Day-7 miss over time"
              aside={
                <span className="v-muted small">
                  model closer on {closer} of {scored7.length} days
                </span>
              }
              label="Day-7 miss over time"
            >
              <TwoLines
                a={day7.map((p) => p.error)}
                b={day7.map((p) => p.baseline_error)}
                label="Day-7 miss in USDT for the model and for no-change, by forecast date"
              />
              <Legend
                items={[
                  { color: C.accent, label: "Model", shape: "line" },
                  { color: "#8193A8", label: "“Stays put”", shape: "line" },
                ]}
              />
            </Card>
            ),
          },
          {
            id: "numbers",
            label: "All numbers",
            content: numbers,
          },
            ]}
          />
          <Dock
            id="eval-side"
            label="Run details"
            className="eval-dock-side"
            panes={[
          {
            id: "honesty",
            label: "Probabilities",
            content: (
            <Card title="When it says 60%, is it 60%?" sub="Bubble size = number of forecasts · on the dashed line = honest" label="Probability honesty">
              <svg viewBox="0 0 250 200" className="v-block" role="img" aria-label={cal.map((c) => `${c.sample_count} forecasts said ${fmt((c.predicted_positive || 0) * 100)} percent, ${fmt((c.actual_positive || 0) * 100)} percent rose`).join("; ")}>
                <rect x="30" y="10" width="200" height="160" fill="#0F1E33" rx="6" />
                <line x1="30" y1="170" x2="230" y2="10" stroke={C.base} strokeDasharray="4 4" />
                {cal.map((c, i) => {
                  const x = 30 + (c.predicted_positive || 0) * 200,
                    y = 170 - (c.actual_positive || 0) * 160;
                  const r = 5 + 17 * Math.sqrt(c.sample_count / calMax);
                  const off = Math.abs((c.actual_positive || 0) - (c.predicted_positive || 0)) > 0.1;
                  const col = off ? C.miss : C.accent;
                  return (
                    <g key={i}>
                      <circle cx={x} cy={y} r={r} fill={col} fillOpacity="0.5" stroke={col}>
                        <title>{`${c.sample_count} forecasts said ${fmt(c.lower * 100)}–${fmt(c.upper * 100)}% (avg ${fmt((c.predicted_positive || 0) * 100)}%); ${fmt((c.actual_positive || 0) * 100)}% actually rose`}</title>
                      </circle>
                      <text x={Math.min(x + r + 3, 200)} y={y + 4} fill={off ? "#F7B37A" : "#B9C8D8"} fontSize="10" className="v-num">
                        {c.sample_count}
                      </text>
                    </g>
                  );
                })}
                <text x="130" y="190" textAnchor="middle" fill={C.dim} fontSize="10">
                  said it would rise
                </text>
                <text x="14" y="90" textAnchor="middle" fill={C.dim} fontSize="10" transform="rotate(-90 14 90)">
                  actually rose
                </text>
              </svg>
              <p className="v-sub">{s.calibration_status}</p>
            </Card>
            ),
          },
          {
            id: "retraining",
            label: "Retraining",
            content: activeKind === "adaptive" ? (
              <Card
                title="Monthly retrain checks"
                aside={
                  <Badge tone={switched ? "good" : "idle"}>
                    {switched} of {decisions.length} switched
                  </Badge>
                }
                sub="A new model replaces the current one only if it wins. Shorter bar = smaller miss."
                label="Monthly retraining checks"
              >
                <div className="v-checks-list">
                  {decisions.map((d) => {
                    const x = d as unknown as {
                      candidate_metrics?: { mae_usdt?: number };
                      incumbent_metrics?: { mae_usdt?: number };
                      baseline_mae_usdt?: number;
                    };
                    const vals = [x.candidate_metrics?.mae_usdt || 0, x.incumbent_metrics?.mae_usdt || 0, x.baseline_mae_usdt || 0];
                    const top = Math.max(1, ...vals);
                    return (
                      <div key={d.id} title={d.reason}>
                        <span className="v-num">{shortDate(d.clock || d.created_at)}</span>
                        <div>
                          {vals.map((v, i) => (
                            <i key={i} style={{ width: `${(100 * v) / top}%`, background: [C.test, C.accent, C.base][i] }} title={fmt(v)} />
                          ))}
                        </div>
                        <span className="small">{d.promoted ? "switched" : "kept current"}</span>
                      </div>
                    );
                  })}
                  {!decisions.length && <p className="v-sub">No retraining checks recorded in this run.</p>}
                </div>
                <Legend
                  items={[
                    { color: C.test, label: "New" },
                    { color: C.accent, label: "Current" },
                    { color: C.base, label: "“Stays put”" },
                  ]}
                />
              </Card>
            ) : (
              <Card title="One model, never retrained" sub="This run keeps the same model for every test day, so there are no retraining checks." label="Retraining">
                <div className="v-pills">
                  <span>{activeKind === "comparison" ? "Chosen model vs stays put" : "Frozen run"}</span>
                  {run?.development && <span>Development run</span>}
                </div>
                <p className="v-note">{run?.evaluation_label}</p>
              </Card>
            ),
          },
          {
            id: "scored",
            label: "Scored",
            content: (
            <Card title={`${fmt(scoredN + pendingN + missingN)} predicted prices`} label="Scored targets">
              <div className="v-donut-row">
                <Donut
                  size={130}
                  parts={[
                    { value: scoredN, color: C.accent },
                    { value: pendingN, color: "#2A3D55" },
                    { value: missingN, color: "#F87171" },
                  ]}
                  center={`${fmt((100 * scoredN) / Math.max(1, scoredN + pendingN + missingN), 1)}%`}
                  label={`${scoredN} scored, ${pendingN} waiting, ${missingN} could not be scored`}
                />
                <div className="v-donut-key">
                  <div>
                    <i style={{ background: C.accent }} />
                    <b className="v-num">{fmt(scoredN)}</b>
                    <span className="v-muted">scored</span>
                  </div>
                  <div>
                    <i style={{ background: "#2A3D55" }} />
                    <b className="v-num">{fmt(pendingN)}</b>
                    <span className="v-muted">waiting for the outcome</span>
                  </div>
                  <div>
                    <i style={{ background: "#F87171" }} />
                    <b className="v-num">{fmt(missingN)}</b>
                    <span className="v-muted">missing in data</span>
                  </div>
                </div>
              </div>
            </Card>
            ),
          },
            ]}
          />
        </div>
      )}
    </main>
  );
}
