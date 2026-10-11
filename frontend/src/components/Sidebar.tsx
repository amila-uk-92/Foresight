import {
  Database,
  LineChart,
  Target,
  History,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
export function Sidebar({
  activeTab,
  onTabClick,
  collapsed = false,
  onToggleCollapsed,
}: {
  activeTab: string;
  onTabClick?: (tab: string) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const items = [
    ["dataset", "Dataset", Database],
    ["forecast_lab", "Forecast Lab", LineChart],
    ["evaluation", "Evaluation", Target],
    ["history", "Forecast History", History],
    ["settings", "Settings", Settings],
  ] as const;
  return (
    <nav
      className={`sidebar ${collapsed ? "collapsed" : ""}`}
      aria-label="Main navigation"
    >
      <div className="sidebar-brand">
        <span aria-hidden="true">F</span>
        <strong>Foresight</strong>
      </div>
      {items.map(([id, label, Icon]) => (
        <button
          key={id}
          className={activeTab === id ? "active" : ""}
          aria-label={collapsed ? label : undefined}
          title={collapsed ? label : undefined}
          onClick={() => onTabClick?.(id)}
        >
          <Icon size={20} />
          <span>{label}</span>
        </button>
      ))}
      <div className="sidebar-spacer" />
      <button
        className="sidebar-toggle"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        onClick={onToggleCollapsed}
      >
        {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
      </button>
    </nav>
  );
}
