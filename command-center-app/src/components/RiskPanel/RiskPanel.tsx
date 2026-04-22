import { useState } from 'react';
import type { RiskCategory } from '../../types';

interface RiskPanelProps {
  riskCategories: RiskCategory[];
  onNavigateToTimeOps: (filter: string) => void;
  onNavigateToRiskOps: (category: string) => void;
}

export default function RiskPanel({ riskCategories, onNavigateToTimeOps, onNavigateToRiskOps }: RiskPanelProps) {
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const totalAlerts = riskCategories.reduce((sum, c) => sum + c.count, 0);
  const timesheetCat = riskCategories.find((c) => c.id === 'timesheet');
  const riskOpsCats = riskCategories.filter((c) => c.id !== 'timesheet');

  const toggleExpand = (id: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="metric-card compliance" style={{ minHeight: 'auto' }}>
      <div className="card-header">
        <span className="card-title">Risk Alerts</span>
      </div>

      <div className="tile" onClick={() => onNavigateToRiskOps('all')} style={{ marginBottom: 8 }}>
        <span className="tile-header">All Risk Alerts</span>
        <span className="tile-value">{totalAlerts}</span>
      </div>

      <div style={{ borderTop: '1.5px dashed #e2e8f0', margin: '8px 2px' }} />

      {/* TimeOps Section */}
      <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' as const, padding: '4px 10px', borderRadius: 6, display: 'inline-block', margin: '6px 2px 4px', background: '#dbeafe', color: '#1d4ed8', border: '1px solid #93c5fd' }}>
        TimeOps Dashboard
      </div>

      {timesheetCat && timesheetCat.subCategories && timesheetCat.subCategories.map((sub) => (
        <div
          key={sub.errorType}
          className="tile"
          onClick={() => onNavigateToTimeOps(sub.errorType)}
          style={{ borderColor: '#93c5fd', marginBottom: 4 }}
        >
          <span className="tile-header">{sub.label}</span>
          <span className="tile-value">{sub.count}</span>
        </div>
      ))}

      <div style={{ borderTop: '1.5px dashed #e2e8f0', margin: '8px 2px' }} />

      {/* RiskOps Section */}
      <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' as const, padding: '4px 10px', borderRadius: 6, display: 'inline-block', margin: '6px 2px 4px', background: '#ffedd5', color: '#c2410c', border: '1px solid #fdba74' }}>
        RiskOps Dashboard
      </div>

      <div className="tile-grid">
        {riskOpsCats.map((cat) => (
          <div key={cat.id}>
            <div
              className="tile"
              onClick={() => {
                if (cat.subCategories && cat.subCategories.length > 0) toggleExpand(cat.id);
                else onNavigateToRiskOps(cat.id);
              }}
              style={{ borderRadius: cat.subCategories && expandedCats.has(cat.id) ? '14px 14px 0 0' : undefined }}
            >
              <div>
                <span className="tile-header">{cat.label}</span>
                <span className={`severity-badge ${cat.severity}`} style={{ marginLeft: 8 }}>{cat.severity}</span>
              </div>
              <span className="tile-value">{cat.count}</span>
            </div>
            {cat.subCategories && expandedCats.has(cat.id) && (
              <div style={{ background: '#fafafa', border: '1.5px solid #c0c8d2', borderTop: '1px solid #e2e8f0', borderRadius: '0 0 14px 14px', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {cat.subCategories.map((sub) => (
                  <div
                    key={sub.errorType}
                    onClick={() => onNavigateToRiskOps(cat.id + ':' + sub.errorType)}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fff', border: '1px solid #e6eef7', borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontWeight: 700, transition: 'all .15s' }}
                  >
                    <span style={{ color: '#475569' }}>{sub.label}</span>
                    <span style={{ color: '#6d28d9', fontWeight: 800 }}>{sub.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
