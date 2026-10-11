import { useEffect, useState, type ReactNode } from "react";

export type DockPane = { id: string; label: ReactNode; content: ReactNode };

// The chosen tab is a per-browser convenience; storage may be unavailable.
const read = (key: string) => {
  try {
    return localStorage.getItem("foresight.dock." + key) || "";
  } catch {
    return "";
  }
};
const write = (key: string, value: string) => {
  try {
    localStorage.setItem("foresight.dock." + key, value);
  } catch {
    /* Ignore unavailable storage. */
  }
};

export function useDockTab(id: string) {
  const [tab, setTab] = useState(() => read(id));
  useEffect(() => write(id, tab), [id, tab]);
  return [tab, setTab] as const;
}

// One-screen layout: secondary panels share one area and show one at a time.
export function Dock({
  id,
  label,
  panes,
  value,
  onChange,
  className = "",
}: {
  id: string;
  label: string;
  panes: (DockPane | false | null | undefined)[];
  value?: string;
  onChange?: (id: string) => void;
  className?: string;
}) {
  const [own, setOwn] = useDockTab(id);
  const tab = value ?? own;
  const select = onChange ?? setOwn;
  const shown = panes.filter((p): p is DockPane => Boolean(p));
  const current = shown.find((p) => p.id === tab) || shown[0];
  if (!current) return null;
  return (
    <section className={`v-card v-dock ${className}`} aria-label={label}>
      <div className="v-dock-tabs" role="tablist" aria-label={label}>
        {shown.map((p) => (
          <button
            key={p.id}
            role="tab"
            id={`${id}-${p.id}-tab`}
            aria-selected={p.id === current.id}
            aria-controls={`${id}-panel`}
            className={p.id === current.id ? "on" : ""}
            onClick={() => select(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div
        className="v-dock-body"
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-${current.id}-tab`}
      >
        {current.content}
      </div>
    </section>
  );
}
