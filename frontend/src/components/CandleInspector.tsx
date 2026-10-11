import React from 'react';
import { Info, ChevronLeft, ChevronRight, ChevronDown, ChevronUp } from 'lucide-react';
import type { Candle } from '../types';

interface CandleInspectorProps {
  candles: Candle[];
  totalRows: number;
  currentPage: number;
  pageSize: number;
  isRealData: boolean;
  onPageChange: (newPage: number) => void;
  onRowClick?: (candle: Candle) => void;
  selectedCandle?: Candle | null;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export const CandleInspector: React.FC<CandleInspectorProps> = ({
  candles,
  totalRows,
  currentPage,
  pageSize,
  isRealData,
  onPageChange,
  onRowClick,
  selectedCandle,
  collapsed = false,
  onToggleCollapsed,
}) => {
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const startIdx = (currentPage - 1) * pageSize + 1;
  const endIdx = Math.min(startIdx + candles.length - 1, totalRows);

  const formatPrice = (val: number) => {
    return val.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const formatVolume = (val: number) => {
    return Math.round(val).toLocaleString('en-US');
  };

  const formatTimestamp = (raw?: string, unixTime?: number) => {
    if (raw) {
      return raw.replace('T', ' ').substring(0, 19);
    }
    if (unixTime) {
      return new Date(unixTime * 1000).toISOString().replace('T', ' ').substring(0, 19);
    }
    return '';
  };

  const getSplitBadge = (split: string) => {
    if (split === 'training') {
      return (
        <span
          style={{
            backgroundColor: '#082f41',
            border: '1px solid #0e5372',
            color: '#4bebf6',
            fontSize: '8.5px',
            fontWeight: 600,
            padding: '1px 7px',
            borderRadius: '9px',
            display: 'inline-block',
          }}
        >
          Training
        </span>
      );
    } else if (split === 'validation') {
      return (
        <span
          style={{
            backgroundColor: '#231e15',
            border: '1px solid #54441f',
            color: '#f8c758',
            fontSize: '8.5px',
            fontWeight: 600,
            padding: '1px 7px',
            borderRadius: '9px',
            display: 'inline-block',
          }}
        >
          Validation
        </span>
      );
    } else {
      return (
        <span
          style={{
            backgroundColor: '#261642',
            border: '1px solid #552e8d',
            color: '#c084fc',
            fontSize: '8.5px',
            fontWeight: 600,
            padding: '1px 7px',
            borderRadius: '9px',
            display: 'inline-block',
          }}
        >
          Test
        </span>
      );
    }
  };

  // Display candles with comfortable pagination rows
  const displayCandles = candles;

  return (
    <div className={`candle-inspector ${collapsed ? "collapsed" : ""}`}
      style={{
        margin: 0,
        backgroundColor: '#021020',
        border: '1px solid #0f2d4e',
        borderRadius: '7px',
        overflow: 'hidden',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        flex: '0 0 auto',
        height: '100%',
        minHeight: 0,
      }}
    >
      {/* Table Header Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '4px 12px',
          borderBottom: '1px solid #0f2d4e',
          backgroundColor: '#031427',
          height: '28px',
          boxSizing: 'border-box',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {/* Table List Icon */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <div style={{ width: '2.5px', height: '2.5px', borderRadius: '50%', backgroundColor: '#00f0ff' }} />
              <div style={{ width: '8px', height: '1px', backgroundColor: '#829ab1' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <div style={{ width: '2.5px', height: '2.5px', borderRadius: '50%', backgroundColor: '#00f0ff' }} />
              <div style={{ width: '8px', height: '1px', backgroundColor: '#829ab1' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <div style={{ width: '2.5px', height: '2.5px', borderRadius: '50%', backgroundColor: '#00f0ff' }} />
              <div style={{ width: '8px', height: '1px', backgroundColor: '#829ab1' }} />
            </div>
          </div>

          <span style={{ color: '#ffffff', fontSize: '10.5px', fontWeight: 600 }}>
            Candle inspector
          </span>
          <span style={{ color: '#627d98', fontSize: '9px', fontWeight: 400 }}>
            View individual candles from the selected dataset
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: '#627d98', fontSize: '9px', display: 'flex', alignItems: 'center', gap: '3px' }}>
            {!isRealData ? 'No imported rows' : collapsed ? `${totalRows.toLocaleString()} rows` : `Showing ${startIdx}–${endIdx} of ${totalRows.toLocaleString()} rows`}
            <Info size={10} color="#627d98" />
          </span>

          {isRealData && !collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px', marginLeft: '3px' }}>
              <button
                aria-label="Previous candle page"
                disabled={currentPage <= 1}
                onClick={() => onPageChange(currentPage - 1)}
                style={{
                  background: 'none',
                  border: '1px solid #133254',
                  borderRadius: '3px',
                  color: currentPage <= 1 ? '#334e68' : '#e2e8f0',
                  padding: '1px 2px',
                  cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <ChevronLeft size={10} />
              </button>
              <button
                aria-label="Next candle page"
                disabled={currentPage >= totalPages}
                onClick={() => onPageChange(currentPage + 1)}
                style={{
                  background: 'none',
                  border: '1px solid #133254',
                  borderRadius: '3px',
                  color: currentPage >= totalPages ? '#334e68' : '#e2e8f0',
                  padding: '1px 2px',
                  cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <ChevronRight size={10} />
              </button>
            </div>
          )}
          <button
            className="inspector-collapse"
            aria-expanded={!collapsed}
            onClick={onToggleCollapsed}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {collapsed ? 'Show' : 'Hide'}
          </button>
        </div>
      </div>

      {/* Table Data View */}
      {!collapsed && <div className="inspector-table-scroll" style={{ minHeight: 0, overflowX: 'auto', overflowY: 'auto', width: '100%', flex: 1 }}>
        <table
          aria-label="Candle inspector"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '9.5px',
            textAlign: 'left',
          }}
        >
          <thead>
            <tr style={{ backgroundColor: '#051930', borderBottom: '1px solid #0f2d4e', height: '22px' }}>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500, width: '25px' }}>#</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500, width: '130px' }}>Timestamp (UTC)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500 }}>Open (USDT)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500 }}>High (USDT)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500 }}>Low (USDT)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500 }}>Close (USDT)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500 }}>Base volume</th>
              <th>Quote volume (USDT)</th>
              <th style={{ padding: '3px 12px', color: '#627d98', fontWeight: 500, textAlign: 'center', width: '75px' }}>Split</th>
            </tr>
          </thead>
          <tbody>
            {displayCandles.map((c, idx) => {
              const rowNum = startIdx + idx;
              const isSelected = selectedCandle?.time === c.time;

              return (
                <tr
                  key={c.time || idx}
                  onClick={() => onRowClick?.(c)}
                  style={{
                    borderBottom: '1px solid #092038',
                    height: '22px',
                    backgroundColor: isSelected
                      ? 'rgba(0, 229, 255, 0.08)'
                      : idx % 2 === 0
                      ? '#021020'
                      : '#031427',
                    cursor: 'pointer',
                    transition: 'background-color 0.1s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = '#07203b';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.backgroundColor = idx % 2 === 0 ? '#021020' : '#031427';
                    }
                  }}
                >
                  <td style={{ padding: '3px 12px', color: '#627d98' }}>{rowNum}</td>
                  <td style={{ padding: '3px 12px', color: '#d8e2ec', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                    {formatTimestamp(c.timestamp, c.time)}
                  </td>
                  <td style={{ padding: '3px 12px', color: '#ffffff' }}>{formatPrice(c.open)}</td>
                  <td style={{ padding: '3px 12px', color: '#ffffff' }}>{formatPrice(c.high)}</td>
                  <td style={{ padding: '3px 12px', color: '#ffffff' }}>{formatPrice(c.low)}</td>
                  <td style={{ padding: '3px 12px', color: '#ffffff' }}>{formatPrice(c.close)}</td>
                  <td style={{ padding: '3px 12px', color: '#ffffff' }}>{formatVolume(c.volume)}</td>
                  <td>{formatVolume(c.quote_volume)}</td>
                  <td style={{ padding: '3px 12px', textAlign: 'center' }}>{getSplitBadge(c.split)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>}
    </div>
  );
};
