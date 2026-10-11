import { useState } from "react";
import { X } from "lucide-react";
import type { ImportStatus } from "../types";
interface Props {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  onStartImport: (both: boolean) => void;
  onCancelImport: () => void;
  importStatus: ImportStatus | null;
  dateCoverage?: string;
  expectedCandles?: number;
  months?: number;
  error?: string;
}
export function ImportModal({
  isOpen,
  onClose,
  symbol,
  onStartImport,
  onCancelImport,
  importStatus: job,
  dateCoverage,
  expectedCandles,
  months,
  error,
}: Props) {
  const [both, setBoth] = useState(false);
  if (!isOpen) return null;
  const running =
    !!job && !["complete", "failed", "cancelled", "idle"].includes(job.status);
  return (
    <div className="modal-backdrop">
      <section
        className="panel config-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Import historical data"
      >
        <div className="panel-heading">
          <h2>Import Binance Spot historical data</h2>
          <button aria-label="Close import" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <p>
          {symbol} · {months ?? "Configured"} monthly archives ·{" "}
          {dateCoverage ?? "Configured UTC range"} ·{" "}
          {expectedCandles?.toLocaleString() ?? "Configured"} expected hours.
        </p>
        <p>
          Published SHA-256 checksums required. Verified local archives are
          reused. Failed files can be retried. Raw ZIPs are retained; a complete
          processed bundle is published atomically.
        </p>
        <label className="toggle-row">
          <span>Import both BTC and ETH (explorer only)</span>
          <input
            type="checkbox"
            checked={both}
            onChange={(e) => setBoth(e.target.checked)}
            disabled={running}
          />
        </label>
        {job && (
          <section className="panel" role="status">
            <h3>{job.status.replaceAll("_", " ")}</h3>
            <p>{job.current_step}</p>
            <progress value={job.progress_percentage} max="100" />
            <p>
              {Math.round(job.progress_percentage)}% · {job.completed_files}/
              {job.total_files} archive files
            </p>
            {job.status === "complete" && (
              <p>
                Import complete. Check the dataset quality report for gaps or
                warnings.
              </p>
            )}
            {job.error && <p className="error">{job.error}</p>}
          </section>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="primary-actions">
          <button onClick={onClose}>Close</button>
          {running ? (
            <button onClick={onCancelImport}>Cancel Import</button>
          ) : (
            <button className="primary" onClick={() => onStartImport(both)}>
              Start Import ({both ? "BTC + ETH" : symbol})
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
