import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

export type ChartPoint = { time: number; value: number };
export type ChartSeries = {
  id: string;
  label: string;
  color: string;
  points: ChartPoint[];
  width?: 1 | 2 | 3;
  dashed?: boolean;
  // Expected spacing in seconds; a longer jump is drawn as a break, never bridged.
  step?: number;
  // Hidden from the tooltip (for example the two edges of a range).
  quiet?: boolean;
};

const label = (t: number) =>
  new Date(t * 1000).toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }) + " UTC";

// Missing prices stay missing: insert an empty slot where the series skips a step.
function withGaps(points: ChartPoint[], step?: number) {
  const out: ({ time: UTCTimestamp; value: number } | { time: UTCTimestamp })[] = [];
  points.forEach((p, i) => {
    const prev = points[i - 1];
    if (prev && step && p.time - prev.time > step * 1.5)
      out.push({ time: (prev.time + step) as UTCTimestamp });
    out.push({ time: p.time as UTCTimestamp, value: p.value });
  });
  return out;
}

// One pan/zoom line chart. Series are updated in place, so toggling a model keeps the zoom.
export function LabChart({
  series,
  divider,
  fitKey,
  onPick,
}: {
  series: ChartSeries[];
  divider?: { time: number; label: string };
  fitKey: string;
  onPick?: (time: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lines = useRef(new Map<string, ISeriesApi<"Line">>());
  const latest = useRef({ series, divider, onPick });
  const fitted = useRef("");
  const [tip, setTip] = useState("");
  const [dividerAt, setDividerAt] = useState<{ x: number; flip: boolean } | null>(null);
  useLayoutEffect(() => {
    latest.current = { series, divider, onPick };
  });

  useEffect(() => {
    const el = box.current!;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 360,
      layout: { background: { color: "#0B1626" }, textColor: "#93A7BD", fontSize: 12 },
      grid: { vertLines: { color: "#13243A" }, horzLines: { color: "#13243A" } },
      rightPriceScale: { borderColor: "#172A42" },
      timeScale: { borderColor: "#172A42", timeVisible: true, minBarSpacing: 0.001 },
      crosshair: { mode: 1 },
      localization: { priceFormatter: (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 0 }) },
    });
    chartRef.current = chart;
    const map = lines.current;
    const place = () => {
      const d = latest.current.divider;
      const x = d ? chart.timeScale().timeToCoordinate(d.time as UTCTimestamp) : null;
      setDividerAt(x == null ? null : { x, flip: x > el.clientWidth - 260 });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(place);
    chart.subscribeCrosshairMove((p) => {
      if (!p.time) return setTip("");
      const t = Number(p.time);
      const parts = latest.current.series
        .filter((s) => !s.quiet)
        .flatMap((s) => {
          const q = s.points.find((x) => x.time === t);
          return q ? [`${s.label} ${q.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`] : [];
        });
      setTip(parts.length ? `${label(t)} · ${parts.join(" · ")}` : label(t));
    });
    chart.subscribeClick((p) => {
      if (p.time != null) latest.current.onPick?.(Number(p.time));
    });
    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight || 360 });
      place();
    });
    observer.observe(el);
    const reset = () => chart.timeScale().fitContent();
    el.addEventListener("dblclick", reset);
    return () => {
      observer.disconnect();
      el.removeEventListener("dblclick", reset);
      map.clear();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const map = lines.current;
    const wanted = new Set(series.map((s) => s.id));
    for (const [id, line] of map)
      if (!wanted.has(id)) {
        chart.removeSeries(line);
        map.delete(id);
      }
    for (const s of series) {
      let line = map.get(s.id);
      if (!line) {
        line = chart.addSeries(LineSeries, { lastValueVisible: false, priceLineVisible: false });
        map.set(s.id, line);
      }
      line.applyOptions({
        color: s.color,
        lineWidth: s.width || 2,
        lineStyle: s.dashed ? LineStyle.Dashed : LineStyle.Solid,
        crosshairMarkerVisible: !s.quiet,
      });
      line.setData(withGaps(s.points, s.step));
    }
    if (fitted.current !== fitKey) {
      fitted.current = fitKey;
      chart.timeScale().fitContent();
    }
    const d = divider;
    const x = d ? chart.timeScale().timeToCoordinate(d.time as UTCTimestamp) : null;
    setDividerAt(x == null ? null : { x, flip: x > (box.current?.clientWidth || 0) - 260 });
  }, [series, fitKey, divider]);

  return (
    <div className="lab-chart">
      <div className="lab-chart-plot">
        <div ref={box} className="lab-chart-canvas" />
        {divider && dividerAt && (
          <div
            className={`lab-divider ${dividerAt.flip ? "flip" : ""}`}
            style={{ left: dividerAt.x }}
            aria-hidden="true"
          >
            <span>{divider.label}</span>
          </div>
        )}
      </div>
      <div className="lab-chart-tip" role="status">
        {tip || "Drag to pan · scroll to zoom · double-click to show everything"}
      </div>
    </div>
  );
}
