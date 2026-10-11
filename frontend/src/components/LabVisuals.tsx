import { useState } from "react";
import type { Detail } from "../forecastTypes";
import { Badge, C, Card, Sparkline, fmt, kfmt, shortDate } from "./viz";
import { InspectEvidence } from "./EvidencePanel";

const ts = (s: string) => Date.parse(s) / 1000;

export type Overlay = {
  model_id: string;
  label: string;
  color: string;
  points: { time: number; value: number }[];
};

// History, then the focused model's 80% fan and median, with other models' medians as thin lines.
export function FanChart({
  detail,
  color = C.accent,
  others = [],
  width = 760,
}: {
  detail: Detail;
  color?: string;
  others?: Overlay[];
  // Drawing width for a 340-high canvas; wider boxes get a wider chart, not a smaller one.
  width?: number;
}) {
  const f = detail.forecast;
  const origin = ts(f.origin);
  const hist = detail.history.filter((p) => p.time <= origin);
  const actual = detail.actuals.filter((p) => p.time > origin);
  const pts = f.points.map((p) => ({ t: ts(p.target), m: p.median, l: p.lower, u: p.upper }));
  const t0 = hist[0]?.time ?? origin - 86400;
  const t1 = pts[pts.length - 1].t;
  const values = [
    ...hist.map((p) => p.close),
    ...pts.flatMap((p) => [p.l, p.u]),
    ...actual.map((p) => p.close),
    ...others.flatMap((o) => o.points.map((p) => p.value)),
  ];
  const span = Math.max(...values) - Math.min(...values) || 1;
  const lo = Math.min(...values) - span * 0.06,
    hi = Math.max(...values) + span * 0.06;
  const W = width - 60;
  const X = (t: number) => 4 + ((t - t0) / Math.max(1, t1 - t0)) * (W - 8);
  const Y = (v: number) => 304 - ((v - lo) / (hi - lo)) * 290;
  const ox = X(origin),
    oy = Y(f.origin_price);
  const line = (p: { x: number; y: number }[]) => "M" + p.map((q) => `${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(" L");
  const histLine = line(hist.map((p) => ({ x: X(p.time), y: Y(p.close) })));
  const up = [{ x: ox, y: oy }, ...pts.map((p) => ({ x: X(p.t), y: Y(p.u) }))];
  const low = [{ x: ox, y: oy }, ...pts.map((p) => ({ x: X(p.t), y: Y(p.l) }))];
  const med = [{ x: ox, y: oy }, ...pts.map((p) => ({ x: X(p.t), y: Y(p.m) }))];
  const band = line(up) + " L" + low.slice().reverse().map((q) => `${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(" L") + " Z";
  const step = (() => {
    const raw = (hi - lo) / 4;
    const mag = 10 ** Math.floor(Math.log10(raw));
    return [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= raw) || raw;
  })();
  const grid: number[] = [];
  for (let g = Math.ceil(lo / step) * step; g < hi; g += step) grid.push(g);
  const last = pts[pts.length - 1];
  const dx = X(last.t),
    dy = Y(last.m);
  const tipX = Math.max(0, dx - 120),
    tipY = dy - 62 < 4 ? dy + 16 : dy - 62;
  const labels = [t0, t0 + (origin - t0) / 2, origin, t1];
  return (
    <svg viewBox={`0 0 ${width} 340`} className="v-block" role="img" aria-label={`Price before ${shortDate(f.origin)}, then the 80 percent range for the next 7 days`}>
      <defs>
        <linearGradient id="fanfill" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={color} stopOpacity="0.38" />
          <stop offset="1" stopColor={color} stopOpacity="0.14" />
        </linearGradient>
        <linearGradient id="histfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7FA7D1" stopOpacity="0.22" />
          <stop offset="1" stopColor="#7FA7D1" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x={ox} y="8" width={W - ox} height="300" fill="#0F2236" />
      {grid.map((g) => (
        <g key={g}>
          <line x1="0" x2={W} y1={Y(g)} y2={Y(g)} stroke="#14263C" />
          <text x={W + 6} y={Y(g) + 4} fill={C.dim} fontSize="11" className="v-num">
            {kfmt(g)}
          </text>
        </g>
      ))}
      {hist.length > 1 && (
        <>
          <path d={`${histLine} L${ox} 308 L${X(hist[0].time)} 308 Z`} fill="url(#histfill)" />
          <path d={histLine} fill="none" stroke="#9FC0E3" strokeWidth="2" strokeLinejoin="round" />
        </>
      )}
      <path d={band} fill="url(#fanfill)" />
      <path d={line(up)} fill="none" stroke={color} strokeOpacity="0.5" />
      <path d={line(low)} fill="none" stroke={color} strokeOpacity="0.5" />
      {others.map((o) => (
        <path
          key={o.model_id}
          d={line([{ x: ox, y: oy }, ...o.points.filter((p) => p.time > origin).map((p) => ({ x: X(p.time), y: Y(p.value) }))])}
          fill="none"
          stroke={o.color}
          strokeOpacity="0.55"
          strokeWidth="1.2"
        >
          <title>{o.label}</title>
        </path>
      ))}
      {actual.length > 0 && (
        <path d={line([{ x: ox, y: oy }, ...actual.map((p) => ({ x: X(p.time), y: Y(p.close) }))])} fill="none" stroke={C.text} strokeWidth="2" />
      )}
      <path d={line(med)} fill="none" stroke={color} strokeWidth="2.5" />
      <line x1={ox} x2={ox} y1="8" y2="308" stroke={C.text} strokeOpacity="0.5" strokeDasharray="3 4" />
      <text x={ox - 8} y="24" fill="#B9C8D8" fontSize="11" fontWeight="700" textAnchor="end">
        FORECAST START
      </text>
      <text x={ox + 8} y="24" fill={color} fontSize="11" fontWeight="700">
        NEXT 7 DAYS
      </text>
      {pts.map((p, i) => (
        <circle key={i} cx={X(p.t)} cy={Y(p.m)} r={i === 6 ? 6 : 3.5} fill={color} stroke="#0B1626" strokeWidth="2">
          <title>{`Day ${i + 1} · ${shortDate(p.t)} · ${fmt(p.m)} (80%: ${fmt(p.l)}–${fmt(p.u)})`}</title>
        </circle>
      ))}
      <circle cx={ox} cy={oy} r="5" fill={C.text} />
      <rect x={tipX} y={tipY} width="112" height="44" rx="10" fill={C.text} />
      <text x={tipX + 56} y={tipY + 22} textAnchor="middle" fill="#0B1626" fontSize="14" className="v-num">
        {fmt(last.m)}
      </text>
      <text x={tipX + 56} y={tipY + 37} textAnchor="middle" fill="#3B5068" fontSize="10" fontWeight="700">
        {shortDate(last.t)} · day 7
      </text>
      {labels.map((t, i) => (
        <text key={i} x={X(t)} y="330" fill={C.dim} fontSize="11" textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}>
          {shortDate(t)}
        </text>
      ))}
    </svg>
  );
}

// Where the day-7 price probably lands, relative to the starting price.
export function DaySevenCard({ detail }: { detail: Detail }) {
  const f = detail.forecast;
  const p = f.points[6];
  const lo = Math.min(p.lower, f.origin_price),
    hi = Math.max(p.upper, f.origin_price);
  const X = (v: number) => 10 + ((v - lo) / Math.max(1, hi - lo)) * 280;
  const ev = detail.evaluation?.points[6];
  const actual = ev?.state === "evaluated" ? ev.actual_price : undefined;
  return (
    <Card title={`Where ${shortDate(p.target)} probably lands`} label="Day seven range">
      <svg viewBox="0 0 300 76" className="v-block" role="img" aria-label={`80 percent range ${fmt(p.lower)} to ${fmt(p.upper)}; most likely ${fmt(p.median)}; start ${fmt(f.origin_price)}`}>
        <rect x={X(p.lower)} y="30" width={Math.max(2, X(p.upper) - X(p.lower))} height="14" rx="7" fill={C.accent} fillOpacity="0.35" />
        <line x1={X(f.origin_price)} x2={X(f.origin_price)} y1="22" y2="52" stroke={C.text} strokeWidth="2" />
        <text x={X(f.origin_price)} y="15" fill={C.text} fontSize="10" fontWeight="700" textAnchor={X(f.origin_price) > 150 ? "end" : "start"}>
          start {kfmt(f.origin_price)}
        </text>
        <circle cx={X(p.median)} cy="37" r="8" fill={C.accent} stroke="#0B1626" strokeWidth="3" />
        {actual != null && (
          <rect x={X(actual) - 2} y="24" width="4" height="26" rx="2" fill={actual >= p.lower && actual <= p.upper ? C.text : C.miss}>
            <title>{`Actual ${fmt(actual)}`}</title>
          </rect>
        )}
        <text x={X(p.lower)} y="68" fill={C.muted} fontSize="11" className="v-num">
          {kfmt(p.lower)}
        </text>
        <text x={X(p.upper)} y="68" fill={C.muted} fontSize="11" className="v-num" textAnchor="end">
          {kfmt(p.upper)}
        </text>
      </svg>
      {actual != null && <p className="v-sub">Actual {fmt(actual)} USDT · miss {fmt(ev?.absolute_price_error)}</p>}
    </Card>
  );
}

export function DirectionCard({ detail }: { detail: Detail }) {
  const up = detail.forecast.probabilities.positive;
  const down = 1 - up;
  const tone = Math.abs(up - 0.5) < 0.08 ? "near coin flip" : up > 0.5 ? "leans up" : "leans down";
  return (
    <Card title={`Up or down by ${shortDate(detail.forecast.points[6].target)}?`} aside={<span className="small warn">{tone}</span>} label="Direction">
      <div className="v-updown">
        <div style={{ flex: `${up} 1 0` }}>▲ {fmt(up * 100)}%</div>
        <div style={{ flex: `${down} 1 0` }}>{fmt(down * 100)}% ▼</div>
      </div>
    </Card>
  );
}

export function VersusCard({ model, baseline, n }: { model?: number | null; baseline?: number | null; n?: number }) {
  const max = Math.max(model || 0, baseline || 0, 1);
  const better = model != null && baseline != null && model < baseline * 0.99;
  return (
    <Card
      title="Better than “price stays put”?"
      aside={model == null ? <Badge tone="idle">No scores yet</Badge> : better ? <Badge tone="good">Yes</Badge> : <Badge tone="miss">Not yet</Badge>}
      label="Model versus no-change"
    >
      <div className="v-bars">
        <span>This model</span>
        <i style={{ width: `${(100 * (model || 0)) / max}%`, background: C.accent }} />
        <b className="v-num">{fmt(model)}</b>
        <span>Stays put</span>
        <i style={{ width: `${(100 * (baseline || 0)) / max}%`, background: C.dim }} />
        <b className="v-num">{fmt(baseline)}</b>
      </div>
      <p className="v-sub">Typical day-7 miss in USDT over {n ?? 0} past test days</p>
    </Card>
  );
}

export type ScoreRow = {
  forecast_id: string;
  origin: string;
  model_version: string;
  origin_price: number;
  positive_probability: number;
  points: {
    state: string;
    median: number;
    lower: number;
    upper: number;
    actual: number | null;
    covered: boolean | null;
    error: number | null;
    baseline_error: number | null;
  }[];
};

// One square per test day: was the model or "stays put" closer at day 7?
export function ReplayStrip({
  rows,
  selected,
  onSelect,
  start,
  end,
}: {
  rows: ScoreRow[];
  selected?: string;
  onSelect?: (id: string) => void;
  start: string;
  end: string;
}) {
  const cls = (r: ScoreRow) => {
    const p = r.points[6];
    if (p.error == null || p.baseline_error == null) return p.state === "unscorable" ? "x" : "p";
    return p.error <= p.baseline_error ? "w" : "l";
  };
  const counts = { w: 0, l: 0, p: 0, x: 0 };
  rows.forEach((r) => counts[cls(r)]++);
  return (
    <div>
      <div className="v-legend right">
        <span>
          <i className="box" style={{ background: C.accent }} />
          Model closer · {counts.w}
        </span>
        <span>
          <i className="box" style={{ background: C.miss }} />
          “Stays put” closer · {counts.l}
        </span>
        <span>
          <i className="box" style={{ background: C.idle }} />
          Not known yet · {counts.p + counts.x}
        </span>
      </div>
      <div className="v-days" style={{ gridTemplateColumns: `repeat(${Math.max(1, rows.length)}, minmax(0, 1fr))` }}>
        {rows.map((r) => {
          const c = cls(r);
          const p = r.points[6];
          return (
            <button
              key={r.forecast_id}
              className={`v-day ${c} ${selected === r.forecast_id ? "sel" : ""}`}
              title={`${shortDate(r.origin, true)}: ${
                c === "w"
                  ? `model closer (miss ${fmt(p.error)} vs ${fmt(p.baseline_error)})`
                  : c === "l"
                    ? `"stays put" closer (miss ${fmt(p.error)} vs ${fmt(p.baseline_error)})`
                    : "outcome not known yet"
              }`}
              aria-label={`Forecast made ${shortDate(r.origin, true)}`}
              onClick={() => onSelect?.(r.forecast_id)}
            />
          );
        })}
      </div>
      <TickRow start={start} end={end} />
    </div>
  );
}

export function TickRow({ start, end }: { start: string; end: string }) {
  const s = Date.parse(start),
    e = Date.parse(end) - 86400e3;
  const ticks = [s];
  const d = new Date(s);
  d.setUTCMonth(d.getUTCMonth() + 1, 1);
  while (d.getTime() < e) {
    ticks.push(d.getTime());
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  ticks.push(e);
  return (
    <div className="v-ticks">
      {ticks.map((t) => (
        <span key={t}>{shortDate(t / 1000)}</span>
      ))}
    </div>
  );
}

// Seven daily ranges as vertical bars, with the starting price and any known outcomes.
export function SevenRanges({ detail }: { detail: Detail }) {
  const f = detail.forecast;
  const ev = detail.evaluation?.points || [];
  const vals = [f.origin_price, ...f.points.flatMap((p) => [p.lower, p.upper]), ...ev.flatMap((e) => (e.actual_price != null ? [e.actual_price] : []))];
  const lo = Math.min(...vals),
    hi = Math.max(...vals);
  const Y = (v: number) => 150 - ((v - lo) / Math.max(1, hi - lo)) * 136;
  return (
    <svg viewBox="0 0 540 172" className="v-block" role="img" aria-label="Seven daily 80 percent ranges">
      <line x1="0" x2="540" y1={Y(f.origin_price)} y2={Y(f.origin_price)} stroke={C.text} strokeOpacity="0.35" strokeDasharray="3 4" />
      <text x="0" y={Y(f.origin_price) - 6} fill={C.muted} fontSize="10" fontWeight="700">
        start {fmt(f.origin_price)}
      </text>
      {f.points.map((p, i) => {
        const x = 70 + i * 66;
        const e = ev[i];
        return (
          <g key={p.target}>
            <rect x={x} y={Y(p.upper)} width="34" height={Math.max(2, Y(p.lower) - Y(p.upper))} rx="8" fill={C.accent} fillOpacity="0.28">
              <title>{`Day ${i + 1}: ${fmt(p.lower)}–${fmt(p.upper)}, most likely ${fmt(p.median)}`}</title>
            </rect>
            <circle cx={x + 17} cy={Y(p.median)} r="5" fill={C.accent} />
            {e?.state === "evaluated" && e.actual_price != null && (
              <rect x={x + 3} y={Y(e.actual_price) - 2} width="28" height="4" rx="2" fill={e.interval_coverage ? C.text : C.miss}>
                <title>{`Actual ${fmt(e.actual_price)}`}</title>
              </rect>
            )}
            <text x={x + 17} y="168" textAnchor="middle" fill={C.dim} fontSize="11">
              Day {i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const tone = (status: string) =>
  /^(Ready|Complete|Saved|Approved)$/.test(status)
    ? "ok"
    : /^(Rejected|Failed|Unscorable|Not trained)$/.test(status)
      ? "bad"
      : /^(Waiting|Pending|Partial)$/.test(status)
        ? "idle"
        : "busy";

export function AgentStrip({
  detail,
  onInspect,
}: {
  detail: Detail;
  onInspect: () => void;
}) {
  const a = detail.agents;
  const items: [string, string][] = [
    ["Price & Volume Specialist", a.specialist],
    ["Coordinator", a.coordinator],
    ["Publisher", a.publisher],
    ["Evaluator", a.evaluator],
  ];
  return (
    <nav className="v-agents" aria-label="Agent pipeline for the focused model">
      {items.map(([name, status]) => (
        <button key={name} onClick={onInspect} aria-label={`Inspect ${name}: ${status}`}>
          <i className={`v-dot ${tone(status)}`} />
          <span>
            <span className="name">{name}</span>
            <span className={`status ${tone(status)}`}>{status}</span>
          </span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.dim} strokeWidth="2" aria-hidden="true">
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      ))}
    </nav>
  );
}

// Read-only look at one saved forecast. Opening it never trains or re-predicts.
export function InspectDrawer({ detail, label, onClose }: { detail: Detail; label?: string; onClose: () => void }) {
  const [tab, setTab] = useState("Overview");
  const f = detail.forecast,
    m = detail.model;
  const origin = ts(f.origin);
  const before = detail.history.filter((p) => p.time <= origin).map((p) => p.close);
  const features = Object.entries(f.input_summary.feature_values || {});
  const defs = m.feature_definitions || {};
  const ev = detail.evaluation?.points || [];
  const scored = ev.filter((e) => e.state === "evaluated");
  return (
    <div className="v-drawer-backdrop" onClick={onClose}>
      <aside className="v-drawer" aria-label={`Inspect ${label || m.family}`} onClick={(e) => e.stopPropagation()}>
        <header>
          <span className="v-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M3 17l5-6 4 3 6-8" />
              <path d="M3 21h18" />
            </svg>
          </span>
          <div>
            <h2>{label || "Price & Volume Specialist"}</h2>
            <span className={`status ${tone(detail.agents.specialist)}`}>
              <i className={`v-dot ${tone(detail.agents.specialist)}`} />
              {detail.agents.specialist} · forecast {detail.agents.publisher.toLowerCase()}
            </span>
          </div>
          <div className="v-grow" />
          <button className="v-icon-btn" aria-label="Close" onClick={onClose}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="v-seg" role="tablist">
          {["Overview", "Inputs", "Scores", "Evidence"].map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        {tab === "Overview" && (
          <>
            <Card title="What it read" aside={<span className="v-muted small">last {detail.history_days} days before {shortDate(f.origin)}</span>}>
              <Sparkline values={before} label={`Price over the ${detail.history_days} days before ${shortDate(f.origin)}`} />
              <div className="v-pills">
                <span>{features.length} signals from price &amp; volume</span>
                <span>{f.input_summary.lookback_days}-day look-back</span>
                <span>
                  <i className={`v-dot ${f.quality_flags.length ? "idle" : "ok"}`} />
                  {f.quality_flags.length ? f.quality_flags.join(", ") : "No gaps in window"}
                </span>
              </div>
            </Card>
            <Card title="What it said" aside={<span className="v-muted small">80% range per day · USDT</span>}>
              <SevenRanges detail={detail} />
            </Card>
          </>
        )}
        {tab === "Inputs" && (
          <Card title="Signals at the forecast start" sub="Values the model saw, computed only from candles closed before the start.">
            <div className="v-features">
              {features.map(([k, v]) => (
                <div key={k} title={defs[k] || k}>
                  <span>{defs[k] ? defs[k].split(/[.;(]/)[0] : k}</span>
                  <b className="v-num">{fmt(v, Math.abs(v) < 10 ? 4 : 1)}</b>
                </div>
              ))}
            </div>
          </Card>
        )}
        {tab === "Scores" && (
          <Card title={`${scored.length} of 7 days scored`} sub={detail.evaluation ? `Outcomes known through ${shortDate(detail.evaluation.clock, true)}` : "No outcomes known yet"}>
            <div className="v-targets">
              {f.points.map((p, i) => {
                const e = ev[i];
                const st = e?.state === "evaluated" ? (e.interval_coverage ? "inside" : "outside") : e?.state === "unscorable" ? "missing" : "waiting";
                return (
                  <div key={p.target} className={st}>
                    <span>
                      Day {i + 1} · {shortDate(p.target)}
                    </span>
                    <b className="v-num">{fmt(p.median)}</b>
                    <small>
                      {st === "waiting"
                        ? "Outcome not known yet"
                        : st === "missing"
                          ? "Target hour missing in data"
                          : `Actual ${fmt(e?.actual_price)} · miss ${fmt(e?.absolute_price_error)}`}
                    </small>
                  </div>
                );
              })}
            </div>
          </Card>
        )}
        {tab === "Evidence" && (
          <Card title="Evidence and provenance" sub="Read from the saved records; opening this never re-predicts.">
            <InspectEvidence id={f.id} />
          </Card>
        )}
        <div className="v-pills">
          <span>🔒 Saved · cannot change</span>
          <span>Learned from data before {shortDate(m.training_cutoff, true)}</span>
          <span>Dataset {m.dataset_version.slice(0, 8)}</span>
          <span>Model {m.id}</span>
          <span>{f.mode === "prediction" ? "Prediction" : `${f.mode} run`}</span>
        </div>
      </aside>
    </div>
  );
}
