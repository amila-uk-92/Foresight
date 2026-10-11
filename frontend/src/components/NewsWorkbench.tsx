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

export function NewsWorkbench({ symbol = "BTCUSDT" }: { symbol?: string }) {
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
  const [view, setView] = useState("news");
  const [market, setMarket] = useState(symbol);
  const [origin, setOrigin] = useState(() => new Date().toISOString());
  const [policy, setPolicy] = useState("strict");
  const [lookback, setLookback] = useState(7);
  const [packetId, setPacketId] = useState("");
  const [classifier, setClassifier] = useState("keywords");
  const [budget, setBudget] = useState("0");
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
  const [graphFocus, setGraphFocus] = useState(false);
  const [graphView, setGraphView] = useState("next");
  const [horizon, setHorizon] = useState(7);
  const [originIndex, setOriginIndex] = useState(-1);
  const [annotation, setAnnotation] = useState({ annotator: "", relevance: "unknown", category: "unknown", framing: "unknown", note: "" });
  const [usedEvidence, setUsedEvidence] = useState<{ forecast_id: string; packet_id: string; feature: { names: string[]; values: number[] } } | null>(null);
  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [evaluation, setEvaluation] = useState<ClassificationEvaluation | null>(null);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const [s, a, p, c, r, j] = await Promise.all([
      api<Status>("/status"), api<{ items: Article[]; total: number }>(`/records/article?page_size=100&page=${articlePage}&provider=${encodeURIComponent(providerFilter)}&q=${encodeURIComponent(search)}`),
      api<{ items: Packet[] }>(`/records/packet?symbol=${encodeURIComponent(market)}`),
      api<{ items: Classification[] }>(`/records/classification?symbol=${encodeURIComponent(market)}&page_size=100`),
      api<{ items: ForecastRun[] }>(`/records/forecast_experiment?symbol=${encodeURIComponent(market)}`), api<Job | null>("/latest-job"),
    ]);
    if (sequence !== refreshSequence.current) return;
    setStatus(s); setArticles(a.items); setArticleTotal(a.total); setPackets(p.items); setClassifications(c.items); setRuns(r.items); setJob(j);
  }, [market, articlePage, providerFilter, search]);
  useEffect(() => { let stop = false; refresh().catch(e => !stop && setError(e.message)); return () => { stop = true; }; }, [refresh]);
  useEffect(() => { api<Job | null>("/latest-job").then(setJob).catch(e => setError(e.message)); }, []);
  const running = job && ["pending", "running"].includes(job.status);
  useEffect(() => {
    if (!job || !running) return;
    let stop = false;
    const t = setInterval(() => api<Job>("/jobs/" + job.job_id).then(j => {
      if (stop) return;
      setJob(j);
      if (!["pending", "running"].includes(j.status)) {
        setOrigin(new Date().toISOString());
        if (j.kind === "news-forecast" && j.result?.id) setRunId(j.result.id);
        void refresh().catch(e => setError(e.message));
      }
    }).catch(e => !stop && setError(e.message)), 1000);
    return () => { stop = true; clearInterval(t); };
  }, [job, running, refresh]);
  async function act(fn: () => Promise<void>) { setBusy(true); setError(""); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  const packet = packets.find(p => p.id === packetId);
  const article = articles.find(a => a.id === articleId) || (inspectedArticle?.id === articleId ? inspectedArticle : null);
  useEffect(() => { let stop = false; if (articleId) api<Article>(`/records/article/${articleId}`).then(a => !stop && setInspectedArticle(a)).catch(e => !stop && setError(e.message)); return () => { stop = true; }; }, [articleId]);
  const run = runs.find(r => r.id === runId) || runs[0];
  const selectedRunId = run?.id || "";
  useEffect(() => {
    let stop = false;
    const controller = new AbortController();
    if (selectedRunId) api<GraphView>(`/forecast-experiments/${selectedRunId}/view?origin_index=${originIndex}&horizon=${horizon}`, undefined, controller.signal).then(x => {
      if (!stop) { setDetails(x.details); setChartData(x); }
    }).catch(e => !stop && setError(e.message));
    return () => { stop = true; controller.abort(); };
  }, [selectedRunId, originIndex, horizon]);
  const activePrimary = run?.variants[primary] ? primary : Object.keys(run?.variants || {})[0];
  const displayed = details[activePrimary];
  const series = useMemo<ChartSeries[]>(() => {
    if (!displayed) return [];
    const lines: ChartSeries[] = [];
    if (showActual) lines.push({ id: "actual", label: "Actual price", color: "#F1F5FA", points: displayed.actual.map(p => ({ time: stamp(p.time), value: p.value })), width: 2 });
    for (const [i, v] of [activePrimary, ...extras.filter(v => v !== activePrimary)].entries()) {
      const d = details[v]; if (!d) continue;
      const points = [{ time: stamp(d.forecast.origin), value: d.forecast.origin_price }, ...d.forecast.points.map(p => ({ time: stamp(p.target), value: p.median }))];
      lines.push({ id: v, label: v.replaceAll("_", " "), color: i === 0 ? "#4C9AFF" : ["#F6B84A", "#B690FF", "#78E4A1"][i - 1] || "#EC729D", points, width: i === 0 ? 3 : 2 });
      if (v === activePrimary && showRange) for (const key of ["lower", "upper"] as const) lines.push({ id: key, label: "80% " + key, color: "#4C9AFF", dashed: true, width: 1, points: d.forecast.points.map(p => ({ time: stamp(p.target), value: p[key] })) });
    }
    return lines;
  }, [displayed, details, activePrimary, extras, showActual, showRange]);
  const classificationPayload = { packet_id: packetId, classifier, budget_usd: Number(budget), max_articles: 100 };
  const visibleClassifications = classifications.filter(c => packet?.article_ids.includes(c.article_id) && c.classifier === classifier && (!status?.classifiers.find(x => x.id === classifier)?.model || c.model === status.classifiers.find(x => x.id === classifier)?.model));
  const forecastPayload = { symbol: market, policy, lookback_days: 30, minimum_origins: 30, evidence_lookback_days: lookback };
  const disabled = busy || !!running;
  return <section className={`news-workbench${graphFocus && view === "forecasting" ? " news-focus" : ""}`}>
    <header className="news-head"><div><h2>News &amp; Macro Lab <span className="ev-dim small">Experimental</span></h2><p className="v-sub">Timestamped evidence and measured experiments. News interpretation is not a price forecast.</p></div>
      <select aria-label="News instrument" value={market} onChange={e => { setMarket(e.target.value); setPacketId(""); setRunId(""); setPreview(null); setEvaluation(null); setArticleId(""); setUsedEvidence(null); setModelInfo(null); }}>
        {(status?.markets || [{ instrument_id: symbol, name: symbol }]).map(m => <option key={m.instrument_id} value={m.instrument_id}>{m.name}</option>)}
      </select><button className="v-btn" onClick={() => void act(refresh)}>Refresh</button>
    </header>
    <nav className="v-seg" aria-label="News lab views">{["news", "classification", "forecasting"].map(v => <button key={v} aria-pressed={view === v} className={view === v ? "on" : ""} onClick={() => { setView(v); setPreview(null); }}>{v === "news" ? "News & timestamps" : v === "classification" ? "Classification experiment" : "Forecast models"}</button>)}</nav>
    {error && <div className="error" role="alert">{error}<button className="v-btn small" onClick={() => void act(refresh)}>Retry reads</button></div>}
    {job && <div className="news-job" role="status"><progress max={100} value={job.progress_percentage} /><span>{job.symbol === "NEWS" ? "Shared news" : job.symbol} · {job.status === "complete" && job.result?.state ? job.result.state : job.status} · {job.status === "complete" ? "Work finished" : job.current_step}{job.error ? " · " + job.error : ""}</span>{running && <button className="v-btn small" onClick={() => void act(async () => setJob(await api<Job>(`/jobs/${job.job_id}/cancel`, {})))}>Cancel</button>}{job.result?.state && <span>Result: {job.result.state}</span>}{job.manifest_id && ["cancelled", "failed"].includes(job.status) && <button className="v-btn small" onClick={() => void act(async () => download(await api(`/jobs/${job.job_id}/retained`), "retained-news-artifacts.json"))}>Export retained partial results</button>}</div>}
    {view === "news" && <>
      <div className="news-controls"><button className="v-btn" disabled={disabled} onClick={() => void act(async () => setJob(await api<Job>("/collect", { source: "federal-reserve" })))}>Collect official macro RSS</button>
        <label>Import permitted JSON/JSONL<input type="file" accept=".json,.jsonl" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
        <button className="v-btn" disabled={disabled || !file} onClick={() => void act(async () => {
          if (!file || file.size > 2_000_000) throw new Error("Choose a JSON/JSONL file under 2MB");
          const text = await file.text(); const rows = file.name.endsWith(".jsonl") ? text.trim().split("\n").map(s => JSON.parse(s)) : JSON.parse(text);
          setJob(await api<Job>("/import", { provider: "local", articles: Array.isArray(rows) ? rows : rows.articles }));
        })}>Import news</button>
      </div>
      <p className="v-note">{status?.article_count ?? 0} real article versions stored. RSS is forward collection, not a four-year archive. Stock and gold adapters require explicit instrument configuration.</p>
      <div className="news-controls"><label>Evidence cutoff (UTC)<input aria-label="News evidence cutoff" value={origin} onChange={e => setOrigin(e.target.value)} /></label><label>Past sessions/days<select value={lookback} onChange={e => { setLookback(Number(e.target.value)); setPreview(null); }}><option value={1}>1</option><option value={7}>7</option><option value={30}>30</option></select></label>
        <label>Availability policy<select value={policy} onChange={e => { setPolicy(e.target.value); setPreview(null); }}><option value="strict">Strict as-of</option><option value="exploratory">Exploratory publication dates</option></select></label>
        <button className="v-primary" disabled={disabled} onClick={() => void act(async () => { const p = await api<Packet>("/packets", { symbol: market, origin, lookback_days: lookback, policy }); await refresh(); setPacketId(p.id); setUsedEvidence(null); })}>Build evidence packet</button>
      </div>
      {packet && <p className="v-note">Packet: {packet.article_ids.length} eligible versions · {packet.excluded.length} excluded · {packet.coverage_state}. Origin {dt(packet.origin)}. <button className="v-btn small" onClick={() => download(packet, "evidence-packet.json")}>Export packet</button></p>}
      {usedEvidence?.packet_id === packetId && usedEvidence && <details open><summary>Numerical evidence actually used by forecast {usedEvidence.forecast_id.slice(0, 12)}</summary><table className="comparison-table"><tbody>{usedEvidence.feature.names.map((name, i) => <tr key={name}><td>{name}</td><td>{money(usedEvidence.feature.values[i])}</td></tr>)}</tbody></table><button className="v-btn small" onClick={() => download(usedEvidence, "used-news-features.json")}>Export used features</button></details>}
      <div className="news-controls"><label>Source<select value={providerFilter} onChange={e => { setProviderFilter(e.target.value); setArticlePage(1); }}><option value="">All sources</option>{status?.imported_providers?.map(p => <option key={p}>{p}</option>)}</select></label><label>Search news<input aria-label="Search news" value={search} onChange={e => { setSearch(e.target.value); setArticlePage(1); }} /></label><button className="v-btn small" disabled={articlePage === 1} onClick={() => setArticlePage(x => x - 1)}>Previous articles</button><span>Page {articlePage} · {articleTotal} matching versions</span><button className="v-btn small" disabled={articlePage * 100 >= articleTotal} onClick={() => setArticlePage(x => x + 1)}>Next articles</button></div>
      <div className="lab-table"><table className="comparison-table"><thead><tr><th>Article</th><th>Published</th><th>Available</th><th>Availability</th><th>Packet</th></tr></thead><tbody>{articles.map(a => <tr key={a.id}><td><button className="news-link" onClick={() => setArticleId(a.id)}>{a.headline}</button><div className="v-muted small">{a.publisher} · {a.content_scope}</div></td><td>{dt(a.published_at)}</td><td>{dt(a.effective_available_at)}</td><td>{a.availability_quality}</td><td>{packet ? packet.article_ids.includes(a.id) ? "Included" : packet.excluded.find(x => x.id === a.id)?.reason || "Superseded version" : "Not checked"}</td></tr>)}</tbody></table>{!articles.length && <p className="ev-empty">No news imported. Collect a source or import permitted records.</p>}</div>
      {article && <article className="news-detail"><button className="v-btn small" onClick={() => setArticleId("")}>Close article</button><h3>{article.headline}</h3><p>{article.text || "Headline only; full article text not available."}</p><a href={article.url} target="_blank" rel="noreferrer">Original source</a><p className="v-sub">Ingested {dt(article.ingested_at)} · rights: {article.rights} · version {article.id.slice(0, 12)}{article.predecessor_id && " · revision"}</p>
        <h4>Human evaluation label</h4><div className="news-controls"><input placeholder="Annotator name" aria-label="Annotator" value={annotation.annotator} onChange={e => setAnnotation({ ...annotation, annotator: e.target.value })} />{(["relevance", "category", "framing"] as const).map(k => <label key={k}>{k}<select value={annotation[k]} onChange={e => setAnnotation({ ...annotation, [k]: e.target.value })}>{(k === "relevance" ? ["unknown", "relevant", "irrelevant"] : k === "framing" ? ["unknown", "positive", "negative", "mixed", "neutral"] : ["unknown", "regulatory", "macro", "security", "market_infrastructure", "flows_adoption", "corporate", "supply_network", "other"]).map(v => <option key={v}>{v}</option>)}</select></label>)}<button className="v-btn" disabled={disabled || !annotation.annotator} onClick={() => void act(async () => { await api("/labels", { ...annotation, article_id: article.id, symbol: market }); })}>Save immutable label</button></div>
      </article>}
    </>}
    {view === "classification" && <>
      <div className="news-controls"><label>Saved packet<select value={packetId} onChange={e => { setPacketId(e.target.value); setPreview(null); }}><option value="">Select packet</option>{packets.map(p => <option key={p.id} value={p.id}>{dt(p.origin)} · {p.policy} · {p.article_ids.length} articles</option>)}</select></label>
        <label>Classifier<select value={classifier} onChange={e => { setClassifier(e.target.value); setPreview(null); }}><option value="keywords">Keyword/rule comparator</option><option value="jev">Jev · {(status?.classifiers.find(c => c.id === "jev")?.state === "configured" ? "Ready" : "Not configured")}</option><option value="openai">OpenAI · {status?.classifiers.find(c => c.id === "openai")?.state === "configured" ? "Ready" : "Not configured"}</option></select></label>
        <label>Hard experiment budget (USD)<input type="number" min="0" max="100" step="0.01" value={budget} onChange={e => { setBudget(e.target.value); setPreview(null); }} /></label>
        <button className="v-btn" disabled={disabled || !packetId} onClick={() => void act(async () => setPreview(await api<Preview>("/classifications/preview", classificationPayload)))}>Preview classification</button>
        <button className="v-primary" disabled={disabled || !preview || !packetId || classifier !== "keywords" && (Number(budget) <= 0 || status?.classifiers.find(c => c.id === classifier)?.state !== "configured" || classifier === "openai" && Number(budget) > (status?.classifiers.find(c => c.id === "openai")?.max_experiment_usd ?? 0))} onClick={() => void act(async () => { setJob(await api<Job>("/classifications", classificationPayload)); setPreview(null); })}>Run classification</button>
      </div>
      {preview && <p className="v-note">{preview.pending_ids?.length ?? 0} pending · {preview.cached_count ?? 0} cached · {preview.omitted_count ?? 0} omitted. Conservative maximum ${money(preview.conservative_max_cost_usd)}. No call occurs until Run.</p>}
      <p className="v-note">OpenAI and Jev need a server API key, explicit enablement and a budget. ChatGPT subscriptions do not include API billing. OpenAI confidence is self-reported, not calibrated. Keyword indicators are not calibrated. Novelty is unknown until earlier-event context is implemented.</p>
      {classifier === "openai" && <p className="v-note">Pinned model: {status?.classifiers.find(c => c.id === "openai")?.model}. Cumulative API cap ${money(status?.classifiers.find(c => c.id === "openai")?.total_budget?.limit_usd)} · remaining ${money(status?.classifiers.find(c => c.id === "openai")?.total_budget?.remaining_usd)} · per-experiment cap ${money(status?.classifiers.find(c => c.id === "openai")?.max_experiment_usd)}. Reservations survive restart; this cap covers Foresight calls only.</p>}
      <div className="lab-table"><table className="comparison-table"><thead><tr><th style={{ width: "42%" }}>Article version</th><th>Classifier</th><th>Relevant?</th><th>Category</th><th>Framing</th><th>Confidence</th><th>Estimated cost</th></tr></thead><tbody>{visibleClassifications.map(c => <tr key={c.id}><td><button className="news-link" onClick={() => { setArticleId(c.article_id); setView("news"); }}>{articles.find(a => a.id === c.article_id)?.headline || c.article_id.slice(0, 12)}</button></td><td>{c.model}</td><td>{c.answers.relevance.choice}</td><td>{c.answers.category.choice}</td><td>{c.answers.framing.choice}</td><td>{c.classifier === "keywords" ? "Not estimated" : money(c.answers.relevance.confidence)}</td><td>${money(c.cost_usd)}</td></tr>)}</tbody></table></div>
      {!visibleClassifications.length && <p className="ev-empty">No saved results for this classifier and packet.</p>}
      <button className="v-btn" disabled={disabled || !packetId} onClick={() => void act(async () => setEvaluation(await api<ClassificationEvaluation>("/classification-evaluations", { packet_id: packetId, classifier: classifier === "openai" ? "openai" : "jev" })))}>Evaluate saved human labels</button>
      {evaluation && <section><h3>Extraction quality · {evaluation.status}</h3><p>{evaluation.matched_article_ids.length} common labelled articles; {evaluation.conflicting_article_ids.length} annotation conflicts. This is not forecasting accuracy.</p><div className="lab-table"><table className="comparison-table"><thead><tr><th>Classifier</th><th>Samples</th><th>Relevance F1</th><th>Category F1</th><th>Framing F1</th><th>Brier</th><th>Abstentions</th></tr></thead><tbody>{Object.entries(evaluation.results).map(([k, r]) => <tr key={k}><td>{k}</td><td>{r.sample_count}</td><td>{money(r.metrics.relevance.macro_f1)}</td><td>{money(r.metrics.category.macro_f1)}</td><td>{money(r.metrics.framing.macro_f1)}</td><td>{money(r.multiclass_brier)}</td><td>{r.abstentions}</td></tr>)}</tbody></table></div><details><summary>Confusion matrices</summary><pre>{JSON.stringify(evaluation.results, null, 2)}</pre></details><button className="v-btn" onClick={() => download(evaluation, "classification-quality.json")}>Export measured results</button></section>}
    </>}
    {view === "forecasting" && <>
      <p className="v-note">Six declared variants: price only, price + keywords, price + Jev, Jev news specialist, price + OpenAI and OpenAI news specialist. Uses saved classifications; no AI calls. Missing historical evidence blocks the affected variants. Incumbent unchanged.</p>
      <div className="news-controls"><label>Evidence policy<select value={policy} onChange={e => { setPolicy(e.target.value); setPreview(null); }}><option value="strict">Strict as-of</option><option value="exploratory">Exploratory</option></select></label><button className="v-btn" disabled={disabled} onClick={() => void act(async () => setPreview(await api<Preview>("/forecast-experiments/preview", forecastPayload)))}>Preview forecast experiment</button><button className="v-primary" disabled={disabled || !preview} onClick={() => void act(async () => { setJob(await api<Job>("/forecast-experiments", forecastPayload)); setPreview(null); })}>Train &amp; compare news variants</button>
        <label>Saved experiment<select value={selectedRunId} onChange={e => { setRunId(e.target.value); setOriginIndex(-1); setDetails({}); setModelInfo(null); }}><option value="">Select experiment</option>{runs.map(r => <option key={r.id} value={r.id}>{r.symbol} · {r.state} · {r.id.slice(-8)}</option>)}</select></label>
      </div>{preview && <p className="v-note">{preview.article_count} stored article versions. {preview.notice}</p>}
      {run && <><p className="v-note">{run.evaluation_label} · {run.intended_origins} intended origins · {run.matched_complete_origins.length} complete common origins.</p>
        <details className="news-metrics"><summary>Results &amp; coverage · {Object.keys(run.errors).length} unavailable variants · {run.matched_complete_origins.length} matched origins</summary>
        {Object.entries(run.errors).map(([v, reason]) => <div className="ev-empty" key={v}>{v.replaceAll("_", " ")}: {reason}</div>)}
        <div className="lab-table"><table className="comparison-table"><thead><tr><th>Variant</th><th>7-step samples</th><th>7-step MAE</th><th>No-change MAE</th><th>Coverage</th><th>Interval score</th><th>Paired change</th><th>Missing origins</th></tr></thead><tbody>{Object.entries(run.variants).map(([v, x]) => { const h = (run.matched_complete_origins.length ? x.matched_metrics : x.full_origin_metrics).horizons[6]; return <tr key={v}><td>{v.replaceAll("_", " ")}</td><td>{h?.sample_count || 0}</td><td>{money(h?.mae)}</td><td>{money(h?.baseline_mae)}</td><td>{h?.coverage == null ? "—" : money(100 * h.coverage) + "%"}</td><td>{money(h?.interval_score)}</td><td>{money(x.paired_day7_mae_difference)}</td><td>{x.unavailable.length}</td></tr>; })}</tbody></table></div>
        <p className="v-note">{run.promotion.reason} {run.matched_complete_origins.length === 0 ? "No matched comparison is available; individual metrics are not comparative proof." : "Paired uncertainty and full horizon metrics are in the export."}</p>
        </details>
        <div className="news-graph"><div className="news-controls graph-controls"><div className="v-seg"><button className={graphView === "next" ? "on" : ""} onClick={() => setGraphView("next")}>Selected seven-step forecast</button><button className={graphView === "actual" ? "on" : ""} onClick={() => setGraphView("actual")}>Predicted vs actual history</button></div>
          <button className="v-btn small" aria-pressed={graphFocus} onClick={() => setGraphFocus(x => !x)}>{graphFocus ? "Show experiment controls" : "Expand graph"}</button>
          <label>Primary model<select value={activePrimary || ""} onChange={e => { setPrimary(e.target.value); setExtras([]); setModelInfo(null); }}>{Object.keys(run.variants).map(v => <option key={v}>{v}</option>)}</select></label>
          {Object.keys(run.variants).filter(v => v !== activePrimary).map(v => <label key={v}><input type="checkbox" checked={extras.includes(v)} onChange={() => setExtras(x => x.includes(v) ? x.filter(k => k !== v) : [...x, v])} />{v.replaceAll("_", " ")}</label>)}
          <label><input type="checkbox" checked={showActual} onChange={e => setShowActual(e.target.checked)} />Actual price (white)</label><label><input type="checkbox" checked={showRange} onChange={e => setShowRange(e.target.checked)} />80% range (blue)</label>
          {graphView === "actual" ? <label>Horizon<select value={horizon} onChange={e => setHorizon(Number(e.target.value))}>{[1,2,3,4,5,6,7].map(d => <option key={d}>{d}</option>)}</select></label> : <label>Origin index<input type="number" min={-1} max={chartData.origins.length - 1} value={originIndex} onChange={e => setOriginIndex(Number(e.target.value))} title="-1 selects the latest saved origin" /></label>}
        </div>
        {graphView === "next" && displayed ? <LabChart series={series} divider={{ time: stamp(displayed.forecast.origin), label: "Forecast origin" }} fitKey={selectedRunId + originIndex} /> : graphView === "actual" ? <NewsHistoryGraph saved={chartData.series} runId={run.id} primary={activePrimary} extras={extras} actual={showActual} range={showRange} horizon={horizon} onPick={i => { setOriginIndex(i); setGraphView("next"); }} /> : <p className="ev-empty">No saved forecast available for this origin.</p>}
        </div>
        <div className="news-actions">
        <button className="v-btn" onClick={() => download({ experiment: run, view: chartData, selected_forecasts: details }, "news-forecast-experiment.json")}>Export experiment</button>
        {displayed?.forecast.news_evidence && <button className="v-btn" onClick={() => void act(async () => { const p = await api<Packet>(`/records/packet/${displayed.forecast.news_evidence!.packet_id}`); setPackets(x => x.some(i => i.id === p.id) ? x : [p, ...x]); setPacketId(p.id); setUsedEvidence({ forecast_id: displayed.forecast.id, packet_id: p.id, feature: await api(`/records/features/${displayed.forecast.news_evidence!.features_id}`) }); setView("news"); })}>Inspect evidence actually used</button>}
        <button className="v-btn" disabled={disabled || !run.variants[activePrimary]} onClick={() => void act(async () => { const f = await api<Detail["forecast"]>("/predict", { model_id: run.variants[activePrimary].model_id }); setDetails({ [activePrimary]: { forecast: f, actual: [] } }); setExtras([]); setGraphView("next"); })}>Predict with saved primary model</button>
        <button className="v-btn" disabled={!activePrimary} onClick={() => void act(async () => setModelInfo(await api<Record<string, unknown>>(`/models/${run.variants[activePrimary].model_id}`)))}>Inspect saved primary model</button>
        </div>
        {modelInfo && <details open><summary>Saved model configuration and provenance</summary><button className="v-btn small" onClick={() => setModelInfo(null)}>Close model</button><pre>{JSON.stringify(modelInfo, null, 2)}</pre></details>}
        {displayed && <details><summary>Exact seven targets · {displayed.forecast.quote_currency} · origin {dt(displayed.forecast.origin)}</summary><table className="comparison-table"><thead><tr><th>Target (UTC)</th><th>Prediction (blue)</th><th>Actual (white)</th><th>80% lower</th><th>80% upper</th></tr></thead><tbody>{displayed.forecast.points.map(p => <tr key={p.target}><td>{dt(p.target)}</td><td>{money(p.median)}</td><td>{money(displayed.actual.find(a => a.time === p.target)?.value)}</td><td>{money(p.lower)}</td><td>{money(p.upper)}</td></tr>)}</tbody></table></details>}
      </>}
    </>}
  </section>;
}

function NewsHistoryGraph({ saved, runId, primary, extras, actual, range, horizon, onPick }: { saved: Record<string, HistoryPoint[]>; runId: string; primary: string; extras: string[]; actual: boolean; range: boolean; horizon: number; onPick: (i: number) => void }) {
  const series = useMemo<ChartSeries[]>(() => {
    const result: ChartSeries[] = [];
    const reference = saved[primary] || [];
    if (actual) result.push({ id: "actual", label: "Actual price", color: "#F1F5FA", points: reference.flatMap(p => p.actual == null ? [] : [{ time: stamp(p.target), value: p.actual }]), width: 2 });
    for (const [i, v] of [primary, ...extras.filter(v => v !== primary)].entries()) {
      const rows = saved[v]; if (!rows) continue;
      result.push({ id: v, label: v, color: i === 0 ? "#4C9AFF" : ["#F6B84A", "#B690FF", "#78E4A1"][i - 1], points: rows.map(p => ({ time: stamp(p.target), value: p.median })), width: i === 0 ? 3 : 2 });
      if (i === 0 && range) for (const key of ["lower", "upper"] as const) result.push({ id: key, label: key, color: "#4C9AFF", dashed: true, points: rows.map(p => ({ time: stamp(p.target), value: p[key] })) });
    }
    return result;
  }, [saved, primary, extras, actual, range]);
  if (!Object.keys(saved).length) return <p className="ev-empty">No saved target-aligned forecasts available.</p>;
  return <LabChart series={series} fitKey={runId + horizon} onPick={time => { const p = saved[primary]?.find(p => stamp(p.target) === time); if (p) onPick(p.origin_index); }} />;
}
