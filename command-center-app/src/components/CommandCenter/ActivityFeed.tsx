import type { ActivityItem } from './types';

interface ActivityFeedProps {
  items: ActivityItem[];
  isLoading: boolean;
}

const ICONS: Record<string, string> = {
  success: '✓',
  processing: '⟳',
  alert: '⚠',
  error: '✕',
};

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function ActivityFeed({ items, isLoading }: ActivityFeedProps) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">📋</div>
          Recent Activity
        </div>
        <div className="cc-card-badge">Live Feed</div>
      </div>

      {isLoading ? (
        <div className="cc-activity-feed">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="cc-activity-item">
              <div className="cc-skeleton" style={{ width: 36, height: 36, borderRadius: 10, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div className="cc-skeleton" style={{ width: '70%', height: 13, marginBottom: 6 }} />
                <div className="cc-skeleton" style={{ width: '90%', height: 12 }} />
              </div>
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="cc-no-data">
          <div className="cc-no-data-icon">📋</div>
          <div className="cc-no-data-text">No recent activity</div>
          <div className="cc-no-data-sub">Activity will appear as agents process transactions</div>
        </div>
      ) : (
        <div className="cc-activity-feed">
          {items.map((item) => (
            <div key={item.id} className="cc-activity-item">
              <div className={`cc-activity-icon ${item.type}`}>
                {ICONS[item.type] || '•'}
              </div>
              <div className="cc-activity-content">
                <div className="cc-activity-title">{item.title}</div>
                <div className="cc-activity-meta">
                  <span>{item.agentDisplayName}</span>
                  <span>{timeAgo(item.timestamp)}</span>
                  <span>{item.detail}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
