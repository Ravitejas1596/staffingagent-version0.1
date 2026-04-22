import type { AgentMetrics, AgentId } from './types';
import { AGENT_COLORS, AGENT_ICONS, AGENT_VIEW_MAP } from './types';
import type { ViewId } from '../../types';

export type AgentCardState = 'idle' | 'running' | 'success' | 'error';

interface AgentFleetPanelProps {
  agents: AgentMetrics[];
  isLoading: boolean;
  agentStates: Record<string, AgentCardState>;
  onRunAgent: (agentId: AgentId) => void;
  onNavigate: (view: ViewId) => void;
}

function formatTime(ms: number): string {
  const s = ms / 1000;
  return s < 1 ? `${ms}ms` : `${s.toFixed(1)}s`;
}

const LAUNCHABLE: Set<string> = new Set(['active', 'idle', 'processing']);

export default function AgentFleetPanel({
  agents,
  isLoading,
  agentStates,
  onRunAgent,
  onNavigate,
}: AgentFleetPanelProps) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">🤖</div>
          Agent Fleet Status
        </div>
        <div className="cc-card-badge">Live</div>
      </div>

      {isLoading ? (
        <div className="cc-agent-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="cc-agent-item">
              <div className="cc-skeleton" style={{ width: '70%', height: 13, marginBottom: 16 }} />
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div className="cc-skeleton" style={{ width: 40, height: 16 }} />
                <div className="cc-skeleton" style={{ width: 40, height: 16 }} />
                <div className="cc-skeleton" style={{ width: 40, height: 16 }} />
              </div>
            </div>
          ))}
        </div>
      ) : agents.length === 0 ? (
        <div className="cc-no-data">
          <div className="cc-no-data-icon">🤖</div>
          <div className="cc-no-data-text">No agent data available</div>
          <div className="cc-no-data-sub">Agent metrics will appear once agents begin processing</div>
        </div>
      ) : (
        <div className="cc-agent-grid">
          {agents.map((agent) => {
            const cardState = agentStates[agent.agentId] ?? 'idle';
            const isRunning = cardState === 'running';
            const canLaunch = LAUNCHABLE.has(agent.status) && !isRunning;
            const viewId = AGENT_VIEW_MAP[agent.agentId];
            const icon = AGENT_ICONS[agent.agentId] ?? '🤖';
            const color = AGENT_COLORS[agent.agentId] ?? '#06b6d4';

            return (
              <div
                key={agent.agentId}
                className={`cc-agent-item cc-agent-clickable${isRunning ? ' cc-agent-running' : ''}${cardState === 'success' ? ' cc-agent-success' : ''}${cardState === 'error' ? ' cc-agent-error-flash' : ''}`}
              >
                <div className="cc-agent-header">
                  <span
                    className="cc-agent-name cc-agent-name-link"
                    onClick={() => viewId && onNavigate(viewId)}
                    title="View agent details"
                  >
                    <span className="cc-agent-icon-sm" style={{ color }}>{icon}</span>
                    {agent.displayName}
                  </span>
                  <div className={`cc-agent-status ${agent.status}`} />
                </div>
                <div className="cc-agent-stats">
                  <div className="cc-agent-stat">
                    <div className="cc-agent-stat-value">{agent.transactionsToday.toLocaleString()}</div>
                    <div className="cc-agent-stat-label">Today</div>
                  </div>
                  <div className="cc-agent-stat">
                    <div className="cc-agent-stat-value">{agent.accuracyRate.toFixed(1)}%</div>
                    <div className="cc-agent-stat-label">Accuracy</div>
                  </div>
                  <div className="cc-agent-stat">
                    <div className="cc-agent-stat-value">{formatTime(agent.avgProcessingTimeMs)}</div>
                    <div className="cc-agent-stat-label">Avg Time</div>
                  </div>
                </div>
                <div className="cc-agent-actions">
                  {isRunning ? (
                    <span className="cc-agent-run-indicator">
                      <span className="cc-agent-spinner" />
                      Planning...
                    </span>
                  ) : (
                    <button
                      className="cc-agent-run-btn"
                      disabled={!canLaunch}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRunAgent(agent.agentId);
                      }}
                    >
                      ▶ Run Agent
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
