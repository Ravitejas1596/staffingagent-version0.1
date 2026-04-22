import { useEffect, useState } from 'react';
import { AlertTriangle, Bot, CheckCircle2, Clock, TrendingUp } from 'lucide-react';
import { useUI } from '../../context/UIContext';
import {
  ApiError,
  getAgentAlertMetrics,
  type AgentAlertMetrics,
} from '../../api/client';

interface AgentKpiCardProps {
  onOpenQueue?: () => void;
  windowDays?: number;
}

/**
 * Top-of-dashboard KPI card for the Time Anomaly agent.
 *
 * Three primary numbers + two "right now" backlog chips:
 *   - Alerts triggered (window) — how much the agent caught
 *   - Auto-resolved rate — the ROI headline: "x% resolved without a human"
 *   - HITL required (window) — how many actually needed a human
 *   - Currently open / Currently in HITL — real-time backlog
 *
 * The card is deliberately read-only: clicking it (when ``onOpenQueue`` is
 * provided) jumps the user into the AlertQueue so they can drill in.
 */
export default function AgentKpiCard({
  onOpenQueue,
  windowDays = 7,
}: AgentKpiCardProps) {
  const { newUI } = useUI();
  const [metrics, setMetrics] = useState<AgentAlertMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await getAgentAlertMetrics({
          window_days: windowDays,
          agent_type: 'time_anomaly',
        });
        if (!cancelled) setMetrics(m);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [windowDays]);

  const dark = newUI;
  const surface = dark ? 'rgba(15,23,42,0.7)' : '#ffffff';
  const border = dark ? 'rgba(148,163,184,0.25)' : '#e2e8f0';
  const muted = dark ? '#94a3b8' : '#64748b';
  const heading = dark ? '#e2e8f0' : '#0f172a';
  const accent = dark ? '#2dd4bf' : '#2563eb';

  const clickable = typeof onOpenQueue === 'function';

  return (
    <div
      onClick={clickable ? onOpenQueue : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpenQueue?.();
              }
            }
          : undefined
      }
      style={{
        background: surface,
        border: `1px solid ${border}`,
        borderRadius: 16,
        padding: '20px 24px',
        marginBottom: 16,
        cursor: clickable ? 'pointer' : 'default',
        transition: 'border-color 0.15s ease, transform 0.15s ease',
        boxShadow: dark ? 'none' : '0 1px 2px rgba(15,23,42,0.04)',
      }}
      onMouseEnter={(e) => {
        if (clickable) e.currentTarget.style.borderColor = accent;
      }}
      onMouseLeave={(e) => {
        if (clickable) e.currentTarget.style.borderColor = border;
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Bot size={18} color={accent} />
          <div style={{ fontWeight: 700, color: heading, fontSize: 15 }}>
            Time Anomaly agent — last {windowDays} days
          </div>
        </div>
        {clickable && (
          <div style={{ fontSize: 12, color: muted }}>Open alert queue →</div>
        )}
      </div>

      {loading && (
        <div style={{ color: muted, fontSize: 13 }}>Loading agent metrics…</div>
      )}

      {error && !loading && (
        <div style={{ color: '#dc2626', fontSize: 13 }}>
          Couldn&apos;t load agent metrics: {error}
        </div>
      )}

      {!loading && !error && metrics && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 16,
            }}
          >
            <Stat
              icon={<TrendingUp size={18} color={accent} />}
              label="Alerts triggered"
              value={metrics.alerts_triggered}
              muted={muted}
              heading={heading}
            />
            <Stat
              icon={<CheckCircle2 size={18} color="#16a34a" />}
              label="Auto-resolved rate"
              value={`${metrics.auto_resolved_rate_pct.toFixed(1)}%`}
              sub={`${metrics.auto_resolved} resolved by employee`}
              muted={muted}
              heading={heading}
            />
            <Stat
              icon={<AlertTriangle size={18} color="#f59e0b" />}
              label="HITL required"
              value={metrics.hitl_required}
              sub={
                metrics.alerts_triggered > 0
                  ? `${(
                      (metrics.hitl_required / metrics.alerts_triggered) *
                      100
                    ).toFixed(1)}% of all alerts`
                  : undefined
              }
              muted={muted}
              heading={heading}
            />
          </div>

          <div
            style={{
              display: 'flex',
              gap: 12,
              marginTop: 16,
              paddingTop: 12,
              borderTop: `1px dashed ${border}`,
              flexWrap: 'wrap',
            }}
          >
            <Pill
              icon={<Clock size={14} />}
              color={muted}
              label={`${metrics.currently_open} currently open`}
            />
            <Pill
              icon={<AlertTriangle size={14} />}
              color="#f59e0b"
              label={`${metrics.currently_hitl} waiting on HITL`}
            />
          </div>
        </>
      )}
    </div>
  );
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  muted: string;
  heading: string;
}

function Stat({ icon, label, value, sub, muted, heading }: StatProps) {
  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          color: muted,
          fontSize: 12,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: 0.4,
          marginBottom: 6,
        }}
      >
        {icon}
        <span>{label}</span>
      </div>
      <div style={{ color: heading, fontSize: 28, fontWeight: 700 }}>
        {value}
      </div>
      {sub && (
        <div style={{ color: muted, fontSize: 12, marginTop: 4 }}>{sub}</div>
      )}
    </div>
  );
}

interface PillProps {
  icon: React.ReactNode;
  color: string;
  label: string;
}

function Pill({ icon, color, label }: PillProps) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        color,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {icon}
      <span>{label}</span>
    </div>
  );
}
