export function Header({
  isRealData,
  activeTab = "dataset",
  qualityStatus,
}: {
  isRealData: boolean;
  activeTab?: string;
  qualityStatus?: string;
}) {
  const title: Record<string, string> = {
    dataset: "Dataset Explorer",
    forecast_lab: "Forecast Lab",
    evaluation: "Evaluation",
    history: "Forecast History",
    settings: "Settings",
  };
  return (
    <header className="app-header">
      <div>
        <span className="brand">✦ FORESIGHT</span>
        <span className="header-divider">/</span>
        <span>{title[activeTab] || "Foresight"}</span>
        {activeTab === "dataset" && (
          <span
            className={`badge ${qualityStatus === "verified" ? "verified" : "warning"}`}
          >
            {!qualityStatus
              ? "Loading dataset…"
              : isRealData
                ? qualityStatus === "verified"
                  ? "Verified dataset"
                  : "Dataset has warnings"
                : "Awaiting import"}
          </span>
        )}
      </div>
      <span className="subtitle">Local research · Binance Spot · UTC</span>
    </header>
  );
}
