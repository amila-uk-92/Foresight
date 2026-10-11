import type { ReactNode } from "react";
import type { ForecastEvidence, RecordState, StateNote } from "../forecastTypes";
import { useForecastEvidence, type EvidenceLoad } from "./evidenceApi";
import { fmt, shortDate } from "./viz";

const when = (s: string | null | undefined) =>
  s ? `${shortDate(s, true)} ${new Date(s).toISOString().slice(11, 16)} UTC` : "—";

const STATE_TEXT: Record<RecordState, string> = {
  recorded: "Recorded",
  empty: "Recorded, none found",
  not_recorded: "Not recorded",
  not_implemented: "Planned — not implemented",
  unavailable: "Unavailable",
};
const AGENT_TEXT: Record<string, string> = {
  active: "Ran",
  planned: "Planned — not implemented",
  pending: "Waiting for outcomes",
  not_recorded: "Not recorded",
  experimental: "Experimental",
  unavailable: "Unavailable",
  bypassed: "Bypassed",
};
const tone = (s: string) =>
  s === "recorded" || s === "active" || s === "known" ? "ok" : s === "unavailable" || s === "missing" ? "bad" : s === "pending" ? "wait" : "off";

function State({ state, children }: { state: string; children?: ReactNode }) {
  return <span className={`ev-state ${tone(state)}`}>{children ?? (STATE_TEXT as Record<string, string>)[state] ?? state}</span>;
}

function Note({ note, compact = false }: { note: StateNote; compact?: boolean }) {
  const why = note.error || note.reason;
  return (
    <span className="ev-note" title={compact ? why : undefined}>
      <State state={note.state} />
      {why && !compact && <small>{why}</small>}
    </span>
  );
}

// Reasoning items have no frozen contract yet; show their own text, never a summary of our own.
const describe = (item: unknown) =>
  typeof item === "string"
    ? item
    : item && typeof item === "object" && "text" in item
      ? String((item as { text: unknown }).text)
      : JSON.stringify(item);

function ReasoningList({ title, items, empty }: { title: string; items: unknown[]; empty: string }) {
  return (
    <div className="ev-reason">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((x, i) => (
            <li key={i}>{describe(x)}</li>
          ))}
        </ul>
      ) : (
        <p className="ev-empty">{empty}</p>
      )}
    </div>
  );
}

export function EvidenceFailure({ load, onRetry }: { load: EvidenceLoad; onRetry: () => void }) {
  if (load.status === "ok") return null;
  if (load.status === "loading") return <p className="v-sub lab-wait">Loading the saved evidence…</p>;
  const title = load.status === "missing" ? "Saved forecast not found" : load.status === "no-endpoint" ? "Evidence not available on this server" : "Evidence service unavailable";
  return (
    <div className="ev-failure" role="alert">
      <strong>{title}</strong>
      <span>{load.message}</span>
      {load.status !== "missing" && (
        <button className="v-btn small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

// Outcome availability, prediction uncertainty and trade eligibility, each from its own record.
export function StatusTriple({ e }: { e: ForecastEvidence }) {
  const o = e.outcomes;
  const p = e.numerical.points[6];
  const pending = o.points.filter((x) => x.status === "pending");
  return (
    <div className="ev-triple">
      <section aria-label="Outcome availability">
        <h4>Outcome availability</h4>
        <div className="ev-outcomes">
          {o.points.map((x) => (
            <span key={x.day} className={x.status} title={`Day ${x.day} · ${shortDate(x.target, true)}: ${x.status === "known" ? `actual ${fmt(x.actual_price)}` : x.reason}`}>
              <i />
              {shortDate(x.target)}
            </span>
          ))}
        </div>
        <p>
          <b>{o.counts.known}</b> known · <b>{o.counts.pending}</b> pending · <b>{o.counts.missing}</b> missing
        </p>
        <small>
          {pending.length
            ? `${pending[0].reason}${o.observed_through ? ` (data ends ${when(o.observed_through)})` : ""}.`
            : o.counts.missing
              ? "Missing targets have no candle in the dataset; they are never scored."
              : "All seven outcomes are in the data."}
        </small>
      </section>
      <section aria-label="Prediction uncertainty">
        <h4>Prediction uncertainty</h4>
        <p>
          Day 7: <b className="v-num">{fmt(p?.lower)}–{fmt(p?.upper)}</b>
        </p>
        <p>
          Rise <b className="v-num">{fmt((e.numerical.probabilities?.positive ?? NaN) * 100)}%</b> · fall{" "}
          <b className="v-num">{fmt((e.numerical.probabilities?.negative ?? NaN) * 100)}%</b>
        </p>
        <small>{e.numerical.definitions?.interval || "Interval definition not recorded"}; stored with the forecast, not agent agreement.</small>
      </section>
      <section aria-label="Trade eligibility">
        <h4>Trade eligibility</h4>
        <p>
          <State state="not_implemented">{e.trading.label}</State>
        </p>
        <small>{e.trading.reason}</small>
      </section>
    </div>
  );
}

export function SourceList({ e, compact = false }: { e: ForecastEvidence; compact?: boolean }) {
  const m = e.sources.market_data;
  if (m.state !== "recorded") return <Note note={m} />;
  return (
    <div className="ev-sources">
      <p className="ev-meta">
        {m.venue} {m.symbol} · {m.candle_count} hourly candles, last closed {when(m.latest_candle_close)}
      </p>
      <ul>
        {m.records!.map((r) => (
          <li key={r.source_id} title={`${r.url ?? ""}\nSHA-256 ${r.sha256 ?? "not recorded"}`}>
            <span className="ev-cite">[{r.source_id}]</span>
            <span>
              {r.candles_used} candle{r.candles_used > 1 ? "s" : ""} to {when(r.last_candle_close)}
            </span>
            <span className={r.checksum_verified ? "ev-ok" : "ev-bad"}>{r.checksum_verified ? "SHA-256 verified" : "Checksum not verified"}</span>
            {!compact && (
              <span className="ev-dim">
                Published: not recorded · retrieved {shortDate(r.retrieved_at || "", true)}
                {r.retrieved_after_origin && ", after this origin"}
              </span>
            )}
          </li>
        ))}
      </ul>
      {!compact && (
        <small className="ev-dim" title={`${m.availability_rule} ${m.publication_note}`}>
          Each candle counts as available once it closes. The archive has no publication times.
        </small>
      )}
    </div>
  );
}

export function EvidenceView({ e, label, actions }: { e: ForecastEvidence; label: string; actions?: ReactNode }) {
  const f = e.forecast;
  const r = e.reasoning;
  const reasonEmpty = r.state === "not_implemented" ? "Planned — not implemented" : r.forecast_state === "not_recorded" ? "Reasoning not recorded" : "None recorded";
  const w = e.numerical.coordination.weights;
  const job = e.cost_latency.job;
  return (
    <>
      <div className="lab-info">
        <span>
          <b>{label}</b> forecast made {when(f.origin)}
          {f.historical_origin && <em className="ev-tag">historical origin, saved {shortDate(f.generated_at, true)}</em>}
        </span>
        <span>
          Targets <b>{shortDate(f.targets[0].target)} – {shortDate(f.targets[6].target, true)}</b> 00:00 UTC
        </span>
        <span>
          Evidence cutoff <b>{when(f.evidence_cutoff)}</b>
        </span>
        {actions}
      </div>
      <StatusTriple e={e} />
      <div className="ev-grid">
        <section className="ev-col" aria-label="Numerical forecast">
          <h3>
            Numerical forecast <small>stored numbers only</small>
          </h3>
          <table className="ev-table">
            <thead>
              <tr>
                <th>Target</th>
                <th>Median</th>
                <th>80% range</th>
              </tr>
            </thead>
            <tbody>
              {e.numerical.points.map((p) => (
                <tr key={p.target}>
                  <td>{shortDate(p.target)}</td>
                  <td className="v-num">{fmt(p.median)}</td>
                  <td className="v-num">
                    {fmt(p.lower)}–{fmt(p.upper)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="ev-dl">
            <dt>Coordination</dt>
            <dd>
              {e.numerical.coordination.method || "Not recorded"}
              {e.numerical.coordination.coordinator_version && ` (v${e.numerical.coordination.coordinator_version})`}
            </dd>
            <dt>Recorded weights</dt>
            <dd>{w ? Object.entries(w).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(" · ") : "Not recorded"}</dd>
            <dt>Baseline</dt>
            <dd title={e.numerical.baseline?.name}>{e.numerical.baseline ? `No change, ${e.numerical.baseline.sample_count} samples for its range` : "Not recorded"}</dd>
            <dt>Quality flags</dt>
            <dd>{e.numerical.quality_flags.length ? e.numerical.quality_flags.join("; ") : "None"}</dd>
          </dl>
          <h3 className="ev-gap">Versions</h3>
          <dl className="ev-dl">
            <dt>Model</dt>
            <dd>
              {e.versions.model_family_label || "Family not recorded"} · <code>{e.versions.model_version}</code>
            </dd>
            <dt>Data</dt>
            <dd>
              <code title={e.versions.dataset_version}>{e.versions.dataset_version.slice(0, 16)}</code>
            </dd>
            <dt>Configuration</dt>
            <dd>
              <code>{e.versions.configuration_id || "—"}</code>
            </dd>
            <dt>Contract</dt>
            <dd>
              {e.versions.contract_version ? `v${e.versions.contract_version}` : "—"} · coordinator {e.versions.coordinator_version ? `v${e.versions.coordinator_version}` : "not recorded"}
            </dd>
            <dt>Training cutoff</dt>
            <dd>{when(f.training_cutoff)}</dd>
            <dt>Prompt</dt>
            <dd>
              <Note note={e.versions.prompt_version} compact />
            </dd>
            <dt>Memory</dt>
            <dd>
              <Note note={e.versions.memory_version} compact />
            </dd>
            <dt>Ensemble</dt>
            <dd>
              <Note note={e.versions.ensemble_version} compact />
            </dd>
          </dl>
        </section>
        <section className="ev-col" aria-label="Source evidence">
          <h3>
            Sources and as-of times <small>what the forecast could read</small>
          </h3>
          <h4>Market data</h4>
          <SourceList e={e} />
          <h4>News, macro and research sources</h4>
          <Note note={e.sources.research} />
          {e.news_evidence && <section aria-label="Saved news evidence">
            <Note note={e.news_evidence} />
            {e.news_evidence.packet && <p>As-of {when(e.news_evidence.packet.origin)} · {e.news_evidence.packet.policy}</p>}
            <ul>{e.news_evidence.articles?.map(a => <li key={a.id}><a href={a.url} target="_blank" rel="noreferrer">{a.headline}</a><p className="ev-dim small">Published {when(a.published_at)} · available {when(a.effective_available_at)} · {a.content_scope}</p></li>)}</ul>
            {e.news_evidence.features && <details><summary>Saved numerical news features</summary><table className="ev-table"><tbody>{e.news_evidence.features.names.map((name, i) => <tr key={name}><td>{name}</td><td>{e.news_evidence!.features!.values[i]}</td></tr>)}</tbody></table></details>}
          </section>}
          <h3 className="ev-gap">Agents for this forecast</h3>
          {Object.entries(
            e.agents.reduce<Record<string, typeof e.agents>>((g, a) => ({ ...g, [a.state]: [...(g[a.state] || []), a] }), {}),
          ).map(([state, list]) => (
            <div key={state} className="ev-agent-group">
              <State state={state}>{AGENT_TEXT[state] || state}</State>
              <ul className="ev-agents">
                {list.map((a) => (
                  <li key={a.id} title={a.detail}>
                    <i className={`v-dot ${a.state === "active" ? "ok" : a.state === "pending" ? "idle" : "off"}`} />
                    {a.name}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
        <section className="ev-col" aria-label="Reasoning">
          <h3>
            Reasoning <small>cited summaries only, no private chain-of-thought</small>
          </h3>
          <div className={`ev-banner ${r.state === "recorded" ? "ok" : ""}`}>
            <strong>{r.state === "recorded" ? "Reasoning recorded" : "Reasoning not recorded"}</strong>
            <span>{r.reason}</span>
          </div>
          {r.summary && <p className="ev-summary">{r.summary}</p>}
          <div className="ev-two">
            <ReasoningList title="Supported findings" items={r.findings} empty={reasonEmpty} />
            <ReasoningList title="Counterarguments" items={r.arguments.counterarguments} empty={reasonEmpty} />
            <ReasoningList title="Bull arguments" items={r.arguments.bull} empty={reasonEmpty} />
            <ReasoningList title="Bear arguments" items={r.arguments.bear} empty={reasonEmpty} />
            <ReasoningList title="Moderator findings" items={r.moderator.findings} empty={reasonEmpty} />
            <ReasoningList title="Rejected claims" items={r.moderator.rejected_claims} empty={reasonEmpty} />
            <ReasoningList title="Unresolved conflicts" items={r.moderator.unresolved_conflicts} empty={reasonEmpty} />
          </div>
          <p className="ev-dim small">Agent agreement: {r.agreement == null ? "not recorded" : describe(r.agreement)}. Agreement is not prediction confidence.</p>
          <h3 className="ev-gap">Cost and latency</h3>
          <dl className="ev-dl">
            <dt>Inference cost</dt>
            <dd>
              <Note note={e.cost_latency.inference_cost} compact />
            </dd>
            <dt>Forecast latency</dt>
            <dd>
              <Note note={e.cost_latency.forecast_latency} compact />
            </dd>
            <dt>Producing job</dt>
            <dd>{job.state === "recorded" ? <span title={job.scope}>{fmt(job.seconds, 1)} s for the whole run</span> : <Note note={job} />}</dd>
          </dl>
        </section>
      </div>
    </>
  );
}

// Compact evidence and provenance for the Inspect drawer.
export function InspectEvidence({ id }: { id: string }) {
  const { load, retry } = useForecastEvidence(id);
  if (load.status !== "ok") return <EvidenceFailure load={load} onRetry={retry} />;
  const e = load.data;
  const r = e.reasoning;
  return (
    <div className="ev-inspect">
      <section>
        <h4>Provenance</h4>
        <dl className="ev-dl">
          <dt>Origin</dt>
          <dd>{when(e.forecast.origin)}</dd>
          <dt>Evidence cutoff</dt>
          <dd>{when(e.forecast.evidence_cutoff)}</dd>
          <dt>Saved</dt>
          <dd>{when(e.forecast.generated_at)}</dd>
          <dt>Coordination</dt>
          <dd>
            {e.numerical.coordination.method || "Not recorded"}
            {e.numerical.coordination.weights && ` · weights ${Object.entries(e.numerical.coordination.weights).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(", ")}`}
          </dd>
        </dl>
      </section>
      <section>
        <h4>Cited inputs</h4>
        <SourceList e={e} compact />
        <p className="ev-dim small">Research sources: {STATE_TEXT[e.sources.research.state]}.</p>
      </section>
      <section>
        <h4>Reasoning summary</h4>
        {r.summary ? <p>{r.summary}</p> : <p className="ev-empty">{r.state === "recorded" ? "No summary recorded" : "Reasoning not recorded"}. {r.reason}</p>}
      </section>
      <StatusTriple e={e} />
    </div>
  );
}
