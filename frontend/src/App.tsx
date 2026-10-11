import React, { useState, useEffect, useRef } from "react";
import { Sidebar } from "./components/Sidebar";
import { MainChart } from "./components/MainChart";
import { CandleInspector } from "./components/CandleInspector";
import { ForecastLabView } from "./components/ForecastLabView";
import { ImportModal } from "./components/ImportModal";
import {
  DatasetHeader,
  DatasetTiles,
  PriceSummary,
  SplitChips,
  SplitRibbon,
} from "./components/DatasetOverview";
import type { Candle, DatasetMetadata, ImportStatus } from "./types";

// Layout preferences are per-browser conveniences; storage may be unavailable.
const readSetting = (key: string, fallback: string) => {
  try {
    return localStorage.getItem("foresight." + key) ?? fallback;
  } catch {
    return fallback;
  }
};
const writeSetting = (key: string, value: string) => {
  try {
    localStorage.setItem("foresight." + key, value);
  } catch {
    /* Ignore unavailable storage. */
  }
};

export const App: React.FC = () => {
  // Navigation
  const [activeTab, setActiveTab] = useState<string>("dataset");
  const [selectedSymbol, setSelectedSymbol] = useState<string>("BTCUSDT");

  // Display toggles
  const [showSplitRegions, setShowSplitRegions] = useState<boolean>(true);
  const [showVolume, setShowVolume] = useState<boolean>(true);

  // Split selection filter (null = all history)
  const [activeSplitFilter, setActiveSplitFilter] = useState<string | null>(
    null,
  );

  // Data state
  const [isRealData, setIsRealData] = useState<boolean>(false);
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [chartCandles, setChartCandles] = useState<Candle[]>([]);
  const [tableCandles, setTableCandles] = useState<Candle[]>([]);
  const [totalTableRows, setTotalTableRows] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize] = useState<number>(50);

  // Interactive selection
  const [, setHoveredCandle] = useState<Candle | null>(null);
  const [selectedCandle, setSelectedCandle] = useState<Candle | null>(null);

  // Import Modal & Status
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null);

  const [error, setError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [inspectorOpen, setInspectorOpen] = useState(
    () => readSetting("inspectorOpen", "1") === "1",
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => readSetting("sidebarCollapsed", "0") === "1",
  );
  useEffect(
    () => writeSetting("inspectorOpen", inspectorOpen ? "1" : "0"),
    [inspectorOpen],
  );
  useEffect(
    () => writeSetting("sidebarCollapsed", sidebarCollapsed ? "1" : "0"),
    [sidebarCollapsed],
  );
  const lastImportStatus = useRef<ImportStatus | null>(null);

  // Chart requests are independent of table pagination. Abort superseded loads.
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const split = activeSplitFilter ? `?split=${activeSplitFilter}` : "";
        const [metaRes, candleRes] = await Promise.all([
          fetch(`/api/datasets/${selectedSymbol}/metadata`, {
            signal: controller.signal,
          }),
          fetch(`/api/datasets/${selectedSymbol}/candles${split}`, {
            signal: controller.signal,
          }),
        ]);
        if (!metaRes.ok || !candleRes.ok)
          throw new Error("Dataset unavailable");
        const meta: DatasetMetadata = await metaRes.json();
        const data = await candleRes.json();
        if (controller.signal.aborted) return;
        setMetadata(meta);
        setIsRealData(meta.total_candles > 0);
        setChartCandles(data.candles);
        setError("");
      } catch {
        if (controller.signal.aborted) return;
        setIsRealData(false);
        setMetadata(null);
        setChartCandles([]);
        setError("Dataset unavailable. Check the backend and retry.");
      }
    };
    void load();
    return () => controller.abort();
  }, [selectedSymbol, activeSplitFilter, refreshVersion]);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const split = activeSplitFilter ? `&split=${activeSplitFilter}` : "";
        const res = await fetch(
          `/api/datasets/${selectedSymbol}/table?page=${currentPage}&page_size=${pageSize}${split}`,
          { signal: controller.signal },
        );
        if (!res.ok) throw new Error("Table unavailable");
        const data = await res.json();
        if (controller.signal.aborted) return;
        setTableCandles(data.rows || []);
        setTotalTableRows(data.total_rows || 0);
      } catch {
        if (controller.signal.aborted) return;
        setTableCandles([]);
        setTotalTableRows(0);
        setError("Could not load candle rows.");
      }
    };
    void load();
    return () => controller.abort();
  }, [
    selectedSymbol,
    activeSplitFilter,
    currentPage,
    pageSize,
    refreshVersion,
  ]);

  // Refresh once when a running import completes, not on every completed-status poll.
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const res = await fetch("/api/import/status", {
          signal: controller.signal,
        });
        if (!res.ok) {
          const body = await res.json();
          throw new Error(body.detail || "Import failed");
        }
        if (res.ok) {
          const data: ImportStatus | null = await res.json();
          if (controller.signal.aborted) return;
          const previous = lastImportStatus.current;
          if (
            data?.status === "complete" &&
            previous &&
            (previous.job_id !== data.job_id || previous.status !== "complete")
          ) {
            setRefreshVersion((v) => v + 1);
          }
          lastImportStatus.current = data;
          setImportStatus(data);
        }
      } catch {
        /* Retry transient failures on the next poll. */
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  const handleStartImport = async (importBoth: boolean) => {
    try {
      const res = await fetch("/api/import/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: selectedSymbol,
          import_both: importBoth,
        }),
      });
      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.detail || "Import failed");
      }
      if (res.ok) {
        const data = await res.json();
        setImportStatus(data);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleCancelImport = async () => {
    if (!importStatus?.job_id) return;
    try {
      await fetch(`/api/import/cancel/${importStatus.job_id}`, {
        method: "POST",
      });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const isImporting =
    importStatus?.status === "pending" ||
    importStatus?.status === "normalizing" ||
    importStatus?.status === "running" ||
    importStatus?.status === "downloading" ||
    importStatus?.status === "parsing" ||
    importStatus?.status === "validating" ||
    importStatus?.status === "saving";

  return (
    <div className="app-shell">
      {/* Main Layout Body */}
      <div
        className={`app-body ${activeTab === "dataset" ? "dataset-body" : "forecast-body"} ${inspectorOpen ? "inspector-visible" : "inspector-collapsed"} ${sidebarCollapsed ? "nav-collapsed" : ""}`}
      >
        {/* Left Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onTabClick={setActiveTab}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed((c) => !c)}
        />

        {activeTab !== "dataset" ? (
          <ForecastLabView
            view={activeTab}
            onBackToDataset={() => setActiveTab("dataset")}
          />
        ) : (
          <>
            <main className="dataset-stage v-page">
              <DatasetHeader
                symbol={selectedSymbol}
                metadata={metadata}
                onSymbolChange={(sym) => {
                  setSelectedSymbol(sym);
                  setCurrentPage(1);
                  setSelectedCandle(null);
                }}
                onImport={() => setIsImportModalOpen(true)}
                importLabel={
                  isImporting
                    ? `Importing · ${Math.round(importStatus?.progress_percentage || 0)}%`
                    : "Import data"
                }
              />
              {error && (
                <div className="error" role="alert">
                  {error}{" "}
                  <button onClick={() => setRefreshVersion((v) => v + 1)}>
                    Retry
                  </button>
                </div>
              )}
              <div className="v-stage dataset-fit">
              <section className="v-card v-hero" aria-label="Price history">
                <div className="v-hero-top">
                  <PriceSummary
                    candles={chartCandles}
                    filter={activeSplitFilter}
                  />
                  {metadata && (
                    <SplitChips
                      splits={metadata.splits}
                      active={activeSplitFilter}
                      onSelect={(split) => {
                        setActiveSplitFilter(split);
                        setCurrentPage(1);
                        setSelectedCandle(null);
                      }}
                    />
                  )}
                  <div className="v-toggles">
                    <label>
                      <input
                        type="checkbox"
                        checked={showSplitRegions}
                        onChange={(e) => setShowSplitRegions(e.target.checked)}
                      />
                      Shading
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={showVolume}
                        onChange={(e) => setShowVolume(e.target.checked)}
                      />
                      Volume
                    </label>
                  </div>
                </div>
                <MainChart
                  candles={chartCandles}
                  symbol={selectedSymbol}
                  showSplitRegions={showSplitRegions}
                  showVolume={showVolume}
                  activeSplitFilter={activeSplitFilter}
                  onHoverCandle={setHoveredCandle}
                  selectedCandle={selectedCandle}
                />
                {metadata && <SplitRibbon splits={metadata.splits} />}
              </section>
              {metadata && <DatasetTiles metadata={metadata} />}
              </div>
            </main>

            <CandleInspector
              collapsed={!inspectorOpen}
              onToggleCollapsed={() => setInspectorOpen((open) => !open)}
              candles={tableCandles}
              totalRows={totalTableRows}
              currentPage={currentPage}
              pageSize={pageSize}
              isRealData={isRealData}
              onPageChange={setCurrentPage}
              onRowClick={setSelectedCandle}
              selectedCandle={selectedCandle}
            />
          </>
        )}
      </div>

      {/* Import Modal */}
      <ImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        symbol={selectedSymbol}
        onStartImport={handleStartImport}
        onCancelImport={handleCancelImport}
        importStatus={importStatus}
        dateCoverage={metadata?.date_coverage}
        expectedCandles={metadata?.expected_candles}
        months={
          metadata
            ? Object.values(metadata.splits).reduce(
                (a, s) => a + s.duration_months,
                0,
              )
            : undefined
        }
        error={error}
      />
    </div>
  );
};

export default App;
