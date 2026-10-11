export function Toolbar({
  symbol,
  onSymbolChange,
  dateCoverage,
}: {
  symbol: string;
  dateCoverage?: string;
  onSymbolChange: (symbol: string) => void;
}) {
  return (
    <div className="dataset-toolbar">
      <select
        aria-label="Symbol"
        value={symbol}
        onChange={(e) => onSymbolChange(e.target.value)}
      >
        <option value="BTCUSDT">₿ BTC/USDT</option>
        <option value="ETHUSDT">Ξ ETH/USDT</option>
      </select>
      <span
        className="dataset-meta"
        title={dateCoverage || "Configured import period"}
      >
        Binance Spot · 1h · UTC
      </span>
    </div>
  );
}
