import React, { useEffect, useRef, useState, useMemo, useLayoutEffect } from 'react';
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
} from 'lightweight-charts';
import type {
  IChartApi,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  SeriesMarker,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import type { Candle } from '../types';

interface MainChartProps {
  candles: Candle[];
  symbol: string;
  showSplitRegions: boolean;
  showVolume: boolean;
  activeSplitFilter: string | null;
  onHoverCandle?: (candle: Candle | null) => void;
  selectedCandle?: Candle | null;
}


export const MainChart: React.FC<MainChartProps> = ({
  candles,
  symbol,
  showSplitRegions,
  showVolume,
  activeSplitFilter,
  onHoverCandle,
  selectedCandle,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const gapMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [gapCount, setGapCount] = useState(0);
  const [volumeHeight, setVolumeHeight] = useState(85);

  const latest = useRef({ candles, onHoverCandle });
  useLayoutEffect(() => { latest.current = { candles, onHoverCandle }; }, [candles, onHoverCandle]);
  const [regions, setRegions] = useState<Array<{ key: string; left: number; width: number }>>([]);
  const [navRange, setNavRange] = useState({ startPct: 0, endPct: 100 });
  const navigatorRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; start: number; end: number; type: 'left' | 'right' | 'window' } | null>(null);
  const timeline = useRef<Array<{time:number;split:string}>>([]);
  const syncView = useRef<() => void>(() => {});

  // Initialize and mount Lightweight Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const initialWidth = container.clientWidth || 720;
    const initialHeight = container.clientHeight || 280;


    const chart = createChart(container, {
      width: initialWidth,
      height: initialHeight,
      layout: {
        background: { color: '#031427' },
        textColor: '#64748b',
        fontSize: 12,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(15, 45, 78, 0.4)', style: 1 },
        horzLines: { color: 'rgba(15, 45, 78, 0.4)', style: 1 },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: 'rgba(0, 229, 255, 0.4)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#02182e',
        },
        horzLine: {
          color: 'rgba(0, 229, 255, 0.4)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#02182e',
        },
      },
      rightPriceScale: {
        borderColor: '#0f2d4e',
        scaleMargins: {
          top: 0.08,
          bottom: 0.08,
        },
        ticksVisible: true,
      },
      timeScale: {
        minBarSpacing: 0.001,
        borderColor: '#0f2d4e',
        timeVisible: false,
        secondsVisible: false,
        visible: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    chartRef.current = chart;

    // Candlestick Series (exact teal/cyan bullish & coral bearish colors)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00d4d8',
      downColor: '#ef4444',
      borderUpColor: '#00d4d8',
      borderDownColor: '#ef4444',
      wickUpColor: '#00d4d8',
      wickDownColor: '#ef4444',
    });
    candleSeriesRef.current = candleSeries;
    gapMarkersRef.current = createSeriesMarkers(candleSeries, []);

    // Volume Subpanel Series (synchronized, bottom 22% of chart)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'right',
    }, 1);
    volumeSeriesRef.current = volumeSeries;
    chart.panes()[1]?.setHeight(85);

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0.01,
      },
      visible: true,
      borderColor: '#0f2d4e',
    });

    chart.subscribeCrosshairMove((param) => {
      const { candles: current, onHoverCandle: callback } = latest.current;
      callback?.(current.find(c => c.time === param.time) || null);
    });

    const updateView = () => {
      const current = timeline.current;
      const scale = chart.timeScale();
      const range = scale.getVisibleLogicalRange();
      if (!range || !current.length) { setRegions([]); return; }
      const plotWidth = Math.max(0, container.clientWidth - chart.priceScale('right').width());
      const next: Array<{ key: string; left: number; width: number }> = [];
      let start = 0;
      while (start < current.length) {
        const key = current[start].split;
        let end = start + 1;
        while (end < current.length && current[end].split === key) end++;
        // The renderer accepts integer indices; offset the candle centers to their edges.
        const spacing = chart.options().timeScale.barSpacing;
        const left = Math.max(0, (scale.logicalToCoordinate(start as import('lightweight-charts').Logical) ?? 0) - spacing / 2);
        const right = Math.min(plotWidth, (scale.logicalToCoordinate((end - 1) as import('lightweight-charts').Logical) ?? plotWidth) + spacing / 2);
        if (right > left) next.push({ key, left, width: right - left });
        start = end;
      }
      setRegions(next);
      const last = Math.max(1, current.length - 1);
      setNavRange({ startPct: Math.max(0, Math.min(100, range.from / last * 100)), endPct: Math.max(0, Math.min(100, range.to / last * 100)) });
    };
    let frame = 0;
    const scheduleView = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(updateView); };
    syncView.current = scheduleView;
    chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleView);

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0 || !chartRef.current) return;
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        chartRef.current.applyOptions({ width, height });
        // Volume pane shrinks on short windows so the price pane keeps most of the height.
        const volume = Math.round(Math.min(85, Math.max(44, height * 0.26)));
        chartRef.current.panes()[1]?.setHeight(volume);
        setVolumeHeight(volume);
        scheduleView();
      }
    });
    resizeObserver.observe(container);

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      syncView.current = () => {};
    };
  }, []);

  // Update volume series visibility
  useEffect(() => {
    if (!volumeSeriesRef.current) return;
    volumeSeriesRef.current.applyOptions({
      visible: showVolume,
    });
    volumeSeriesRef.current.moveToPane(showVolume ? 1 : 0);
    volumeSeriesRef.current.priceScale().applyOptions({ visible: true });
    chartRef.current?.panes()[1]?.setHeight(85);
  }, [showVolume]);

  useEffect(() => {
    if (!selectedCandle || !chartRef.current) return;
    const index = timeline.current.findIndex(c => c.time === selectedCandle.time);
    const range = chartRef.current.timeScale().getVisibleLogicalRange();
    if (index >= 0 && range && (index < range.from || index > range.to)) {
      const half = Math.max(20, (range.to - range.from) / 2);
      chartRef.current.timeScale().setVisibleLogicalRange({ from: index - half, to: index + half });
    }
  }, [selectedCandle, candles]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    const chart = chartRef.current;
    if (!series || !volume || !chart) return;
    const priceData: Array<{time:UTCTimestamp;open?:number;high?:number;low?:number;close?:number}> = [];
    const volumeData: Array<{time:UTCTimestamp;value?:number;color?:string}> = [];
    timeline.current = [];
    // Missing hours stay as empty slots (never filled) and get a visible marker.
    const markers: SeriesMarker<Time>[] = [];
    let missingHours = 0;
    for (const [i,c] of candles.entries()) {
      const previous = candles[i-1];
      if(previous && c.time - previous.time > 3600){
        const hours = (c.time - previous.time) / 3600 - 1;
        missingHours += hours;
        markers.push({time:c.time as UTCTimestamp,position:'aboveBar',shape:'arrowDown',color:'#f59e0b',text:`${hours}h missing`});
      }
      if(previous) for(let t=previous.time+3600;t<c.time;t+=3600){
        priceData.push({time:t as UTCTimestamp}); volumeData.push({time:t as UTCTimestamp});
        timeline.current.push({time:t,split:previous.split});
      }
      priceData.push({time:c.time as UTCTimestamp,open:c.open,high:c.high,low:c.low,close:c.close});
      volumeData.push({time:c.time as UTCTimestamp,value:c.quote_volume,color:c.close>=c.open?'rgba(0,212,216,.5)':'rgba(239,68,68,.5)'});
      timeline.current.push({time:c.time,split:c.split});
    }
    series.setData(priceData);
    volume.setData(volumeData);
    gapMarkersRef.current?.setMarkers(markers);
    setGapCount(missingHours);
    chart.timeScale().fitContent();
    syncView.current();
  }, [candles]);

  const setNavigatorRange = (start: number, end: number) => {
    if (candles.length < 2 || !chartRef.current) return;
    const last = timeline.current.length - 1;
    chartRef.current.timeScale().setVisibleLogicalRange({ from: start / 100 * last, to: end / 100 * last });
  };

  const sparklinePoints = useMemo(() => {
    if (!candles.length) return '';
    const sampled = candles.filter((_, i) => i % Math.max(1, Math.floor(candles.length / 150)) === 0);
    const low = Math.min(...sampled.map(c => c.low));
    const span = Math.max(...sampled.map(c => c.high)) - low || 1;
    return sampled.map((c, i) => `${i ? 'L' : 'M'} ${i / Math.max(1, sampled.length - 1) * 100} ${90 - (c.close - low) / span * 80}`).join(' ');
  }, [candles]);

  const splitLabels: Record<string, { label: string; color: string }> = {
    training: { label: 'Training', color: '#00d4e6' },
    validation: { label: 'Validation', color: '#f59e0b' },
    final_test: { label: 'Final Test', color: '#c084fc' },
  };
  const dateLabel = (time?: number) => time === undefined ? '—' : new Date(time * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

  const waitingForSplit = activeSplitFilter && candles.some(c => c.split !== activeSplitFilter);

  return (
    <section className="main-chart" aria-label="Historical candlestick chart">
      <div className="chart-heading">
        <div><strong>{symbol.replace('USDT', '/USDT')}</strong> · 1h · Binance Spot</div>
        <div className="chart-period">{waitingForSplit ? 'Loading selected period…' : `${activeSplitFilter ? splitLabels[activeSplitFilter]?.label : 'All history'} · ${dateLabel(candles[0]?.time)} – ${dateLabel(candles.at(-1)?.time)} UTC`}</div>
        <button className="chart-reset" onClick={() => chartRef.current?.timeScale().fitContent()}>Reset zoom</button>
      </div>
      <div className="chart-plot">
        <div ref={chartContainerRef} className="chart-canvas" />
        {showSplitRegions && <div className="split-overlays" aria-hidden="true" style={{bottom:showVolume?volumeHeight+27:28}}>
          {regions.map(region => <div key={region.key} style={{ position: 'absolute', left: region.left, width: region.width, top: 0, bottom: 0, borderLeft: `1px dashed ${splitLabels[region.key]?.color}`, background: `${splitLabels[region.key]?.color}0d` }}>
            {region.width > 110 && <span className="region-label" style={{ color: splitLabels[region.key]?.color }}>{splitLabels[region.key]?.label}</span>}
          </div>)}
        </div>}
        {!candles.length && <div className="chart-empty">No candles in this period</div>}
      </div>
      <div className="chart-navigator">
        <div ref={navigatorRef} className="navigator-track"
          onPointerMove={event => {
            if (!drag.current || !navigatorRef.current) return;
            const initial = drag.current;
            const delta = (event.clientX - initial.x) / navigatorRef.current.clientWidth * 100;
            let start = initial.start;
            let end = initial.end;
            if (initial.type === 'left') start = Math.max(0, Math.min(end - 1, start + delta));
            else if (initial.type === 'right') end = Math.min(100, Math.max(start + 1, end + delta));
            else { start = Math.max(0, Math.min(100 - (end - start), start + delta)); end = start + initial.end - initial.start; }
            setNavigatorRange(start, end);
          }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none"><path d={sparklinePoints} fill="none" stroke="#0284c7" strokeWidth="1.5" /></svg>
          <div className="navigator-window" style={{ left: `${navRange.startPct}%`, width: `${navRange.endPct - navRange.startPct}%` }}
            onPointerDown={event => { navigatorRef.current?.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, start: navRange.startPct, end: navRange.endPct, type: 'window' }; }}>
            {(['left', 'right'] as const).map((side) => <button key={side} className={`navigator-handle ${side}`} aria-label={`Adjust range ${side === 'left' ? 'start' : 'end'}`}
              onPointerDown={event => { event.stopPropagation(); navigatorRef.current?.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, start: navRange.startPct, end: navRange.endPct, type: side }; }}
              onKeyDown={event => { if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return; event.preventDefault(); const delta = event.key === 'ArrowRight' ? 1 : -1; setNavigatorRange(side === 'left' ? Math.max(0, Math.min(navRange.endPct - 1, navRange.startPct + delta)) : navRange.startPct, side === 'right' ? Math.min(100, Math.max(navRange.startPct + 1, navRange.endPct + delta)) : navRange.endPct); }} />)}
          </div>
        </div>
        <div className="navigator-dates"><span>{dateLabel(candles[0]?.time)}</span><span>{showVolume ? 'Price (USDT) & quote volume (USDT)' : 'Price (USDT)'} · UTC{gapCount ? ` · ${gapCount} missing hour${gapCount === 1 ? '' : 's'} shown as empty slots` : ''}</span><span>{dateLabel(candles.at(-1)?.time)}</span></div>
      </div>
    </section>
  );
};
