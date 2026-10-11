// Small SVG building blocks shared by the visual Dataset, Forecast Lab and Evaluation pages.
import type { ReactNode } from "react";

export const C = {
  accent: "#2DD4E8",
  validation: "#F5A524",
  test: "#A78BFA",
  good: "#34D399",
  warn: "#F7C46A",
  miss: "#F08A4B",
  base: "#53677E",
  idle: "#1B2C42",
  text: "#E8F0F8",
  muted: "#93A7BD",
  dim: "#6E849C",
};

export const fmt = (n: number | null | undefined, d = 0) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : n.toLocaleString("en-US", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      });
export const kfmt = (n: number) =>
  Math.abs(n) >= 1000 ? `${fmt(n / 1000, 1)}k` : fmt(n);
export const shortDate = (s: string | number, year = false) =>
  new Date(typeof s === "number" ? s * 1000 : s).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    ...(year ? { year: "numeric" } : {}),
  });
export const pct = (n: number | null | undefined, d = 0) =>
  n == null ? "—" : `${fmt(n * 100, d)}%`;

export function Card({
  title,
  aside,
  sub,
  children,
  className = "",
  label,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  sub?: ReactNode;
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <section className={`v-card ${className}`} aria-label={label}>
      {(title || aside) && (
        <div className="v-card-head">
          {title && <h2>{title}</h2>}
          {aside}
        </div>
      )}
      {sub && <p className="v-sub">{sub}</p>}
      {children}
    </section>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: "good" | "warn" | "miss" | "idle";
  children: ReactNode;
}) {
  return <span className={`v-badge ${tone}`}>{children}</span>;
}

export function Ring({
  value,
  color = C.good,
  size = 28,
  label,
}: {
  value: number;
  color?: string;
  size?: number;
  label: string;
}) {
  const c = 2 * Math.PI * 14;
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" role="img" aria-label={label}>
      <circle cx="18" cy="18" r="14" fill="none" stroke="#17304A" strokeWidth="5" />
      <circle
        cx="18"
        cy="18"
        r="14"
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeDasharray={`${Math.max(0, Math.min(1, value)) * c} ${c}`}
        transform="rotate(-90 18 18)"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Donut({
  parts,
  center,
  caption,
  size = 140,
  label,
}: {
  parts: { value: number; color: string }[];
  center: string;
  caption?: string;
  size?: number;
  label: string;
}) {
  const c = 2 * Math.PI * 44;
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  let offset = 0;
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" role="img" aria-label={label}>
      <circle cx="60" cy="60" r="44" fill="none" stroke="#13233A" strokeWidth="16" />
      {parts.map((p, i) => {
        const len = (p.value / total) * c;
        const el = (
          <circle
            key={i}
            cx="60"
            cy="60"
            r="44"
            fill="none"
            stroke={p.color}
            strokeWidth="16"
            strokeDasharray={`${len} ${c}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 60 60)"
          />
        );
        offset += len;
        return el;
      })}
      <text x="60" y={caption ? 58 : 65} textAnchor="middle" className="v-num" fontSize="15" fill={C.text}>
        {center}
      </text>
      {caption && (
        <text x="60" y="73" textAnchor="middle" fill={C.muted} fontSize="9">
          {caption}
        </text>
      )}
    </svg>
  );
}

// A horizontal 80% range with its median dot and an optional reference marker.
export function RangeBar({
  lower,
  upper,
  median,
  lo,
  hi,
  marker,
  markerLabel,
  markerColor = C.text,
  height = 24,
}: {
  lower: number;
  upper: number;
  median: number;
  lo: number;
  hi: number;
  marker?: number | null;
  markerLabel?: string;
  markerColor?: string;
  height?: number;
}) {
  const x = (v: number) => (100 * (v - lo)) / Math.max(1e-9, hi - lo);
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="v-range" style={{ height }} aria-hidden="true">
      <rect x="0" y={height / 2 - 1} width="100" height="2" fill="#13243A" />
      <rect
        x={x(lower)}
        y={height / 2 - 7}
        width={Math.max(0.5, x(upper) - x(lower))}
        height="14"
        rx="7"
        fill={C.accent}
        fillOpacity="0.3"
      />
      <rect x={x(median) - 0.4} y={height / 2 - 9} width="0.8" height="18" fill={C.accent} />
      {marker != null && (
        <rect x={x(marker) - 0.5} y="1" width="1" height={height - 2} fill={markerColor}>
          {markerLabel && <title>{markerLabel}</title>}
        </rect>
      )}
    </svg>
  );
}

export function Sparkline({
  values,
  height = 90,
  color = "#9FC0E3",
  label,
}: {
  values: number[];
  height?: number;
  color?: string;
  label: string;
}) {
  if (values.length < 2) return null;
  const lo = Math.min(...values),
    hi = Math.max(...values);
  const X = (i: number) => 4 + (i / (values.length - 1)) * 532;
  const Y = (v: number) => height - 6 - ((v - lo) / Math.max(1e-9, hi - lo)) * (height - 14);
  const line = "M" + values.map((v, i) => `${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(" L");
  return (
    <svg viewBox={`0 0 540 ${height}`} className="v-block" role="img" aria-label={label}>
      <path d={`${line} L${X(values.length - 1)} ${height} L${X(0)} ${height} Z`} fill={color} fillOpacity="0.16" />
      <path d={line} fill="none" stroke={color} strokeWidth="2" />
      <circle cx={X(values.length - 1)} cy={Y(values[values.length - 1])} r="4" fill={C.text} />
    </svg>
  );
}

// Paired columns per horizon: baseline (grey) next to model (colour).
export function PairBars({
  model,
  baseline,
  color = C.accent,
  max,
  target,
  label,
}: {
  model: (number | null | undefined)[];
  baseline: (number | null | undefined)[];
  color?: string;
  max: number;
  target?: number;
  label: string;
}) {
  const H = 120;
  const h = (v: number | null | undefined) => (v == null ? 0 : (Math.min(v, max) / max) * H);
  return (
    <svg viewBox="0 0 300 150" className="v-block" role="img" aria-label={label}>
      {target != null && (
        <>
          <line x1="0" x2="300" y1={132 - (target / max) * H} y2={132 - (target / max) * H} stroke={C.text} strokeOpacity="0.6" strokeDasharray="4 4" />
          <text x="300" y={128 - (target / max) * H} textAnchor="end" fill="#B9C8D8" fontSize="10" fontWeight="700">
            target {fmt(target * 100)}%
          </text>
        </>
      )}
      {model.map((v, i) => {
        const x = 14 + i * 40;
        return (
          <g key={i}>
            <rect x={x} y={132 - h(baseline[i])} width="14" height={h(baseline[i])} rx="3" fill={C.base}>
              <title>{`Day ${i + 1} no-change: ${fmt(baseline[i] ?? null, max <= 1 ? 3 : 0)}`}</title>
            </rect>
            <rect x={x + 15} y={132 - h(v)} width="14" height={h(v)} rx="3" fill={color}>
              <title>{`Day ${i + 1} model: ${fmt(v ?? null, max <= 1 ? 3 : 0)}`}</title>
            </rect>
            <text x={x + 14.5} y="146" textAnchor="middle" fill={C.dim} fontSize="10">
              d{i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function Gauge({ value, label }: { value: number | null; label: string }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  const a = Math.PI * (1 - v);
  const ex = 150 + 110 * Math.cos(a),
    ey = 140 - 110 * Math.sin(a);
  const nx = 150 + 110 * Math.cos(a),
    ny = 140 - 110 * Math.sin(a);
  return (
    <svg viewBox="0 0 300 160" className="v-block" role="img" aria-label={label}>
      <path d="M40 140 A110 110 0 0 1 260 140" fill="none" stroke={C.idle} strokeWidth="22" strokeLinecap="round" />
      {value != null && v > 0 && (
        <path d={`M40 140 A110 110 0 0 1 ${ex.toFixed(1)} ${ey.toFixed(1)}`} fill="none" stroke={v >= 0.55 ? C.good : "#B9C8D8"} strokeWidth="22" strokeLinecap="round" />
      )}
      <circle cx={nx} cy={ny} r="6" fill={C.text} />
      <text x="150" y="128" textAnchor="middle" className="v-num" fill={C.text} fontSize="30">
        {value == null ? "—" : `${fmt(v * 100)}%`}
      </text>
      <text x="34" y="158" textAnchor="middle" fill={C.dim} fontSize="10">
        0%
      </text>
      <text x="266" y="158" textAnchor="middle" fill={C.dim} fontSize="10">
        100%
      </text>
    </svg>
  );
}

// Two lines on a shared scale (for example model miss vs no-change miss over time).
export function TwoLines({
  a,
  b,
  colorA = C.accent,
  colorB = "#8193A8",
  height = 180,
  label,
}: {
  a: (number | null)[];
  b: (number | null)[];
  colorA?: string;
  colorB?: string;
  height?: number;
  label: string;
}) {
  const all = [...a, ...b].filter((v): v is number => v != null);
  if (!all.length) return <p className="v-sub">No scored outcomes yet.</p>;
  const max = Math.max(...all) * 1.05;
  const n = Math.max(a.length, b.length);
  const X = (i: number) => 4 + (i / Math.max(1, n - 1)) * 950;
  const Y = (v: number) => height - 10 - (v / max) * (height - 20);
  const path = (s: (number | null)[]) => {
    let d = "",
      pen = false;
    s.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)} `;
      pen = true;
    });
    return d;
  };
  const step = max > 12000 ? 5000 : max > 4000 ? 2000 : 1000;
  const grid = [];
  for (let g = step; g < max; g += step) grid.push(g);
  return (
    <svg viewBox={`0 0 1000 ${height}`} className="v-block" role="img" aria-label={label}>
      {grid.map((g) => (
        <g key={g}>
          <line x1="0" x2="960" y1={Y(g)} y2={Y(g)} stroke="#14263C" />
          <text x="966" y={Y(g) + 4} fill={C.dim} fontSize="10" className="v-num">
            {kfmt(g)}
          </text>
        </g>
      ))}
      <path d={path(b)} fill="none" stroke={colorB} strokeWidth="1.5" />
      <path d={path(a)} fill="none" stroke={colorA} strokeWidth="2" />
    </svg>
  );
}

export function Legend({ items }: { items: { color: string; label: ReactNode; shape?: "line" | "box" | "dot" }[] }) {
  return (
    <div className="v-legend">
      {items.map((it, i) => (
        <span key={i}>
          <i className={it.shape || "box"} style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

export function MonthTicks({ start, end }: { start: string; end: string }) {
  const s = Date.parse(start),
    e = Date.parse(end);
  const ticks: string[] = [];
  const d = new Date(s);
  while (d.getTime() <= e) {
    ticks.push(shortDate(d.toISOString()));
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  return (
    <div className="v-ticks">
      {ticks.map((t) => (
        <span key={t}>{t}</span>
      ))}
    </div>
  );
}
