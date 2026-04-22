import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { EntityPanelData, EntityMetric } from '../../types';

interface EntityPanelProps {
  panel: EntityPanelData;
  onNavigate?: (filter: string) => void;
  onDrillThrough?: (label: string, value: string | number) => void;
}

function TileMetric({ metric, onDrillThrough }: { metric: EntityMetric; onDrillThrough?: (label: string, value: string | number) => void }) {
  return (
    <div
      className="nb-tile"
      onClick={() => onDrillThrough?.(metric.label, metric.value)}
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', background: 'var(--cc-bg-secondary)', border: '1px solid var(--cc-border)',
        borderRadius: 12, cursor: 'pointer', transition: 'all .2s ease',
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--cc-text-secondary)' }}>{metric.label}</span>
      <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--cc-cyan)', fontFamily: 'var(--cc-mono)' }}>{metric.value}</span>
    </div>
  );
}

function AlertMetric({ metric }: { metric: EntityMetric }) {
  const [expanded, setExpanded] = useState(false);
  const hasSubs = metric.subMetrics && metric.subMetrics.length > 0;

  return (
    <div className="nb-collapsible">
      <div className="alert-box" style={{ cursor: hasSubs ? 'pointer' : undefined }} onClick={() => hasSubs && setExpanded(!expanded)}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          <span className="metric-label" style={{ marginBottom: 0, color: 'var(--cc-text-secondary)' }}>{metric.label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="alert-value" style={{ color: 'var(--cc-red)', fontFamily: 'var(--cc-mono)', fontWeight: 700 }}>{metric.value}</span>
            {hasSubs && (
              <button className="nb-button" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }} style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--cc-red)', borderColor: 'rgba(239, 68, 68, 0.2)' }}>
                Details
                <ChevronDown size={12} className="nb-chev" style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
              </button>
            )}
          </div>
        </div>
      </div>
      {hasSubs && (
        <div className={`nb-panel ${expanded ? 'expanded' : ''}`}>
          <div className="nb-subgrid">
            {metric.subMetrics!.map((sub, i) => (
              <div key={i} className="nb-subtile">
                <span className="nb-label">{sub.label}</span>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span className="nb-num">{sub.value}</span>
                  {sub.percentage && <span style={{ color: '#2563eb', fontWeight: 800, fontSize: 11 }}>{sub.percentage}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CollapsibleMetric({ metric, onNavigate }: { metric: EntityMetric; onNavigate?: (f: string) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="metric-item nb-collapsible">
      <div className="nb-head">
        <div className="nb-left">
          <span className="metric-label">{metric.label}</span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            {metric.percentage && <span className="percentage">{metric.percentage}</span>}
            {metric.amount && <span className="amount">{metric.amount}</span>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="metric-value">{metric.value}</span>
          <button className="nb-button" onClick={() => setExpanded(!expanded)}>
            Details
            <ChevronDown size={12} className="nb-chev" style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
          </button>
        </div>
      </div>
      <div className={`nb-panel ${expanded ? 'expanded' : ''}`}>
        <div className="nb-subgrid">
          {metric.subMetrics!.map((sub, i) => (
            <div
              key={i}
              className="nb-subtile"
              onClick={() => {
                if (sub.clickable) onNavigate?.(sub.label.toLowerCase().replace(/\s+/g, '-'));
              }}
              style={{ cursor: sub.clickable ? 'pointer' : undefined }}
            >
              <span className="nb-label">{sub.label}</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span className="nb-num">{sub.value}</span>
                {sub.percentage && <span style={{ color: '#2563eb', fontWeight: 800, fontSize: 11 }}>{sub.percentage}</span>}
                {sub.amount && <span style={{ color: '#64748b', fontWeight: 600, fontSize: 11 }}>{sub.amount}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PlainMetric({ metric }: { metric: EntityMetric }) {
  return (
    <div className="metric-item">
      <span className="metric-label">{metric.label}</span>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, justifyContent: 'space-between' }}>
        <span className="metric-value">{metric.value}</span>
        <div>
          {metric.percentage && <span className="percentage">{metric.percentage}</span>}
          {metric.amount && <span className="amount">{metric.amount}</span>}
        </div>
      </div>
    </div>
  );
}

function MetricItem({ metric, onNavigate, onDrillThrough }: { metric: EntityMetric; onNavigate?: (f: string) => void; onDrillThrough?: (label: string, value: string | number) => void }) {
  if (metric.isTile) return <TileMetric metric={metric} onDrillThrough={onDrillThrough} />;
  if (metric.isAlert) return <AlertMetric metric={metric} />;
  if (metric.subMetrics && metric.subMetrics.length > 0) return <CollapsibleMetric metric={metric} onNavigate={onNavigate} />;
  return <PlainMetric metric={metric} />;
}

export default function EntityPanel({ panel, onNavigate, onDrillThrough }: EntityPanelProps) {
  const tileMetrics = panel.metrics.filter((m) => m.isTile);
  const otherMetrics = panel.metrics.filter((m) => !m.isTile);

  return (
    <div className={`metric-card ${panel.type}`}>
      <div className="card-header">
        <span className="card-title">{panel.title}</span>
      </div>

      {tileMetrics.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: otherMetrics.length > 0 ? 8 : 0 }}>
          {tileMetrics.map((metric, i) => (
            <MetricItem key={i} metric={metric} onNavigate={onNavigate} onDrillThrough={onDrillThrough} />
          ))}
        </div>
      )}

      {otherMetrics.map((metric, i) => (
        <MetricItem key={i} metric={metric} onNavigate={onNavigate} onDrillThrough={onDrillThrough} />
      ))}

      {panel.progressBar && (
        <div className="progress-bar">
          <div
            className={`progress-fill ${panel.progressBar.status}`}
            style={{ width: `${panel.progressBar.value}%` }}
          />
        </div>
      )}
    </div>
  );
}
