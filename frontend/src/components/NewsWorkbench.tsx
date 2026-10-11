import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LabChart, type ChartSeries } from "./LabChart";

type Article = { id: string; headline: string; text: string; publisher: string; url: string; published_at: string; ingested_at: string; effective_available_at: string; availability_quality: string; content_scope: string; rights: string; predecessor_id?: string };
type Packet = { id: string; origin: string; symbol: string; policy: string; article_ids: string[]; excluded: { id: string; reason: string }[]; coverage_state: string };
type Answer = { choice: string; confidence: number; probabilities: Record<string, number> };
type Classification = { id: string; article_id: string; classifier: string; model: string; answers: Record<string, Answer>; cost_usd: number };
type Job = { kind?: string; symbol?: string; job_id: string; status: string; current_step: string; progress_percentage: number; error?: string; manifest_id?: string; result?: { id?: string; state?: string; errors?: unknown[] } };
type Horizon = { step: number; sample_count: number; mae: number | null; baseline_mae: number | null; coverage: number | null; brier: number | null; interval_score: number | null };
type Variant = { model_id: string; forecast_ids: string[]; unavailable: { origin: string; reason: string }[]; matched_metrics: { horizons: Horizon[] }; full_origin_metrics: { horizons: Horizon[] }; paired_day7_mae_difference?: number; paired_95pct_block_interval?: number[] };
type ForecastRun = { id: string; symbol: string; state: string; variants: Record<string, Variant>; errors: Record<string, string>; intended_origins: number; matched_complete_origins: string[]; evaluation_label: string; promotion: { reason: string } };
type Detail = { forecast: { id: string; origin: string; origin_price: number; quote_currency: string; points: { target: string; median: number; lower: number; upper: number }[]; news_evidence?: { packet_id: string; features_id: string } }; actual: { time: string; value: number }[] };
type HistoryPoint = { target: string; origin: string; origin_index: number; median: number; lower: number; upper: number; actual: number | null };
type GraphView = { origins: string[]; details: Record<string, Detail>; series: Record<string, HistoryPoint[]> };
type Status = { imported_providers: string[]; article_count: number; classifiers: { id: string; state: string; model?: string; max_experiment_usd?: number; total_budget?: { limit_usd: number; remaining_usd: number; charged_or_reserved_usd: number } }[]; markets: { instrument_id: string; name: string; currency: string }[] };
type Preview = { conservative_max_cost_usd?: number; pending_ids?: string[]; omitted_count?: number; cached_count?: number; notice?: string; article_count?: number };
type ClassificationEvaluation = { id: string; status: string; matched_article_ids: string[]; conflicting_article_ids: string[]; results: Record<string, { sample_count: number; abstentions: number; multiclass_brier: number | null; metrics: Record<string, { macro_f1: number | null; matrix: Record<string, Record<string, number>> }> }> };

async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch("/api/news" + path, body === undefined ? { signal } : { signal, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "News request failed"));
  return data as T;
}
const dt = (s: string) => new Date(s).toLocaleString("en-GB", { timeZone: "UTC" }) + " UTC";
const money = (n?: number | null) => n == null ? "—" : n.toLocaleString("en-GB", { maximumFractionDigits: 4 });
const stamp = (s: string) => Date.parse(s) / 1000;
function download(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}

export function NewsWorkbench({
  symbol = "BTCUSDT",
  mode = "full",
  onSymbolChange,
  onNavigateToLab,
  onNavigateToDataset,
}: {
  symbol?: string;
  mode?: "dataset" | "forecast" | "full";
  onSymbolChange?: (s: string) => void;
  onNavigateToLab?: () => void;
  onNavigateToDataset?: () => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [articlePage, setArticlePage] = useState(1);
  const [articleTotal, setArticleTotal] = useState(0);
  const [providerFilter, setProviderFilter] = useState("");
  const [search, setSearch] = useState("");
  const [inspectedArticle, setInspectedArticle] = useState<Article | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [classifications, setClassifications] = useState<Classification[]>([]);
  const [runs, setRuns] = useState<ForecastRun[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState(mode === "forecast" ? "forecasting" : "news");
  const [forecastTab, setForecastTab] = useState<"next" | "actual" | "metrics" | "evidence">("next");
  const [market, setMarket] = useState(symbol);
  const [origin, setOrigin] = useState(() => new Date().toISOString());
  const [policy, setPolicy] = useState("strict");
  const [lookback, setLookback] = useState(7);
  const [packetId, setPacketId] = useState("");
  const [classifier, setClassifier] = useState("openai");
  const [budget, setBudget] = useState("0.50");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [articleId, setArticleId] = useState("");
  const [runId, setRunId] = useState("");
  const [chartData, setChartData] = useState<GraphView>({ origins: [], details: {}, series: {} });
  const refreshSequence = useRef(0);
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [primary, setPrimary] = useState("price_only");
  const [extras, setExtras] = useState<string[]>([]);
  const [showActual, setShowActual] = useState(true);
  const [showRange, setShowRange] = useState(true);
  const [horizon, setHorizon] = useState(7);
  const [originIndex, setOriginIndex] = useState(-1);
  const [annotation, setAnnotation] = useState({ annotator: "", relevance: "unknown", category: "unknown", framing: "unknown", note: "" });
  const [usedEvidence, setUsedEvidence] = useState<{ forecast_id: string; packet_id: string; feature: { names: string[]; values: number[] } } | null>(null);
  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [evaluation, setEvaluation] = useState<ClassificationEvaluation | null>(null);

  useEffect(() => {
    setMarket(symbol);
  }, [symbol]);

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const [s, a, p, c, r, j] = await Promise.all([
      api<Status>("/status"),
      api<{ items: Article[]; total: number }>(`/records/article?page_size=100&page=${articlePage}&provider=${encodeURIComponent(providerFilter)}&q=${encodeURIComponent(search)}`),
      api<{ items: Packet[] }>(`/records/packet?symbol=${encodeURIComponent(market)}`),
      api<{ items: Classification[] }>(`/records/classification?symbol=${encodeURIComponent(market)}&page_size=100`),
      api<{ items: ForecastRun[] }>(`/records/forecast_experiment?symbol=${encodeURIComponent(market)}`),
      api<Job | null>("/latest-job"),
    ]);
    if (sequence !== refreshSequence.current) return;
    setStatus(s);
    setArticles(a.items);
    setArticleTotal(a.total);
    setPackets(p.items);
    if (!packetId && p.items.length > 0) {
      setPacketId(p.items[0].id);
    }
    setClassifications(c.items);
    setRuns(r.items);
    setJob(j);
  }, [market, articlePage, providerFilter, search, packetId]);

  useEffect(() => {
    let stop = false;
    refresh().catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [refresh]);

  useEffect(() => {
    api<Job | null>("/latest-job")
      .then(setJob)
      .catch((e) => setError(e.message));
  }, []);

  const running = job && ["pending", "running"].includes(job.status);
  useEffect(() => {
    if (!job || !running) return;
    let stop = false;
    const t = setInterval(
      () =>
        api<Job>("/jobs/" + job.job_id)
          .then((j) => {
            if (stop) return;
            setJob(j);
            if (!["pending", "running"].includes(j.status)) {
              setOrigin(new Date().toISOString());
              if (j.kind === "news-forecast" && j.result?.id) setRunId(j.result.id);
              void refresh().catch((e) => setError(e.message));
            }
          })
          .catch((e) => !stop && setError(e.message)),
      1000,
    );
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [job, running, refresh]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const packet = packets.find((p) => p.id === packetId) || packets[0];
  const activePacketId = packet?.id || packetId;
  const article = articles.find((a) => a.id === articleId) || (inspectedArticle?.id === articleId ? inspectedArticle : null);
  useEffect(() => {
    let stop = false;
    if (articleId)
      api<Article>(`/records/article/${articleId}`)
        .then((a) => !stop && setInspectedArticle(a))
        .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [articleId]);

  const run = runs.find((r) => r.id === runId) || runs[0];
  const selectedRunId = run?.id || "";
  useEffect(() => {
    let stop = false;
    const controller = new AbortController();
    if (selectedRunId)
      api<GraphView>(`/forecast-experiments/${selectedRunId}/view?origin_index=${originIndex}&horizon=${horizon}`, undefined, controller.signal)
        .then((x) => {
          if (!stop) {
            setDetails(x.details);
            setChartData(x);
          }
        })
        .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
      controller.abort();
    };
  }, [selectedRunId, originIndex, horizon]);

  const activePrimary = run?.variants[primary] ? primary : Object.keys(run?.variants || {})[0];
  const displayed = details[activePrimary];
  const series = useMemo<ChartSeries[]>(() => {
    if (!displayed) return [];
    const lines: ChartSeries[] = [];
    if (showActual)
      lines.push({
        id: "actual",
        label: "Actual price",
        color: "#F1F5FA",
        points: displayed.actual.map((p) => ({ time: stamp(p.time), value: p.value })),
        width: 2,
      });
    for (const [i, v] of [activePrimary, ...extras.filter((v) => v !== activePrimary)].entries()) {
      const d = details[v];
      if (!d) continue;
      const points = [
        { time: stamp(d.forecast.origin), value: d.forecast.origin_price },
        ...d.forecast.points.map((p) => ({ time: stamp(p.target), value: p.median })),
      ];
      lines.push({
        id: v,
        label: v.replaceAll("_", " "),
        color: i === 0 ? "#4C9AFF" : ["#F6B84A", "#B690FF", "#78E4A1"][i - 1] || "#EC729D",
        points,
        width: i === 0 ? 3 : 2,
      });
      if (v === activePrimary && showRange)
        for (const key of ["lower", "upper"] as const)
          lines.push({
            id: key,
            label: "80% " + key,
            color: "#4C9AFF",
            dashed: true,
            width: 1,
            points: d.forecast.points.map((p) => ({ time: stamp(p.target), value: p[key] })),
          });
    }
    return lines;
  }, [displayed, details, activePrimary, extras, showActual, showRange]);

  const classificationPayload = { packet_id: activePacketId, classifier, budget_usd: Number(budget), max_articles: 100 };
  const visibleClassifications = classifications.filter(
    (c) =>
      (!packet || packet.article_ids.includes(c.article_id)) &&
      c.classifier === classifier &&
      (!status?.classifiers.find((x) => x.id === classifier)?.model || c.model === status.classifiers.find((x) => x.id === classifier)?.model),
  );
  const forecastPayload = { symbol: market, policy, lookback_days: 30, minimum_origins: 30, evidence_lookback_days: lookback };
  const disabled = busy || !!running;
  const openaiInfo = status?.classifiers.find((c) => c.id === "openai");
  const jevInfo = status?.classifiers.find((c) => c.id === "jev");

  // ---------------------------------------------------------------------------
  // MODE 1: DATASET PREPARATION WORKSPACE (Shown inside Dataset -> News & Macro Dataset)
  // ---------------------------------------------------------------------------
  if (mode === "dataset") {
    return (
      <section className="news-workbench news-dataset-prep">
        {error && (
          <div className="error" role="alert">
            {error}
            <button className="v-btn small" onClick={() => void act(refresh)}>
              Retry reads
            </button>
          </div>
        )}
        {job && (
          <div className="news-job" role="status">
            <progress max={100} value={job.progress_percentage} />
            <span>
              {job.symbol === "NEWS" ? "Shared news" : job.symbol} · {job.status === "complete" && job.result?.state ? job.result.state : job.status} ·{" "}
              {job.status === "complete" ? "Work finished" : job.current_step}
              {job.error ? " · " + job.error : ""}
            </span>
            {running && (
              <button className="v-btn small" onClick={() => void act(async () => setJob(await api<Job>(`/jobs/${job.job_id}/cancel`, {})))}>
                Cancel
              </button>
            )}
            {job.manifest_id && ["cancelled", "failed"].includes(job.status) && (
              <button className="v-btn small" onClick={() => void act(async () => download(await api(`/jobs/${job.job_id}/retained`), "retained-news-artifacts.json"))}>
                Export retained partial results
              </button>
            )}
          </div>
        )}

        {/* Top 3-Step Preparation Grid matching the UI Design Mockup */}
        <div className="news-prep-grid">
          {/* Card 1: Ingest & Collect Sources */}
          <div className="v-card news-prep-card">
            <div className="news-prep-card-head">
              <h3>1. Ingest &amp; Collect Sources</h3>
              <span className="ev-state ok">{status?.article_count ?? 0} stored versions</span>
            </div>
            <p className="v-sub">Generate &amp; ingest the 48-month historical Crypto &amp; Macro archive (2022–2026) or collect live Federal Reserve RSS.</p>
            <button
              className="v-primary news-full-btn"
              disabled={disabled}
              onClick={() => void act(async () => setJob(await api<Job>("/collect", { source: "crypto-macro-archive" })))}
            >
              Generate &amp; Ingest Historical Archive (2022–2026)
            </button>
            <div className="news-card-cta-row">
              <button
                className="v-btn news-full-btn"
                disabled={disabled}
                onClick={() => void act(async () => setJob(await api<Job>("/collect", { source: "federal-reserve" })))}
              >
                Collect Official Macro RSS
              </button>
              {articles.length > 0 && (
                <button
                  className="v-btn small"
                  title="Download stored news dataset archive as JSON"
                  onClick={() => download({ provider: "foresight-archive", articles }, `foresight-news-archive-${market}.json`)}
                >
                  Download Archive JSON
                </button>
              )}
            </div>
            <details className="news-optional-upload">
              <summary className="v-muted small">Optional: Import custom JSON / JSONL file</summary>
              <div className="news-file-row" style={{ marginTop: "6px" }}>
                <input type="file" accept=".json,.jsonl" onChange={(e) => setFile(e.target.files?.[0] || null)} />
                <button
                  className="v-btn small"
                  disabled={disabled || !file}
                  onClick={() =>
                    void act(async () => {
                      if (!file || file.size > 2_000_000) throw new Error("Choose a JSON/JSONL file under 2MB");
                      const text = await file.text();
                      const rows = file.name.endsWith(".jsonl") ? text.trim().split("\n").map((s) => JSON.parse(s)) : JSON.parse(text);
                      setJob(await api<Job>("/import", { provider: "local", articles: Array.isArray(rows) ? rows : rows.articles }));
                    })
                  }
                >
                  Import
                </button>
              </div>
            </details>
          </div>

          {/* Card 2: Build Point-in-Time Evidence Packet */}
          <div className="v-card news-prep-card">
            <div className="news-prep-card-head">
              <h3>2. Build Point-in-Time Evidence Packet</h3>
              <span className="ev-state">{packets.length} saved packets</span>
            </div>
            <div className="news-form-rows">
              <label>
                <span>Symbol</span>
                <select
                  aria-label="News instrument"
                  value={market}
                  onChange={(e) => {
                    setMarket(e.target.value);
                    onSymbolChange?.(e.target.value);
                    setPacketId("");
                    setPreview(null);
                  }}
                >
                  {(status?.markets || [{ instrument_id: symbol, name: symbol }]).map((m) => (
                    <option key={m.instrument_id} value={m.instrument_id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Evidence cutoff UTC</span>
                <input aria-label="News evidence cutoff" value={origin} onChange={(e) => setOrigin(e.target.value)} />
              </label>
              <div className="news-form-split">
                <label>
                  <span>Lookback</span>
                  <div className="v-seg small">
                    {[1, 7, 30].map((d) => (
                      <button
                        key={d}
                        type="button"
                        className={lookback === d ? "on" : ""}
                        onClick={() => {
                          setLookback(d);
                          setPreview(null);
                        }}
                      >
                        {d}d
                      </button>
                    ))}
                  </div>
                </label>
                <label>
                  <span>Availability policy</span>
                  <select
                    value={policy}
                    onChange={(e) => {
                      setPolicy(e.target.value);
                      setPreview(null);
                    }}
                  >
                    <option value="strict">Strict as-of policy</option>
                    <option value="exploratory">Exploratory dates</option>
                  </select>
                </label>
              </div>
            </div>
            <button
              className="v-primary news-full-btn"
              disabled={disabled}
              onClick={() =>
                void act(async () => {
                  const p = await api<Packet>("/packets", { symbol: market, origin, lookback_days: lookback, policy });
                  await refresh();
                  setPacketId(p.id);
                  setUsedEvidence(null);
                })
              }
            >
              Build Evidence Packet
            </button>
          </div>

          {/* Card 3: Run Classification & Feature Extraction */}
          <div className="v-card news-prep-card">
            <div className="news-prep-card-head">
              <h3>3. Run Classification &amp; Feature Extraction</h3>
              <span className={`ev-state ${openaiInfo?.state === "configured" ? "ok" : "wait"}`}>
                {openaiInfo?.state === "configured" ? "OpenAI Ready" : "Keywords Ready"}
              </span>
            </div>
            <div className="news-form-rows">
              <label>
                <span>Packet</span>
                <select
                  value={activePacketId}
                  onChange={(e) => {
                    setPacketId(e.target.value);
                    setPreview(null);
                  }}
                >
                  <option value="">Select evidence packet</option>
                  {packets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {dt(p.origin)} · {p.policy} · {p.article_ids.length} articles
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Classifier</span>
                <select
                  value={classifier}
                  onChange={(e) => {
                    setClassifier(e.target.value);
                    setPreview(null);
                  }}
                >
                  <option value="openai">
                    OpenAI · {openaiInfo?.model || "gpt-4o-mini"} ({openaiInfo?.state === "configured" ? "Ready" : "Not configured"})
                  </option>
                  <option value="keywords">Keywords / Rule Comparator (Ready)</option>
                  <option value="jev">
                    Jev · {jevInfo?.model || "jev-1.13.0"} ({jevInfo?.state === "configured" ? "Ready" : "Not configured"})
                  </option>
                </select>
              </label>
              <div className="news-form-split">
                <label>
                  <span>Budget cap (USD)</span>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={budget}
                    onChange={(e) => {
                      setBudget(e.target.value);
                      setPreview(null);
                    }}
                  />
                </label>
                <div className="news-preview-actions">
                  <button
                    className="v-btn small"
                    disabled={disabled || !activePacketId}
                    onClick={() => void act(async () => setPreview(await api<Preview>("/classifications/preview", classificationPayload)))}
                  >
                    Preview Cost
                  </button>
                </div>
              </div>
            </div>
            {preview && (
              <p className="v-note small">
                {preview.pending_ids?.length ?? 0} pending · {preview.cached_count ?? 0} cached · Max est. ${money(preview.conservative_max_cost_usd)}
              </p>
            )}
            <div className="news-card-cta-row">
              <button
                className="v-primary news-full-btn"
                disabled={
                  disabled ||
                  !activePacketId ||
                  (classifier !== "keywords" &&
                    (Number(budget) <= 0 ||
                      status?.classifiers.find((c) => c.id === classifier)?.state !== "configured" ||
                      (classifier === "openai" && Number(budget) > (openaiInfo?.max_experiment_usd ?? 0))))
                }
                onClick={() =>
                  void act(async () => {
                    if (!preview) {
                      await api<Preview>("/classifications/preview", classificationPayload);
                    }
                    setJob(await api<Job>("/classifications", classificationPayload));
                    setPreview(null);
                  })
                }
              >
                Run Classification
              </button>
              {onNavigateToLab && (
                <button className="v-btn" title="Open Forecast Lab to test models on this prepared dataset" onClick={onNavigateToLab}>
                  Test in Forecast Lab &rarr;
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Lower Unified Table: Stored Articles & Classified Evidence */}
        <div className="v-card news-table-card">
          <div className="news-table-header">
            <div>
              <h3>Stored Articles &amp; Classified Evidence</h3>
              {packet && (
                <span className="v-muted small">
                  Active Packet: {packet.article_ids.length} eligible · {packet.excluded.length} excluded · {packet.coverage_state} · Origin {dt(packet.origin)}
                </span>
              )}
            </div>
            <div className="news-controls">
              <label>
                <span>Source</span>
                <select
                  value={providerFilter}
                  onChange={(e) => {
                    setProviderFilter(e.target.value);
                    setArticlePage(1);
                  }}
                >
                  <option value="">All sources</option>
                  {status?.imported_providers?.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Search news</span>
                <input
                  aria-label="Search news"
                  placeholder="Filter headlines or text…"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setArticlePage(1);
                  }}
                />
              </label>
              {packet && (
                <button className="v-btn small" onClick={() => download(packet, "evidence-packet.json")}>
                  Export Packet
                </button>
              )}
              {activePacketId && (
                <button
                  className="v-btn small"
                  disabled={disabled}
                  onClick={() =>
                    void act(async () =>
                      setEvaluation(await api<ClassificationEvaluation>("/classification-evaluations", { packet_id: activePacketId, classifier: classifier === "openai" ? "openai" : "jev" })),
                    )
                  }
                >
                  Evaluate Human Labels
                </button>
              )}
              <button className="v-btn small" onClick={() => void act(refresh)}>
                Refresh
              </button>
            </div>
          </div>

          <div className="lab-table">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th style={{ width: "34%" }}>Headline</th>
                  <th>Source</th>
                  <th>Published UTC</th>
                  <th>Available UTC</th>
                  <th>Packet Status</th>
                  <th>Relevance</th>
                  <th>Category</th>
                  <th>Framing</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {articles.map((a) => {
                  const clf =
                    visibleClassifications.find((c) => c.article_id === a.id) ||
                    classifications.find((c) => c.article_id === a.id);
                  const rel = clf?.answers?.relevance?.choice;
                  const cat = clf?.answers?.category?.choice;
                  const frm = clf?.answers?.framing?.choice;
                  const conf = clf?.answers?.relevance?.confidence;
                  const inPacket = packet ? (packet.article_ids.includes(a.id) ? "Included" : packet.excluded.find((x) => x.id === a.id)?.reason || "Excluded") : "—";
                  return (
                    <tr key={a.id} className={articleId === a.id ? "primary" : ""}>
                      <td>
                        <button className="news-link" onClick={() => setArticleId(a.id)}>
                          {a.headline}
                        </button>
                      </td>
                      <td>
                        <span className="v-muted small">
                          {a.publisher} · {a.content_scope}
                        </span>
                      </td>
                      <td>{dt(a.published_at)}</td>
                      <td>{dt(a.effective_available_at)}</td>
                      <td>
                        <span className={`ev-state ${inPacket === "Included" ? "ok" : ""}`}>{inPacket}</span>
                      </td>
                      <td>
                        {rel ? (
                          <span className={`ev-state ${rel === "relevant" ? "ok" : rel === "irrelevant" ? "bad" : ""}`}>{rel}</span>
                        ) : (
                          <span className="v-muted small">Unclassified</span>
                        )}
                      </td>
                      <td>{cat ? <span className="ev-state">{cat}</span> : "—"}</td>
                      <td>
                        {frm ? (
                          <span className={`ev-state ${frm === "positive" ? "ok" : frm === "negative" ? "bad" : ""}`}>{frm}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {conf != null && clf?.classifier !== "keywords" ? (
                          <div className="news-conf-bar" title={`Self-reported confidence: ${money(conf * 100)}%`}>
                            <span className="track">
                              <i style={{ width: `${Math.round(conf * 100)}%` }} />
                            </span>
                            <small className="v-num">{Math.round(conf * 100)}%</small>
                          </div>
                        ) : clf ? (
                          <span className="v-muted small">Rule</span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!articles.length && <p className="ev-empty">No news imported yet. Click &ldquo;Collect Official Macro RSS&rdquo; or import a JSON/JSONL archive above.</p>}
          </div>

          <div className="news-pagination">
            <button className="v-btn small" disabled={articlePage === 1} onClick={() => setArticlePage((x) => x - 1)}>
              Previous
            </button>
            <span className="v-muted small">
              Page {articlePage} · {articleTotal} matching article versions
            </span>
            <button className="v-btn small" disabled={articlePage * 100 >= articleTotal} onClick={() => setArticlePage((x) => x + 1)}>
              Next
            </button>
          </div>
        </div>

        {/* Bottom Drawer: Article Inspector & Human Evaluation Labels */}
        {article && (
          <article className="v-card news-detail">
            <div className="news-prep-card-head">
              <h3>Inspect Article &amp; Evaluation Labels</h3>
              <button className="v-btn small" onClick={() => setArticleId("")}>
                Close
              </button>
            </div>
            <div className="news-detail-grid">
              <div>
                <h4>{article.headline}</h4>
                <p>{article.text || "Headline only; full article text not available."}</p>
                <p className="v-sub">
                  <a href={article.url} target="_blank" rel="noreferrer">
                    Original source
                  </a>{" "}
                  · Ingested {dt(article.ingested_at)} · rights: {article.rights} · version {article.id.slice(0, 12)}
                </p>
              </div>
              <div>
                <h4>Human Evaluation Label</h4>
                <div className="news-controls">
                  <label>
                    <span>Annotator</span>
                    <input
                      placeholder="Annotator name"
                      aria-label="Annotator"
                      value={annotation.annotator}
                      onChange={(e) => setAnnotation({ ...annotation, annotator: e.target.value })}
                    />
                  </label>
                  {(["relevance", "category", "framing"] as const).map((k) => (
                    <label key={k}>
                      <span>{k}</span>
                      <select value={annotation[k]} onChange={(e) => setAnnotation({ ...annotation, [k]: e.target.value })}>
                        {(k === "relevance"
                          ? ["unknown", "relevant", "irrelevant"]
                          : k === "framing"
                            ? ["unknown", "positive", "negative", "mixed", "neutral"]
                            : ["unknown", "regulatory", "macro", "security", "market_infrastructure", "flows_adoption", "corporate", "supply_network", "other"]
                        ).map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                  <button
                    className="v-primary"
                    disabled={disabled || !annotation.annotator}
                    onClick={() =>
                      void act(async () => {
                        await api("/labels", { ...annotation, article_id: article.id, symbol: market });
                      })
                    }
                  >
                    Save Immutable Label
                  </button>
                </div>
              </div>
            </div>
          </article>
        )}

        {evaluation && (
          <section className="v-card">
            <div className="news-prep-card-head">
              <h3>Extraction Quality · {evaluation.status}</h3>
              <button className="v-btn small" onClick={() => download(evaluation, "classification-quality.json")}>
                Export Measured Results
              </button>
            </div>
            <p className="v-sub">
              {evaluation.matched_article_ids.length} common labelled articles; {evaluation.conflicting_article_ids.length} annotation conflicts. This measures extraction quality, not price forecasting accuracy.
            </p>
            <div className="lab-table">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Classifier</th>
                    <th>Samples</th>
                    <th>Relevance F1</th>
                    <th>Category F1</th>
                    <th>Framing F1</th>
                    <th>Brier</th>
                    <th>Abstentions</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(evaluation.results).map(([k, r]) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{r.sample_count}</td>
                      <td>{money(r.metrics.relevance.macro_f1)}</td>
                      <td>{money(r.metrics.category.macro_f1)}</td>
                      <td>{money(r.metrics.framing.macro_f1)}</td>
                      <td>{money(r.multiclass_brier)}</td>
                      <td>{r.abstentions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </section>
    );
  }

  // ---------------------------------------------------------------------------
  // MODE 2: FORECAST LAB TESTING WORKSPACE (Shown inside Forecast Lab -> News & Macro Models)
  // ---------------------------------------------------------------------------
  if (mode === "forecast") {
    return (
      <section className="news-workbench news-lab-mode">
        {/* Sub-Toolbar for News Forecast Testing */}
        <div className="news-lab-toolbar v-card">
          <label className="v-pill">
            <span className="v-muted">Symbol</span>
            <select
              aria-label="News instrument"
              value={market}
              onChange={(e) => {
                setMarket(e.target.value);
                onSymbolChange?.(e.target.value);
                setRunId("");
                setPreview(null);
              }}
            >
              {(status?.markets || [{ instrument_id: symbol, name: symbol }]).map((m) => (
                <option key={m.instrument_id} value={m.instrument_id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <label className="v-pill">
            <span className="v-muted">Evidence Policy</span>
            <select
              value={policy}
              onChange={(e) => {
                setPolicy(e.target.value);
                setPreview(null);
              }}
            >
              <option value="strict">Strict as-of</option>
              <option value="exploratory">Exploratory</option>
            </select>
          </label>
          <span className="v-pill">
            <i className={`v-dot ${(status?.article_count ?? 0) > 0 ? "ok" : "idle"}`} />
            <span className="v-muted">Prepared Dataset:</span>
            <b>
              {status?.article_count ?? 0} articles · {packets.length} packets · {openaiInfo?.state === "configured" ? "OpenAI Ready" : "Keywords"}
            </b>
          </span>
          {runs.length > 0 && (
            <label className="v-pill">
              <span className="v-muted">Experiment</span>
              <select
                value={selectedRunId}
                onChange={(e) => {
                  setRunId(e.target.value);
                  setOriginIndex(-1);
                  setDetails({});
                  setModelInfo(null);
                }}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.symbol} · {r.state} · {r.id.slice(-8)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="v-grow" />
          {onNavigateToDataset && (
            <button className="v-btn small" onClick={onNavigateToDataset}>
              Prepare News Dataset
            </button>
          )}
          <button
            className="v-btn small"
            disabled={disabled}
            onClick={() => void act(async () => setPreview(await api<Preview>("/forecast-experiments/preview", forecastPayload)))}
          >
            Preview Experiment
          </button>
          <button
            className="v-primary"
            disabled={disabled}
            onClick={() =>
              void act(async () => {
                if (!preview) {
                  await api<Preview>("/forecast-experiments/preview", forecastPayload);
                }
                setJob(await api<Job>("/forecast-experiments", forecastPayload));
                setPreview(null);
              })
            }
          >
            Train &amp; Compare News Variants
          </button>
        </div>

        {error && (
          <div className="error" role="alert">
            {error}
            <button className="v-btn small" onClick={() => void act(refresh)}>
              Retry
            </button>
          </div>
        )}
        {preview && (
          <p className="v-note">
            {preview.article_count} stored article versions. {preview.notice}
          </p>
        )}
        {job && (
          <div className="news-job" role="status">
            <progress max={100} value={job.progress_percentage} />
            <span>
              {job.symbol} · {job.status === "complete" && job.result?.state ? job.result.state : job.status} ·{" "}
              {job.status === "complete" ? "Work finished" : job.current_step}
              {job.error ? " · " + job.error : ""}
            </span>
            {running && (
              <button className="v-btn small" onClick={() => void act(async () => setJob(await api<Job>(`/jobs/${job.job_id}/cancel`, {})))}>
                Cancel
              </button>
            )}
          </div>
        )}

        {!run ? (
          <section className="v-card v-empty">
            <h2>Test Prepared News &amp; Macro Dataset in Forecast Lab</h2>
            <p className="v-sub">
              Compares six model variants on matched forecast origins: <b>price_only</b>, <b>price_keywords</b>, <b>price_openai</b>, <b>news_openai</b>, <b>price_jev</b>, and <b>news_jev</b>. Uses your saved point-in-time news packets and classifications without making live AI calls during backtesting.
            </p>
            <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
              {onNavigateToDataset && (
                <button className="v-btn" onClick={onNavigateToDataset}>
                  1. Prepare News Dataset
                </button>
              )}
              <button
                className="v-primary"
                disabled={disabled}
                onClick={() =>
                  void act(async () => {
                    await api<Preview>("/forecast-experiments/preview", forecastPayload);
                    setJob(await api<Job>("/forecast-experiments", forecastPayload));
                  })
                }
              >
                2. Train &amp; Compare News Variants
              </button>
            </div>
          </section>
        ) : (
          <section className="v-card lab-ws">
            <div className="lab-ws-head">
              <div className="lab-tabs" role="tablist" aria-label="News Forecast Lab views">
                {(
                  [
                    ["next", "Next 7 Days Forecast"],
                    ["actual", "Predicted vs Actual History"],
                    ["metrics", "Variant Ablation Metrics"],
                    ["evidence", "Used Evidence & Provenance"],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    role="tab"
                    aria-selected={forecastTab === k}
                    className={forecastTab === k ? "on" : ""}
                    onClick={() => setForecastTab(k)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="lab-ws-controls">
                {(forecastTab === "next" || forecastTab === "actual") && (
                  <>
                    <label className="lab-toggle">
                      <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
                      Actual price (white)
                    </label>
                    <label className="lab-toggle">
                      <input type="checkbox" checked={showRange} onChange={(e) => setShowRange(e.target.checked)} />
                      80% range (blue)
                    </label>
                    <label className="v-pill">
                      <span className="v-muted">Primary</span>
                      <select
                        value={activePrimary || ""}
                        onChange={(e) => {
                          setPrimary(e.target.value);
                          setExtras([]);
                          setModelInfo(null);
                        }}
                      >
                        {Object.keys(run.variants).map((v) => (
                          <option key={v} value={v}>
                            {v.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>
                    </label>
                    {forecastTab === "actual" ? (
                      <label className="v-pill">
                        <span className="v-muted">Horizon</span>
                        <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
                          {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                            <option key={d} value={d}>
                              {d}d
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <label className="v-pill">
                        <span className="v-muted">Origin index</span>
                        <input
                          type="number"
                          min={-1}
                          max={chartData.origins.length - 1}
                          value={originIndex}
                          onChange={(e) => setOriginIndex(Number(e.target.value))}
                          title="-1 selects the latest saved origin"
                        />
                      </label>
                    )}
                  </>
                )}
              </div>
            </div>

            <div className="lab-ws-body">
              {(forecastTab === "next" || forecastTab === "actual") && (
                <div className="news-forecast-stage">
                  <div className="news-chart-main">
                    <div className="lab-info">
                      <span>
                        {run.evaluation_label} · <b>{run.intended_origins}</b> intended origins · <b>{run.matched_complete_origins.length}</b> complete common origins
                      </span>
                      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                        {Object.keys(run.variants)
                          .filter((v) => v !== activePrimary)
                          .map((v) => (
                            <label key={v} className="lab-toggle">
                              <input
                                type="checkbox"
                                checked={extras.includes(v)}
                                onChange={() => setExtras((x) => (x.includes(v) ? x.filter((k) => k !== v) : [...x, v]))}
                              />
                              Compare {v.replaceAll("_", " ")}
                            </label>
                          ))}
                      </div>
                    </div>
                    {forecastTab === "next" && displayed ? (
                      <LabChart series={series} divider={{ time: stamp(displayed.forecast.origin), label: "Forecast origin" }} fitKey={selectedRunId + originIndex} />
                    ) : forecastTab === "actual" ? (
                      <NewsHistoryGraph
                        saved={chartData.series}
                        runId={run.id}
                        primary={activePrimary}
                        extras={extras}
                        actual={showActual}
                        range={showRange}
                        horizon={horizon}
                        onPick={(i) => {
                          setOriginIndex(i);
                          setForecastTab("next");
                        }}
                      />
                    ) : (
                      <p className="ev-empty">No saved forecast available for this origin.</p>
                    )}
                  </div>

                  {/* Right Summary Sidebar matching Design Image 2 */}
                  <aside className="news-side-summary v-card">
                    <h3>7-Step MAE Comparison</h3>
                    <div className="news-side-list">
                      {Object.entries(run.variants).map(([v, x]) => {
                        const h = (run.matched_complete_origins.length ? x.matched_metrics : x.full_origin_metrics).horizons[6];
                        return (
                          <div key={v} className={`news-side-row ${v === activePrimary ? "active" : ""}`}>
                            <span>{v.replaceAll("_", " ")}</span>
                            <b className="v-num">{money(h?.mae)} USDT</b>
                          </div>
                        );
                      })}
                    </div>
                    <hr className="news-divider" />
                    <h3>Primary Variant Coverage</h3>
                    {(() => {
                      const x = run.variants[activePrimary];
                      const h = x ? (run.matched_complete_origins.length ? x.matched_metrics : x.full_origin_metrics).horizons[6] : undefined;
                      return (
                        <div className="news-cov-highlight">
                          <span className="v-num big" style={{ color: "#2DD4E8" }}>
                            {h?.coverage == null ? "—" : `${money(100 * h.coverage)}%`}
                          </span>
                          <span className="v-muted small">80% interval empirical coverage</span>
                        </div>
                      );
                    })()}
                    <hr className="news-divider" />
                    <h3>Paired Change vs Price-Only</h3>
                    <div className="news-side-list">
                      {Object.entries(run.variants).map(([v, x]) => (
                        <div key={v} className="news-side-row">
                          <span>{v.replaceAll("_", " ")}</span>
                          <b className={`v-num ${(x.paired_day7_mae_difference ?? 0) < 0 ? "up" : ""}`}>
                            {x.paired_day7_mae_difference == null ? "—" : `${x.paired_day7_mae_difference > 0 ? "+" : ""}${money(x.paired_day7_mae_difference)}`}
                          </b>
                        </div>
                      ))}
                    </div>
                    <div className="news-actions" style={{ marginTop: "auto", paddingTop: "10px" }}>
                      <button
                        className="v-btn small"
                        disabled={disabled || !run.variants[activePrimary]}
                        onClick={() =>
                          void act(async () => {
                            const f = await api<Detail["forecast"]>("/predict", { model_id: run.variants[activePrimary].model_id });
                            setDetails({ [activePrimary]: { forecast: f, actual: [] } });
                            setExtras([]);
                            setForecastTab("next");
                          })
                        }
                      >
                        Predict Latest
                      </button>
                      <button
                        className="v-btn small"
                        onClick={() => download({ experiment: run, view: chartData, selected_forecasts: details }, "news-forecast-experiment.json")}
                      >
                        Export JSON
                      </button>
                    </div>
                  </aside>
                </div>
              )}

              {forecastTab === "metrics" && (
                <div className="news-metrics-panel">
                  <p className="v-note">
                    {run.promotion.reason}{" "}
                    {run.matched_complete_origins.length === 0
                      ? "No matched comparison is available; individual metrics are not comparative proof."
                      : "Paired uncertainty and full horizon metrics are included below."}
                  </p>
                  {Object.entries(run.errors).map(([v, reason]) => (
                    <div className="ev-empty" key={v}>
                      <b>{v.replaceAll("_", " ")}</b> unavailable: {reason}
                    </div>
                  ))}
                  <div className="lab-table">
                    <table className="comparison-table">
                      <thead>
                        <tr>
                          <th>Variant</th>
                          <th>7-step samples</th>
                          <th>7-step MAE</th>
                          <th>No-change MAE</th>
                          <th>Coverage</th>
                          <th>Interval score</th>
                          <th>Paired change</th>
                          <th>Missing origins</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(run.variants).map(([v, x]) => {
                          const h = (run.matched_complete_origins.length ? x.matched_metrics : x.full_origin_metrics).horizons[6];
                          return (
                            <tr key={v} className={v === activePrimary ? "primary" : ""}>
                              <td>{v.replaceAll("_", " ")}</td>
                              <td>{h?.sample_count || 0}</td>
                              <td>{money(h?.mae)}</td>
                              <td>{money(h?.baseline_mae)}</td>
                              <td>{h?.coverage == null ? "—" : money(100 * h.coverage) + "%"}</td>
                              <td>{money(h?.interval_score)}</td>
                              <td>{money(x.paired_day7_mae_difference)}</td>
                              <td>{x.unavailable.length}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {forecastTab === "evidence" && (
                <div className="news-evidence-panel">
                  <div className="news-actions">
                    {displayed?.forecast.news_evidence && (
                      <button
                        className="v-primary"
                        onClick={() =>
                          void act(async () => {
                            const p = await api<Packet>(`/records/packet/${displayed.forecast.news_evidence!.packet_id}`);
                            setPackets((x) => (x.some((i) => i.id === p.id) ? x : [p, ...x]));
                            setPacketId(p.id);
                            setUsedEvidence({
                              forecast_id: displayed.forecast.id,
                              packet_id: p.id,
                              feature: await api(`/records/features/${displayed.forecast.news_evidence!.features_id}`),
                            });
                          })
                        }
                      >
                        Load Numerical Evidence Used by Forecast
                      </button>
                    )}
                    <button
                      className="v-btn"
                      disabled={!activePrimary}
                      onClick={() => void act(async () => setModelInfo(await api<Record<string, unknown>>(`/models/${run.variants[activePrimary].model_id}`)))}
                    >
                      Inspect Saved Primary Model
                    </button>
                  </div>
                  {usedEvidence && (
                    <div className="lab-table">
                      <h4>Numerical features consumed by forecast {usedEvidence.forecast_id.slice(0, 12)}</h4>
                      <table className="comparison-table">
                        <thead>
                          <tr>
                            <th>Feature Name</th>
                            <th>Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usedEvidence.feature.names.map((name, i) => (
                            <tr key={name}>
                              <td>{name}</td>
                              <td>{money(usedEvidence.feature.values[i])}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {modelInfo && (
                    <details open>
                      <summary>Saved model configuration and provenance</summary>
                      <pre>{JSON.stringify(modelInfo, null, 2)}</pre>
                    </details>
                  )}
                  {displayed && (
                    <div className="lab-table">
                      <h4>
                        Exact seven targets · {displayed.forecast.quote_currency} · origin {dt(displayed.forecast.origin)}
                      </h4>
                      <table className="comparison-table">
                        <thead>
                          <tr>
                            <th>Target (UTC)</th>
                            <th>Prediction (blue)</th>
                            <th>Actual (white)</th>
                            <th>80% lower</th>
                            <th>80% upper</th>
                          </tr>
                        </thead>
                        <tbody>
                          {displayed.forecast.points.map((p) => (
                            <tr key={p.target}>
                              <td>{dt(p.target)}</td>
                              <td>{money(p.median)}</td>
                              <td>{money(displayed.actual.find((a) => a.time === p.target)?.value)}</td>
                              <td>{money(p.lower)}</td>
                              <td>{money(p.upper)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        )}
      </section>
    );
  }

  // Fallback ("full" mode if rendered standalone)
  return (
    <section className="news-workbench">
      <header className="news-head">
        <div>
          <h2>
            News &amp; Macro Lab <span className="ev-dim small">Experimental</span>
          </h2>
          <p className="v-sub">Timestamped evidence and measured experiments. News interpretation is not a price forecast.</p>
        </div>
        <select
          aria-label="News instrument"
          value={market}
          onChange={(e) => {
            setMarket(e.target.value);
            setPacketId("");
            setRunId("");
            setPreview(null);
            setEvaluation(null);
            setArticleId("");
            setUsedEvidence(null);
            setModelInfo(null);
          }}
        >
          {(status?.markets || [{ instrument_id: symbol, name: symbol }]).map((m) => (
            <option key={m.instrument_id} value={m.instrument_id}>
              {m.name}
            </option>
          ))}
        </select>
        <button className="v-btn" onClick={() => void act(refresh)}>
          Refresh
        </button>
      </header>
      <nav className="v-seg" aria-label="News lab views">
        {["news", "classification", "forecasting"].map((v) => (
          <button
            key={v}
            aria-pressed={view === v}
            className={view === v ? "on" : ""}
            onClick={() => {
              setView(v);
              setPreview(null);
            }}
          >
            {v === "news" ? "News & timestamps" : v === "classification" ? "Classification experiment" : "Forecast models"}
          </button>
        ))}
      </nav>
    </section>
  );
}

function NewsHistoryGraph({
  saved,
  runId,
  primary,
  extras,
  actual,
  range,
  horizon,
  onPick,
}: {
  saved: Record<string, HistoryPoint[]>;
  runId: string;
  primary: string;
  extras: string[];
  actual: boolean;
  range: boolean;
  horizon: number;
  onPick: (i: number) => void;
}) {
  const series = useMemo<ChartSeries[]>(() => {
    const result: ChartSeries[] = [];
    const reference = saved[primary] || [];
    if (actual)
      result.push({
        id: "actual",
        label: "Actual price",
        color: "#F1F5FA",
        points: reference.flatMap((p) => (p.actual == null ? [] : [{ time: stamp(p.target), value: p.actual }])),
        width: 2,
      });
    for (const [i, v] of [primary, ...extras.filter((v) => v !== primary)].entries()) {
      const rows = saved[v];
      if (!rows) continue;
      result.push({
        id: v,
        label: v,
        color: i === 0 ? "#4C9AFF" : ["#F6B84A", "#B690FF", "#78E4A1"][i - 1],
        points: rows.map((p) => ({ time: stamp(p.target), value: p.median })),
        width: i === 0 ? 3 : 2,
      });
      if (i === 0 && range)
        for (const key of ["lower", "upper"] as const)
          result.push({
            id: key,
            label: key,
            color: "#4C9AFF",
            dashed: true,
            points: rows.map((p) => ({ time: stamp(p.target), value: p[key] })),
          });
    }
    return result;
  }, [saved, primary, extras, actual, range]);
  if (!Object.keys(saved).length) return <p className="ev-empty">No saved target-aligned forecasts available.</p>;
  return (
    <LabChart
      series={series}
      fitKey={runId + horizon}
      onPick={(time) => {
        const p = saved[primary]?.find((p) => stamp(p.target) === time);
        if (p) onPick(p.origin_index);
      }}
    />
  );
}
