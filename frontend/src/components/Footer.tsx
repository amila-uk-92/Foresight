export function Footer({
  isRealData,
  totalCandles = 0,
}: {
  isRealData: boolean;
  totalCandles?: number;
}) {
  return (
    <footer className="app-footer">
      <span>FORESIGHT · Local Bitcoin research</span>
      <span>
        {isRealData
          ? `Binance Spot · ${totalCandles.toLocaleString()} imported hourly candles`
          : "No dataset imported"}
      </span>
    </footer>
  );
}
