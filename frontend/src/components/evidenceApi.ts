import { useCallback, useEffect, useState } from "react";
import type { ForecastEvidence } from "../forecastTypes";

const SCHEMA = "forecast-evidence/1";

export type EvidenceLoad =
  | { status: "loading" }
  | { status: "ok"; data: ForecastEvidence }
  // The forecast id is not in the store.
  | { status: "missing"; message: string }
  // The server answered but has no evidence route (older backend still running).
  | { status: "no-endpoint"; message: string }
  // The service could not be reached or failed unexpectedly.
  | { status: "unavailable"; message: string };

// One request per forecast id. Failures are kept too, so switching tabs never calls a
// failing endpoint again; only an explicit Retry clears the entry.
const cache = new Map<string, Promise<EvidenceLoad>>();

async function load(id: string): Promise<EvidenceLoad> {
  let r: Response;
  try {
    r = await fetch(`/api/forecasting/forecasts/${encodeURIComponent(id)}/evidence`);
  } catch (e) {
    return { status: "unavailable", message: `Could not reach the Foresight service (${(e as Error).message}).` };
  }
  let body: { detail?: string; schema_version?: string } | null = null;
  try {
    body = await r.json();
  } catch {
    body = null;
  }
  if (r.status === 404)
    return body?.detail === "Not Found"
      ? { status: "no-endpoint", message: "This server has no evidence endpoint. Restart the backend after updating Foresight." }
      : { status: "missing", message: body?.detail || "Saved forecast not found." };
  if (!r.ok || !body) return { status: "unavailable", message: `Evidence service failed (${r.status}${body?.detail ? `: ${body.detail}` : ""}).` };
  if (body.schema_version !== SCHEMA)
    return { status: "unavailable", message: `Unexpected evidence format ${body.schema_version ?? "(none)"}; expected ${SCHEMA}.` };
  return { status: "ok", data: body as ForecastEvidence };
}

export function useForecastEvidence(id: string | undefined) {
  const [result, setResult] = useState<{ id: string; load: EvidenceLoad } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let stop = false;
    if (!id) return;
    if (!cache.has(id)) cache.set(id, load(id));
    cache.get(id)!.then((l) => !stop && setResult({ id, load: l }));
    return () => {
      stop = true;
    };
  }, [id, attempt]);
  const retry = useCallback(() => {
    if (id) cache.delete(id);
    setResult(null);
    setAttempt((a) => a + 1);
  }, [id]);
  const current: EvidenceLoad = !id ? { status: "loading" } : result?.id === id ? result.load : { status: "loading" };
  return { load: current, retry };
}

