import type { SummaryMetrics } from './types';

interface SummaryRowProps {
  data: SummaryMetrics | null;
  isLoading: boolean;
}

function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

function formatCurrency(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  return `$${n.toLocaleString('en-US')}`;
}

export default function SummaryRow({ data, isLoading }: SummaryRowProps) {
  if (isLoading || !data) {
    return (
      <section className="cc-summary-row">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="cc-summary-card">
            <div className="cc-skeleton" style={{ width: '60%', height: 12, marginBottom: 12 }} />
            <div className="cc-skeleton" style={{ width: '80%', height: 28, marginBottom: 8 }} />
            <div className="cc-skeleton" style={{ width: '50%', height: 13 }} />
          </div>
        ))}
      </section>
    );
  }

  const queueColorClass = data.queueStatus === 'critical' ? 'cc-trend-down'
    : data.queueStatus === 'elevated' ? 'amber' : 'cc-trend-neutral';

  return (
    <section className="cc-summary-row">
      <div className="cc-summary-card">
        <div className="cc-summary-label">Active Agents</div>
        <div className="cc-summary-value cyan">
          <span>{data.activeAgents}</span>
          <span className="cc-summary-unit">/ {data.totalAgents}</span>
        </div>
        <div className={`cc-summary-trend ${data.activeAgents === data.totalAgents ? 'cc-trend-up' : 'cc-trend-neutral'}`}>
          <span>{data.activeAgents === data.totalAgents ? '✓' : '—'}</span>
          {data.activeAgents === data.totalAgents ? '100% uptime' : `${data.totalAgents - data.activeAgents} offline`}
        </div>
      </div>

      <div className="cc-summary-card">
        <div className="cc-summary-label">Transactions Today</div>
        <div className="cc-summary-value green">
          <span>{formatNumber(data.transactionsToday)}</span>
        </div>
        <div className={`cc-summary-trend ${data.transactionsTrend >= 0 ? 'cc-trend-up' : 'cc-trend-down'}`}>
          <span>{data.transactionsTrend >= 0 ? '↑' : '↓'}</span>
          {data.transactionsTrend >= 0 ? '+' : ''}{data.transactionsTrend.toFixed(1)}% vs avg
        </div>
      </div>

      <div className="cc-summary-card">
        <div className="cc-summary-label">MTD Cost Savings</div>
        <div className="cc-summary-value green">
          <span>{formatCurrency(data.mtdCostSavings)}</span>
        </div>
        <div className="cc-summary-trend cc-trend-up">
          <span>↑</span> On track for {formatCurrency(data.projectedMonthlySavings)}
        </div>
      </div>

      <div className="cc-summary-card">
        <div className="cc-summary-label">Queue Depth</div>
        <div className="cc-summary-value amber">
          <span>{data.queueDepth}</span>
          <span className="cc-summary-unit">pending</span>
        </div>
        <div className={`cc-summary-trend ${queueColorClass}`}>
          <span>→</span> {data.queueStatus === 'normal' ? 'Normal range' : data.queueStatus === 'elevated' ? 'Elevated' : 'Critical'}
        </div>
      </div>

      <div className="cc-summary-card">
        <div className="cc-summary-label">Error Rate</div>
        <div className="cc-summary-value cyan">
          <span>{data.errorRate.toFixed(1)}</span>%
        </div>
        <div className={`cc-summary-trend ${data.errorRateTrend <= 0 ? 'cc-trend-up' : 'cc-trend-down'}`}>
          <span>{data.errorRateTrend <= 0 ? '↓' : '↑'}</span>
          {data.errorRateTrend <= 0 ? '' : '+'}{data.errorRateTrend.toFixed(1)}% this week
        </div>
      </div>
    </section>
  );
}
