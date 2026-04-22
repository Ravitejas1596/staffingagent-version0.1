import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, RefreshCw, CheckCircle2, AlertTriangle, Undo2, X } from 'lucide-react';
import { useUI } from '../../context/UIContext';
import {
  ApiError,
  getAlert,
  listAlerts,
  resolveAlert,
  reverseAlert,
  type AgentAlertDetail,
  type AgentAlertSummary,
  type ResolveAlertBody,
} from '../../api/client';
import './alertQueue.css';

interface AlertQueueProps {
  onBack: () => void;
}

type StateFilter = 'all' | 'escalated_hitl' | 'outreach_sent' | 'detected' | 'resolved';
type SeverityFilter = 'all' | 'low' | 'medium' | 'high';

const STATE_LABELS: Record<string, string> = {
  detected: 'Detected',
  outreach_sent: 'Reminder sent',
  escalated_hitl: 'HITL — needs review',
  resolved: 'Resolved',
};

const SEVERITY_COLORS: Record<string, string> = {
  low: '#94a3b8',
  medium: '#f59e0b',
  high: '#dc2626',
};

const ALERT_TYPE_LABELS: Record<string, string> = {
  group_a1_first_miss: 'Missing timesheet (first miss)',
  group_a2_consecutive_miss: 'Missing timesheet (consecutive)',
  group_b_reg_over_limit: 'Regular hours over limit',
  group_b_ot_over_limit: 'Overtime over limit',
  group_b_total_over_limit: 'Total hours over limit',
  group_c_variance: 'Hours variance from typical',
};

export default function AlertQueue({ onBack }: AlertQueueProps) {
  const { c } = useUI();
  const [alerts, setAlerts] = useState<AgentAlertSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState<StateFilter>('escalated_hitl');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [selectedAlert, setSelectedAlert] = useState<AgentAlertDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const rows = await listAlerts({
        state: stateFilter === 'all' ? undefined : stateFilter,
        severity: severityFilter === 'all' ? undefined : severityFilter,
        agent_type: 'time_anomaly',
        limit: 200,
      });
      setAlerts(rows);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : String(err));
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [stateFilter, severityFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const counts = useMemo(() => {
    const byState: Record<string, number> = { escalated_hitl: 0, outreach_sent: 0, detected: 0, resolved: 0 };
    for (const a of alerts) byState[a.state] = (byState[a.state] ?? 0) + 1;
    return byState;
  }, [alerts]);

  const openAlert = useCallback(async (alertId: string) => {
    setDrawerLoading(true);
    try {
      const detail = await getAlert(alertId);
      setSelectedAlert(detail);
    } catch (err) {
      setToast({ kind: 'err', text: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setDrawerLoading(false);
    }
  }, []);

  const runResolve = useCallback(
    async (alert: AgentAlertDetail, body: ResolveAlertBody) => {
      setActionBusy(true);
      try {
        await resolveAlert(alert.id, body);
        setToast({ kind: 'ok', text: `Resolved as ${body.resolution}` });
        setSelectedAlert(null);
        await load();
      } catch (err) {
        setToast({ kind: 'err', text: err instanceof ApiError ? err.message : String(err) });
      } finally {
        setActionBusy(false);
      }
    },
    [load],
  );

  const runReverse = useCallback(
    async (alert: AgentAlertDetail) => {
      const reason = window.prompt('Reason for reversing the most recent action?');
      if (!reason) return;
      setActionBusy(true);
      try {
        const res = await reverseAlert(alert.id, reason);
        setToast({ kind: 'ok', text: `Reversed (${res.reversed_event_id.slice(0, 8)}…)` });
        await openAlert(alert.id);
      } catch (err) {
        setToast({ kind: 'err', text: err instanceof ApiError ? err.message : String(err) });
      } finally {
        setActionBusy(false);
      }
    },
    [openAlert],
  );

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Dashboard
      </button>

      <div className="sub-header">
        <h1>Alert Queue — Time Anomaly</h1>
        <p>Review, resolve, and reverse alerts the Time Anomaly agent has escalated for human judgment.</p>
      </div>

      <div className="aq-filter-bar">
        {(['escalated_hitl', 'outreach_sent', 'detected', 'resolved', 'all'] as StateFilter[]).map((s) => (
          <button
            key={s}
            onClick={() => setStateFilter(s)}
            className={`aq-filter-btn ${stateFilter === s ? 'active' : ''}`}
          >
            <span>{s === 'all' ? 'All states' : STATE_LABELS[s] ?? s}</span>
            {s !== 'all' && (
              <span className="aq-count-badge">
                {counts[s] ?? 0}
              </span>
            )}
          </button>
        ))}

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as SeverityFilter)}
          style={{
            marginLeft: 'auto',
            background: c.cardBg,
            color: c.text,
            border: `1.5px solid ${c.cardBorder}`,
            borderRadius: 10,
            padding: '8px 12px',
            fontSize: 13,
          }}
        >
          <option value="all">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        <button
          onClick={() => void load()}
          style={{
            background: c.cardBg,
            color: c.text,
            border: `1.5px solid ${c.cardBorder}`,
            borderRadius: 10,
            padding: '8px 14px',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {toast && (
        <div
          role="status"
          style={{
            position: 'fixed',
            bottom: 32,
            right: 32,
            background: toast.kind === 'ok' ? '#16a34a' : '#dc2626',
            color: '#fff',
            padding: '12px 20px',
            borderRadius: 10,
            boxShadow: '0 6px 20px rgba(0,0,0,0.25)',
            fontSize: 14,
            fontWeight: 600,
            zIndex: 100,
          }}
        >
          {toast.text}
        </div>
      )}

      <div className="search-section">
        {loading && (
          <div style={{ color: c.textMuted, padding: 24, textAlign: 'center' }}>Loading alerts…</div>
        )}
        {loadError && (
          <div style={{ color: '#dc2626', padding: 16, background: '#fef2f2', borderRadius: 8, marginBottom: 12 }}>
            <AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Could not load alerts: {loadError}
          </div>
        )}
        {!loading && !loadError && alerts.length === 0 && (
          <div style={{ color: c.textMuted, padding: 40, textAlign: 'center' }}>
            <CheckCircle2 size={32} style={{ opacity: 0.5, marginBottom: 8 }} />
            <div>No alerts match the current filters. The agent queue is clear.</div>
          </div>
        )}
        {!loading && alerts.length > 0 && (
          <div className="aq-table-card">
            <table className="aq-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Type</th>
                  <th>Placement</th>
                  <th>Pay period</th>
                  <th>State</th>
                  <th>Detected</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id} onClick={() => void openAlert(a.id)}>
                    <td>
                      <span className={`aq-severity-dot ${a.severity}`} />
                      <span style={{ textTransform: 'capitalize', fontWeight: 600 }}>{a.severity}</span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{ALERT_TYPE_LABELS[a.alert_type] ?? a.alert_type}</td>
                    <td style={{ fontFamily: 'var(--aq-mono)', fontSize: 13, color: 'var(--aq-accent)' }}>
                      {(a.trigger_context?.placement_bullhorn_id as string) ?? a.placement_id?.slice(0, 8) ?? '—'}
                    </td>
                    <td>
                      {a.pay_period_start}
                      {a.pay_period_end ? ` → ${a.pay_period_end}` : ''}
                    </td>
                    <td>
                      <span style={{ color: a.state === 'escalated_hitl' ? 'var(--aq-red)' : 'var(--aq-text-secondary)', fontWeight: 700 }}>
                        {STATE_LABELS[a.state] ?? a.state}
                      </span>
                    </td>
                    <td style={{ color: 'var(--aq-text-secondary)', fontSize: 12 }}>{new Date(a.detected_at).toLocaleString()}</td>
                    <td>
                      <button
                        onClick={(e) => { e.stopPropagation(); void openAlert(a.id); }}
                        className="aq-filter-btn"
                        style={{ padding: '4px 12px', fontSize: 12 }}
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedAlert && (
        <AlertDrawer
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          onResolve={(body) => runResolve(selectedAlert, body)}
          onReverse={() => runReverse(selectedAlert)}
          actionBusy={actionBusy}
          drawerLoading={drawerLoading}
        />
      )}
    </div>
  );
}

interface DrawerProps {
  alert: AgentAlertDetail;
  onClose: () => void;
  onResolve: (body: ResolveAlertBody) => Promise<void>;
  onReverse: () => Promise<void>;
  actionBusy: boolean;
  drawerLoading: boolean;
}

function AlertDrawer({ alert, onClose, onResolve, onReverse, actionBusy, drawerLoading }: DrawerProps) {
  const { c } = useUI();
  const [resolution, setResolution] = useState('employee_corrected');
  const [action, setAction] = useState<'' | 'mark_dnw' | 'set_hold' | 'release_hold'>('');
  const [notes, setNotes] = useState('');
  const [dryRun, setDryRun] = useState(false);

  const hasReversible = alert.events.some((e) => e.reversal_available);

  const handleResolve = async () => {
    const body: ResolveAlertBody = { resolution, notes: notes || undefined };
    if (action) body.action = action;
    if (dryRun) body.dry_run = true;
    await onResolve(body);
  };

  return (
  return (
    <div className="aq-drawer">
      <div className="aq-drawer-header">
        <div>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: 'var(--aq-text-primary)', letterSpacing: '-0.5px' }}>
            {ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
          </h2>
          <div style={{ color: 'var(--aq-text-secondary)', fontSize: 14, marginTop: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: alert.state === 'escalated_hitl' ? 'var(--aq-red)' : 'var(--aq-text-secondary)', fontWeight: 700 }}>
              {STATE_LABELS[alert.state] ?? alert.state}
            </span>
            <span>•</span>
            <span style={{ textTransform: 'capitalize' }}>Severity: {alert.severity}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--aq-border)', borderRadius: '50%', width: 40, height: 40, display: 'flex', alignItems: 'center', justifycenter: 'center', cursor: 'pointer', color: 'var(--aq-text-secondary)', transition: 'all 0.2s' }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'; e.currentTarget.style.color = 'var(--aq-red)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = 'var(--aq-text-secondary)'; }}
        >
          <X size={20} />
        </button>
      </div>

      <div className="aq-drawer-body">
        {drawerLoading && <div style={{ color: 'var(--aq-accent)', fontFamily: 'var(--aq-mono)', marginBottom: 20 }}>[ REFRESHING DATA... ]</div>}

        <section style={{ marginBottom: 32 }}>
          <div className="aq-section-title">Contextual Intelligence</div>
          <div className="aq-context-grid">
            <span className="aq-context-label">Pay Period</span>
            <span className="aq-context-value">{alert.pay_period_start} → {alert.pay_period_end}</span>
            
            <span className="aq-context-label">Placement ID</span>
            <span className="aq-context-value" style={{ color: 'var(--aq-accent)' }}>
              {(alert.trigger_context?.placement_bullhorn_id as string) ?? alert.placement_id ?? '—'}
            </span>
            
            <span className="aq-context-label">Detection Time</span>
            <span className="aq-context-value">{new Date(alert.detected_at).toLocaleString()}</span>
          </div>
          
          {Object.keys(alert.trigger_context || {}).length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--aq-text-secondary)', marginBottom: 8, textTransform: 'uppercase' }}>Raw Detector Output</div>
              <pre style={{ 
                background: 'rgba(0,0,0,0.3)', 
                border: '1px solid var(--aq-border)', 
                borderRadius: 12, 
                padding: 16, 
                fontSize: 12, 
                fontFamily: 'var(--aq-mono)', 
                color: 'var(--aq-accent)',
                maxHeight: 200,
                overflow: 'auto'
              }}>
                {JSON.stringify(alert.trigger_context, null, 2)}
              </pre>
            </div>
          )}
        </section>

        <section style={{ marginBottom: 32 }}>
          <div className="aq-section-title">Agent Event Trail</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {alert.events.map((e) => (
              <div
                key={e.id}
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--aq-border)',
                  borderRadius: 12,
                  padding: '12px 16px',
                  position: 'relative'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, fontSize: 13, color: e.actor_type === 'human' ? 'var(--aq-accent)' : 'var(--aq-text-primary)' }}>
                    {e.event_type}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--aq-text-secondary)', fontFamily: 'var(--aq-mono)' }}>
                    {new Date(e.created_at).toLocaleTimeString()}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--aq-text-secondary)' }}>
                  Actor: <span style={{ fontFamily: 'var(--aq-mono)' }}>{e.actor_type}:{e.actor_id.slice(0, 8)}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {alert.state !== 'resolved' && (
          <section style={{ background: 'rgba(45, 212, 191, 0.03)', border: '1px solid rgba(45, 212, 191, 0.1)', borderRadius: 20, padding: 24 }}>
            <div className="aq-section-title" style={{ color: 'var(--aq-accent)' }}>Human-in-the-Loop Resolution</div>
            
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--aq-text-secondary)', marginBottom: 8, textTransform: 'uppercase' }}>Resolution Type</label>
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
                style={{ width: '100%', padding: '12px', background: '#0f172a', color: '#fff', border: '1px solid var(--aq-border)', borderRadius: 10, fontSize: 14 }}
              >
                <option value="employee_corrected">Employee Corrected — Timesheet fixed</option>
                <option value="recruiter_override">Recruiter Override — Verified OK</option>
                <option value="exception_approved">Exception Approved — Valid variance</option>
                <option value="false_positive">False Positive — Detector error</option>
              </select>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--aq-text-secondary)', marginBottom: 8, textTransform: 'uppercase' }}>Platform Action (Automated)</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value as typeof action)}
                style={{ width: '100%', padding: '12px', background: '#0f172a', color: '#fff', border: '1px solid var(--aq-border)', borderRadius: 10, fontSize: 14 }}
              >
                <option value="">(No Bullhorn write-back)</option>
                <option value="mark_dnw">Mark as Did-Not-Work</option>
                <option value="set_hold">Set Billable Hold</option>
                <option value="release_hold">Release Billable Hold</option>
              </select>
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--aq-text-secondary)', marginBottom: 8, textTransform: 'uppercase' }}>Audit Notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                placeholder="Enter justification for this resolution..."
                style={{ width: '100%', padding: '12px', background: '#0f172a', color: '#fff', border: '1px solid var(--aq-border)', borderRadius: 10, fontSize: 14, fontFamily: 'inherit' }}
              />
            </div>

            <button
              onClick={handleResolve}
              disabled={actionBusy}
              className="aq-btn-primary"
            >
              {actionBusy ? 'Processing...' : 'Confirm Resolution'}
            </button>
          </section>
        )}
      </div>
    </div>
  );

        {hasReversible && (
          <section style={{ marginTop: 24 }}>
            <button
              onClick={onReverse}
              disabled={actionBusy}
              style={{
                width: '100%',
                padding: '10px 16px',
                background: '#fef2f2',
                color: '#b91c1c',
                border: '1.5px solid #fecaca',
                borderRadius: 8,
                fontWeight: 700,
                cursor: actionBusy ? 'wait' : 'pointer',
              }}
            >
              <Undo2 size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Undo most recent Bullhorn action
            </button>
            <div style={{ fontSize: 12, color: c.textMuted, marginTop: 6 }}>
              Reversal is available for 7 days after the action.
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
