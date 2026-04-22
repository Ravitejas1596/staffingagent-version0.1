import type { ROIMetrics } from './types';

interface ROIPanelProps {
  data: ROIMetrics | null;
  isLoading: boolean;
}

function formatCurrency(n: number): string {
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  return `$${n.toLocaleString('en-US')}`;
}

export default function ROIPanel({ data, isLoading }: ROIPanelProps) {
  const hasData = data && (data.mtdCostSavings > 0 || data.laborHoursSaved > 0);

  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">💰</div>
          Financial Impact (MTD)
        </div>
      </div>

      {isLoading ? (
        <div className="cc-roi-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="cc-roi-item savings">
              <div className="cc-skeleton" style={{ width: '60%', height: 32, margin: '0 auto 8px' }} />
              <div className="cc-skeleton" style={{ width: '80%', height: 12, margin: '0 auto 8px' }} />
              <div className="cc-skeleton" style={{ width: '50%', height: 12, margin: '0 auto' }} />
            </div>
          ))}
        </div>
      ) : !hasData ? (
        <div className="cc-no-data">
          <div className="cc-no-data-icon">📊</div>
          <div className="cc-no-data-text">ROI data pending baseline</div>
          <div className="cc-no-data-sub">Metrics will populate after initial 30-day baseline capture</div>
        </div>
      ) : (
        <div className="cc-roi-grid">
          <div className="cc-roi-item savings">
            <div className="cc-roi-value">{formatCurrency(data.mtdCostSavings)}</div>
            <div className="cc-roi-label">Cost Savings</div>
            <div className="cc-roi-trend cc-trend-up">
              ↑ {data.mtdCostSavingsTrend > 0 ? `${data.mtdCostSavingsTrend}%` : '—'} vs last month
            </div>
          </div>
          <div className="cc-roi-item hours">
            <div className="cc-roi-value">{data.laborHoursSaved.toLocaleString()}</div>
            <div className="cc-roi-label">Labor Hours Saved</div>
            <div className="cc-roi-trend cc-trend-up">
              ↑ {data.laborHoursTrend > 0 ? `${data.laborHoursTrend}%` : '—'} vs last month
            </div>
          </div>
          <div className="cc-roi-item disputes">
            <div className="cc-roi-value">{data.disputeReduction > 0 ? `-${data.disputeReduction}%` : '0%'}</div>
            <div className="cc-roi-label">Billing Disputes</div>
            <div className="cc-roi-trend cc-trend-up">
              ↓ {data.disputesPrevented} disputes prevented
            </div>
          </div>
          <div className="cc-roi-item dso">
            <div className="cc-roi-value">{data.dsoImprovement > 0 ? `-${data.dsoImprovement.toFixed(1)}` : '0'}</div>
            <div className="cc-roi-label">DSO Improvement (Days)</div>
            <div className="cc-roi-trend cc-trend-up">
              ↓ {formatCurrency(data.cashVelocityImpact)} cash velocity
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
