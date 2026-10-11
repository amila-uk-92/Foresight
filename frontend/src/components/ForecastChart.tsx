import { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  ColorType,
  LineStyle,
} from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";
import type { Detail } from "../forecastTypes";

interface Props {
  detail: Detail;
  showActuals?: boolean;
  showIntervals?: boolean;
  mini?: boolean;
  clock: number;
  onPoint?: (index: number) => void;
}
export function ForecastChart({
  detail,
  showActuals = true,
  showIntervals = true,
  mini = false,
  clock,
  onPoint,
}: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = useState<{
    polygon: string;
    originX: number | null;
  }>({ polygon: "", originX: null });
  const [tooltip, setTooltip] = useState("");
  useEffect(() => {
    if (!mount.current) return;
    const node = mount.current,
      f = detail.forecast;
    const chart = createChart(node, {
      width: node.clientWidth,
      height: node.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#031427" },
        textColor: "#91a8c0",
        fontSize: 12,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#10283f" },
        horzLines: { color: "#10283f" },
      },
      rightPriceScale: {
        borderColor: "#17354e",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: "#17354e",
        timeVisible: false,
        minBarSpacing: 0.1,
      },
      localization: {
        locale: "en-GB",
        priceFormatter: (p: number) =>
          p.toLocaleString("en-GB", { maximumFractionDigits: 0 }),
      },
    });
    const history = chart.addSeries(LineSeries, {
      color: "#65a4d8",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: "History",
    });
    const median = chart.addSeries(LineSeries, {
      color: "#00e5ef",
      lineWidth: 2,
      pointMarkersVisible: true,
      pointMarkersRadius: 4,
      priceLineVisible: false,
      lastValueVisible: false,
      title: "Median",
    });
    const lower = chart.addSeries(LineSeries, {
      color: "#2891ae",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      visible: showIntervals,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const upper = chart.addSeries(LineSeries, {
      color: "#2891ae",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      visible: showIntervals,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const actual = chart.addSeries(LineSeries, {
      color: "#eab763",
      lineWidth: 2,
      pointMarkersVisible: true,
      visible: showActuals,
      priceLineVisible: false,
      lastValueVisible: false,
      title: "Actual",
    });
    const origin = Date.parse(f.origin) / 1000;
    history.setData(
      detail.history.map((p) => ({
        time: p.time as UTCTimestamp,
        value: p.close,
      })),
    );
    median.setData(
      f.points.map((p) => ({
        time: (Date.parse(p.target) / 1000) as UTCTimestamp,
        value: p.median,
      })),
    );
    lower.setData(
      f.points.map((p) => ({
        time: (Date.parse(p.target) / 1000) as UTCTimestamp,
        value: p.lower,
      })),
    );
    upper.setData(
      f.points.map((p) => ({
        time: (Date.parse(p.target) / 1000) as UTCTimestamp,
        value: p.upper,
      })),
    );
    actual.setData(
      detail.actuals
        .filter((p) => p.time <= clock)
        .map((p) => ({ time: p.time as UTCTimestamp, value: p.close })),
    );
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const coords = (key: "lower" | "upper") =>
          f.points.map((p) => {
            const x = chart
              .timeScale()
              .timeToCoordinate((Date.parse(p.target) / 1000) as UTCTimestamp);
            const y = median.priceToCoordinate(p[key]);
            return x !== null && y !== null ? `${x},${y}` : "";
          });
        const bottom = coords("lower"),
          top = coords("upper");
        setGeometry({
          polygon:
            bottom.every(Boolean) && top.every(Boolean)
              ? [...top, ...bottom.reverse()].join(" ")
              : "",
          originX: chart.timeScale().timeToCoordinate(origin as UTCTimestamp),
        });
      });
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(update);
    const observer = new ResizeObserver(() => {
      chart.resize(node.clientWidth, node.clientHeight);
      update();
    });
    observer.observe(node);
    const crosshair = (param: { time?: unknown }) => {
      const p = f.points.find(
        (p) => Date.parse(p.target) / 1000 === param.time,
      );
      setTooltip(
        p
          ? `${new Date(p.target).toLocaleDateString("en-GB", { timeZone: "UTC" })} · Median ${p.median.toFixed(2)} USDT · 80% ${p.lower.toFixed(2)}–${p.upper.toFixed(2)}`
          : "",
      );
    };
    chart.subscribeCrosshairMove(crosshair);
    chart.subscribeClick((param) => {
      const i = f.points.findIndex(
        (p) => Date.parse(p.target) / 1000 === param.time,
      );
      if (i >= 0) onPoint?.(i);
    });
    chart.timeScale().setVisibleRange({
      from: (mini
        ? origin - 2 * 86400
        : (detail.history[0]?.time ?? origin)) as UTCTimestamp,
      to: (origin + 8 * 86400) as UTCTimestamp,
    });
    update();
    const reset = () => {
      chart.timeScale().setVisibleRange({
        from: (mini
          ? origin - 2 * 86400
          : (detail.history[0]?.time ?? origin)) as UTCTimestamp,
        to: (origin + 8 * 86400) as UTCTimestamp,
      });
    };
    node.addEventListener("dblclick", reset);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      node.removeEventListener("dblclick", reset);
      chart.remove();
    };
  }, [detail, showActuals, showIntervals, mini, clock, onPoint]);
  return (
    <div className={`forecast-plot ${mini ? "mini-plot" : ""}`}>
      <div ref={mount} className="chart-canvas" />
      <svg className="forecast-band" aria-hidden="true">
        {showIntervals && geometry.polygon && (
          <polygon points={geometry.polygon} fill="#00d4e6" fillOpacity=".13" />
        )}
        {geometry.originX !== null && (
          <line
            x1={geometry.originX}
            x2={geometry.originX}
            y1="0"
            y2="100%"
            stroke="#849bb6"
            strokeDasharray="4 4"
          />
        )}
      </svg>
      {geometry.originX !== null && (
        <span
          className="origin-label"
          style={{ left: Math.max(0, geometry.originX - 40) }}
        >
          Origin UTC
        </span>
      )}
      {tooltip && <div className="chart-tooltip">{tooltip}</div>}
    </div>
  );
}
