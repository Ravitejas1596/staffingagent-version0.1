import type { ActionQueue as ActionQueueData, AgentId } from './types';
import { AGENT_COLORS, AGENT_VIEW_MAP, AGENT_ICONS } from './types';
import type { ViewId } from '../../types';

interface ActionQueueProps {
  data: ActionQueueData | null;
  isLoading: boolean;
  onNavigate: (view: ViewId) => void;
}

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  if (value > 0) return `$${Math.round(value)}`;
  return '';
}

function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return null;
  const s = severity.toLowerCase();
  let cls = 'cc-aq-severity';
  if (s === 'critical' || s === 'high') cls += ' critical';
  else if (s === 'medium' || s === 'elevated') cls += ' elevated';
  else cls += ' low';
  return <span className={cls}>{severity}</span>;
}

export default function ActionQueue({ data, isLoading, onNavigate }: ActionQueueProps) {
  if (isLoading) {
    return (
      <div className="cc-action-queue cc-action-queue--loading">
        <div className="cc-aq-header">
          <div className="cc-skeleton" style={{ width: 200, height: 18 }} />
          <div className="cc-skeleton" style={{ width: 60, height: 24, borderRadius: 12 }} />
        </div>
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="cc-aq-item">
            <div className="cc-skeleton" style={{ width: 36, height: 36, borderRadius: 10, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div className="cc-skeleton" style={{ width: '60%', height: 14, marginBottom: 6 }} />
              <div className="cc-skeleton" style={{ width: '80%', height: 12 }} />
            </div>
            <div className="cc-skeleton" style={{ width: 100, height: 32, borderRadius: 8 }} />
          </div>
        ))}
      </div>
    );
  }

  if (!data || data.totalItems === 0) return null;

  const { planApprovals, resultReviews, totalItems } = data;

  return (
    <div className="cc-action-queue">
      <div className="cc-aq-header">
        <div className="cc-aq-title">
          <span className="cc-aq-icon">⚡</span>
          Action Required
        </div>
        <span className="cc-aq-badge">{totalItems} {totalItems === 1 ? 'item' : 'items'}</span>
      </div>

      {planApprovals.length > 0 && (
        <div className="cc-aq-section">
          <div className="cc-aq-section-label">Plans Awaiting Approval</div>
          {planApprovals.map((item) => {
            const agentId = item.agentId as AgentId;
            const viewId = AGENT_VIEW_MAP[agentId];
            const icon = AGENT_ICONS[agentId] ?? '🤖';
            const color = AGENT_COLORS[agentId] ?? '#06b6d4';

            return (
              <div key={item.runId} className="cc-aq-item">
                <div className="cc-aq-item-icon" style={{ background: `${color}20`, color }}>
                  {icon}
                </div>
                <div className="cc-aq-item-content">
                  <div className="cc-aq-item-title">{item.agentDisplayName}</div>
                  <div className="cc-aq-item-meta">
                    <span>{item.actionCount} {item.actionCount === 1 ? 'action' : 'actions'} proposed</span>
                    {item.totalFinancialImpact > 0 && <span>{formatCurrency(item.totalFinancialImpact)} impact</span>}
                    <span>{timeAgo(item.createdAt)}</span>
                  </div>
                </div>
                <div className="cc-aq-item-actions">
                  <SeverityBadge severity={item.maxSeverity} />
                  {viewId && (
                    <button className="cc-aq-review-btn" onClick={() => onNavigate(viewId)}>
                      Review Plan
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {resultReviews.length > 0 && (
        <div className="cc-aq-section">
          <div className="cc-aq-section-label">Results Awaiting Review</div>
          {resultReviews.map((item) => {
            const agentId = item.agentId as AgentId;
            const viewId = AGENT_VIEW_MAP[agentId];
            const icon = AGENT_ICONS[agentId] ?? '🤖';
            const color = AGENT_COLORS[agentId] ?? '#06b6d4';

            return (
              <div key={agentId} className="cc-aq-item">
                <div className="cc-aq-item-icon" style={{ background: `${color}20`, color }}>
                  {icon}
                </div>
                <div className="cc-aq-item-content">
                  <div className="cc-aq-item-title">{item.agentDisplayName}</div>
                  <div className="cc-aq-item-meta">
                    <span>{item.pendingCount} {item.pendingCount === 1 ? 'result' : 'results'} pending</span>
                    {item.totalFinancialImpact > 0 && <span>{formatCurrency(item.totalFinancialImpact)} impact</span>}
                    <span>Oldest: {timeAgo(item.oldestItemAt)}</span>
                  </div>
                </div>
                <div className="cc-aq-item-actions">
                  <SeverityBadge severity={item.maxSeverity} />
                  {viewId && (
                    <button className="cc-aq-review-btn" onClick={() => onNavigate(viewId)}>
                      Review Results
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
