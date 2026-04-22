import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Play, Loader2, CheckCircle2, XCircle, AlertTriangle, ArrowLeft,
  Clock, ChevronDown, ChevronUp, Shield, Zap, RefreshCw, RotateCcw,
  Eye, Bot,
} from 'lucide-react';
import type { AgentConfig } from '../../types';
import {
  createAgentPlan, getAgentPlan, approveAgentPlan, executeAgentPlan,
  cancelAgentPlan, getExecutionReport, listAgentRuns,
  type AgentPlanAction, type AgentRunOut,
} from '../../api/client';
import { useUI, type UIColors } from '../../context/UIContext';

type Phase = 'idle' | 'planning' | 'plan_ready' | 'approved' | 'executing' | 'completed' | 'completed_with_errors' | 'cancelled' | 'error';

interface AgentPlanViewProps {
  agent: AgentConfig;
  onBack: () => void;
}

// ── Small reusable badges ───────────────────────────────────

const SEVERITY_STYLES: Record<string, { bg: string; text: string }> = {
  high:   { bg: '#fee2e2', text: '#dc2626' },
  medium: { bg: '#fef3c7', text: '#b45309' },
  low:    { bg: '#dcfce7', text: '#15803d' },
};

function SeverityBadge({ severity }: { severity: string | null }) {
  const s = SEVERITY_STYLES[severity ?? 'medium'] ?? SEVERITY_STYLES.medium;
  return (
    <span style={{
      background: s.bg, color: s.text,
      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
      textTransform: 'uppercase', letterSpacing: '.3px',
    }}>
      {severity ?? '—'}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence === null) return <span style={{ color: '#94a3b8', fontSize: 12 }}>—</span>;
  const pct = Math.round(confidence * 100);
  const color = pct >= 95 ? '#15803d' : pct >= 70 ? '#b45309' : '#dc2626';
  const bg = pct >= 95 ? '#dcfce7' : pct >= 70 ? '#fef3c7' : '#fee2e2';
  return (
    <span style={{ background: bg, color, fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6 }}>
      {pct}%
    </span>
  );
}

function ExecStatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    success:         { bg: '#dcfce7', text: '#15803d', label: 'Success' },
    failed:          { bg: '#fee2e2', text: '#dc2626', label: 'Failed' },
    manual_required: { bg: '#fef3c7', text: '#b45309', label: 'Manual' },
    pending:         { bg: '#f1f5f9', text: '#64748b', label: 'Pending' },
  };
  const s = map[status] ?? map.pending;
  return (
    <span style={{ background: s.bg, color: s.text, fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 5, textTransform: 'uppercase', letterSpacing: '.3px' }}>
      {s.label}
    </span>
  );
}

// ── Single action row (expandable) ──────────────────────────

function ActionRow({ action, selected, onToggle, showCheckbox, c }: {
  action: AgentPlanAction;
  selected: boolean;
  onToggle: (id: string) => void;
  showCheckbox: boolean;
  c: UIColors;
}) {
  const [expanded, setExpanded] = useState(false);
  const details = action.details ?? {};
  const isExecuted = action.execution_status !== 'pending';
  const execColor = action.execution_status === 'success' ? '#10b981'
    : action.execution_status === 'failed' ? '#dc2626'
    : action.execution_status === 'manual_required' ? '#f59e0b' : '#94a3b8';

  return (
    <div style={{
      border: `1.5px solid ${isExecuted ? (action.execution_status === 'success' ? '#bbf7d0' : action.execution_status === 'failed' ? '#fecaca' : '#fde68a') : selected ? '#93c5fd' : c.cardBorder}`,
      borderRadius: 12, overflow: 'hidden', transition: 'all .15s',
      opacity: action.approval_status === 'skipped' ? 0.55 : 1,
      background: c.cardBg,
    }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: showCheckbox ? '32px 2.5fr 1fr 80px 80px 90px auto' : '2.5fr 1fr 80px 80px 90px auto',
          gap: 10, padding: '12px 16px', alignItems: 'center', cursor: 'pointer',
        }}
        onClick={() => setExpanded(!expanded)}
      >
        {showCheckbox && (
          <div onClick={e => { e.stopPropagation(); onToggle(action.id); }}>
            <input type="checkbox" checked={selected} readOnly style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#2563eb' }} />
          </div>
        )}
        <div>
          <div style={{ fontWeight: 700, fontSize: 13, color: c.text, display: 'flex', alignItems: 'center', gap: 8 }}>
            {isExecuted && (
              action.execution_status === 'success' ? <CheckCircle2 size={14} style={{ color: '#10b981', flexShrink: 0 }} />
              : action.execution_status === 'failed' ? <XCircle size={14} style={{ color: '#dc2626', flexShrink: 0 }} />
              : <AlertTriangle size={14} style={{ color: '#f59e0b', flexShrink: 0 }} />
            )}
            {action.target_name ?? action.target_ref ?? '—'}
          </div>
          <div style={{ fontSize: 12, color: c.textMuted, marginTop: 2, lineHeight: 1.4 }}>{action.description}</div>
        </div>
        <div>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            background: c.panelBg, color: c.textMuted,
            fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 6, whiteSpace: 'nowrap',
          }}>
            {action.action_type.replace(/_/g, ' ')}
          </span>
        </div>
        <div><ConfidenceBadge confidence={action.confidence} /></div>
        <div><SeverityBadge severity={action.severity} /></div>
        <div style={{ fontSize: 13, fontWeight: 600, color: (action.financial_impact ?? 0) > 100 ? '#dc2626' : c.textMuted, textAlign: 'right' }}>
          {action.financial_impact != null ? `$${Math.abs(action.financial_impact).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
        </div>
        <div>{expanded ? <ChevronUp size={16} style={{ color: c.textDim }} /> : <ChevronDown size={16} style={{ color: c.textDim }} />}</div>
      </div>

      {expanded && (
        <div style={{ borderTop: `1px solid ${c.cardBorder}`, background: c.subBg, padding: 20 }}>
          {isExecuted && (
            <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: c.textMuted }}>Execution:</span>
              <ExecStatusBadge status={action.execution_status} />
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <h4 style={{ fontSize: 11, fontWeight: 800, color: c.textDim, textTransform: 'uppercase', marginBottom: 8 }}>Details</h4>
              {Object.entries(details).filter(([k]) => !['explanation'].includes(k)).slice(0, 12).map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4, gap: 12 }}>
                  <span style={{ color: c.textMuted, fontWeight: 600, whiteSpace: 'nowrap' }}>{k.replace(/_/g, ' ')}</span>
                  <span style={{ fontWeight: 700, color: c.text, textAlign: 'right', wordBreak: 'break-all' }}>{v != null ? String(v) : '—'}</span>
                </div>
              ))}
            </div>
            <div>
              {!!details.explanation && (
                <div style={{ padding: '10px 14px', background: '#fef3c7', borderRadius: 8, fontSize: 12, color: '#92400e', lineHeight: 1.6, marginBottom: 10 }}>
                  <span style={{ fontWeight: 700 }}>AI Reasoning: </span>{String(details.explanation)}
                </div>
              )}
              {action.execution_result && (
                <div style={{ padding: '10px 14px', background: execColor + '18', borderRadius: 8, fontSize: 12, color: execColor, lineHeight: 1.6, marginBottom: 10 }}>
                  <span style={{ fontWeight: 700 }}>Result: </span>{String((action.execution_result as Record<string, unknown>).message ?? JSON.stringify(action.execution_result))}
                </div>
              )}
              {action.error_message && (
                <div style={{ padding: '10px 14px', background: '#fee2e2', borderRadius: 8, fontSize: 12, color: '#dc2626', lineHeight: 1.6 }}>
                  <span style={{ fontWeight: 700 }}>Error: </span>{action.error_message}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Main component ──────────────────────────────────────────

export default function AgentPlanView({ agent, onBack }: AgentPlanViewProps) {
  const { c } = useUI();
  const [phase, setPhase] = useState<Phase>('idle');
  const [runId, setRunId] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentPlanAction[]>([]);
  const [planSummary, setPlanSummary] = useState<Record<string, unknown> | null>(null);
  const [executionReport, setExecutionReport] = useState<Record<string, unknown> | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [pastRuns, setPastRuns] = useState<AgentRunOut[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [planningStep, setPlanningStep] = useState(0);

  const agentTypeId = useMemo(() => {
    const map: Record<string, string> = {
      'time-anomaly': 'time-anomaly',
      'risk-alert': 'risk-alert',
      'invoice-matching': 'invoice-matching',
      'collections': 'collections',
      'compliance': 'compliance',
      'payment-prediction': 'payment-prediction',
      'vms-reconciliation': 'vms-match',
    };
    return map[agent.id] ?? agent.id;
  }, [agent.id]);

  // Animated planning steps
  useEffect(() => {
    if (phase !== 'planning') { setPlanningStep(0); return; }
    const steps = [0, 1, 2, 3];
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % steps.length;
      setPlanningStep(steps[i]);
    }, 2000);
    return () => clearInterval(interval);
  }, [phase]);

  const [backendReady, setBackendReady] = useState(true);

  const fetchPastRuns = useCallback(async () => {
    setLoadingRuns(true);
    try {
      const runs = await listAgentRuns(agentTypeId, 10);
      setPastRuns(runs);
      setBackendReady(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '';
      if (msg.includes('Network error') || msg.includes('Internal Server Error') || msg.includes('500') || msg.includes('database')) {
        setBackendReady(false);
      }
    } finally {
      setLoadingRuns(false);
    }
  }, [agentTypeId]);

  useEffect(() => { fetchPastRuns(); }, [fetchPastRuns]);

  const resetToIdle = useCallback(() => {
    setPhase('idle');
    setRunId(null);
    setActions([]);
    setPlanSummary(null);
    setExecutionReport(null);
    setError(null);
    setSelectedIds(new Set());
  }, []);

  const handleStartPlan = useCallback(async () => {
    setPhase('planning');
    setError(null);
    setActions([]);
    setPlanSummary(null);
    setExecutionReport(null);
    try {
      const result = await createAgentPlan(agentTypeId);
      setRunId(result.run_id);
      if (result.status === 'error') {
        setPhase('error');
        setError((result as Record<string, unknown>).error as string ?? 'Planning failed — the agent could not analyze the data.');
        fetchPastRuns();
        return;
      }
      const plan = await getAgentPlan(result.run_id);
      setActions(plan.actions);
      setPlanSummary(plan.run.plan);
      setSelectedIds(new Set(plan.actions.map(a => a.id)));
      setPhase('plan_ready');
      fetchPastRuns();
    } catch (e) {
      setPhase('error');
      const msg = e instanceof Error ? e.message : 'Planning failed';
      if (msg.toLowerCase().includes('not found') && !msg.toLowerCase().includes('record')) {
        setError('The plan endpoint is not available on the backend yet. This feature requires the latest API deployment.');
      } else if (msg.toLowerCase().includes('database error') || msg.toLowerCase().includes('migration')) {
        setError('Database setup required — the backend needs a migration to support the agent execution framework. Contact your administrator.');
      } else if (msg.toLowerCase().includes('internal server error')) {
        setError('The server encountered an error processing this request. This may indicate the backend needs to be updated. Check the API logs for details.');
      } else {
        setError(msg);
      }
      fetchPastRuns();
    }
  }, [agentTypeId, fetchPastRuns]);

  const handleApproveAll = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      await approveAgentPlan(runId);
      setPhase('executing');
      const result = await executeAgentPlan(runId);
      const report = await getExecutionReport(runId);
      setActions([...report.succeeded, ...report.failed, ...report.manual_required, ...report.skipped]);
      setExecutionReport(result.report);
      setPhase(result.status as Phase);
      fetchPastRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Execution failed');
      setPhase('error');
    }
  }, [runId, fetchPastRuns]);

  const handleApproveSelected = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      await approveAgentPlan(runId, Array.from(selectedIds));
      setPhase('executing');
      const result = await executeAgentPlan(runId);
      const report = await getExecutionReport(runId);
      setActions([...report.succeeded, ...report.failed, ...report.manual_required, ...report.skipped]);
      setExecutionReport(result.report);
      setPhase(result.status as Phase);
      fetchPastRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Execution failed');
      setPhase('error');
    }
  }, [runId, selectedIds, fetchPastRuns]);

  const handleCancel = useCallback(async () => {
    if (!runId) return;
    try {
      await cancelAgentPlan(runId);
      setPhase('cancelled');
      fetchPastRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cancel failed');
    }
  }, [runId, fetchPastRuns]);

  const handleViewPastRun = useCallback(async (id: string) => {
    setError(null);
    try {
      const plan = await getAgentPlan(id);
      setRunId(id);
      setActions(plan.actions);
      setPlanSummary(plan.run.plan);
      setExecutionReport(plan.run.execution_report);
      const s = plan.run.status as Phase;
      setPhase(s);
      if (s === 'plan_ready') {
        setSelectedIds(new Set(plan.actions.map(a => a.id)));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run');
    }
  }, []);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === actions.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(actions.map(a => a.id)));
  }, [actions, selectedIds.size]);

  const stats = useMemo(() => {
    const highSeverity = actions.filter(a => a.severity === 'high').length;
    const mediumSeverity = actions.filter(a => a.severity === 'medium').length;
    const lowSeverity = actions.filter(a => a.severity === 'low').length;
    const totalImpact = actions.reduce((sum, a) => sum + (a.financial_impact ?? 0), 0);
    const succeeded = actions.filter(a => a.execution_status === 'success').length;
    const failed = actions.filter(a => a.execution_status === 'failed').length;
    const manual = actions.filter(a => a.execution_status === 'manual_required').length;
    return { highSeverity, mediumSeverity, lowSeverity, totalImpact, total: actions.length, succeeded, failed, manual };
  }, [actions]);

  const isComingSoon = agent.status === 'coming-soon';
  const showActions = (phase === 'plan_ready' || phase === 'completed' || phase === 'completed_with_errors' || phase === 'cancelled') && actions.length > 0;
  const showEmptyPlan = (phase === 'plan_ready' || phase === 'completed') && actions.length === 0 && planSummary;
  const isReport = phase === 'completed' || phase === 'completed_with_errors';
  const phaseLabel: Record<string, string> = { P0: 'Phase 0 — Core', P1: 'Phase 1 — Advanced', P2: 'Phase 2 — Specialized' };
  const planningSteps = ['Loading data from Bullhorn...', 'Running AI analysis...', 'Generating proposed actions...', 'Preparing plan for review...'];

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Command Center
      </button>

      {/* ── Agent Header ────────────────────────────── */}
      <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 16, padding: 32, marginBottom: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.1)', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 6, background: `linear-gradient(90deg, ${agent.color}, ${agent.color}88)` }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <span style={{ fontSize: 32 }}>{agent.icon}</span>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: c.text, margin: 0 }}>{agent.name}</h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: agent.status === 'active' ? '#dcfce7' : agent.status === 'beta' ? '#fef3c7' : '#f1f5f9', color: agent.status === 'active' ? '#065f46' : agent.status === 'beta' ? '#92400e' : '#64748b', textTransform: 'uppercase', letterSpacing: '.3px' }}>
                    {agent.status === 'active' ? 'Active' : agent.status === 'beta' ? 'Beta' : 'Coming Soon'}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: c.textMuted }}>{phaseLabel[agent.phase]}</span>
                </div>
              </div>
            </div>
            <p style={{ color: c.textMuted, fontSize: 14, maxWidth: 600, lineHeight: 1.6, marginTop: 8 }}>{agent.description}</p>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            {showActions && (
              <button onClick={resetToIdle} style={outlineBtnStyle('#64748b')}>
                <RotateCcw size={14} /> New Run
              </button>
            )}
            {(phase === 'idle' || phase === 'cancelled' || phase === 'completed' || phase === 'completed_with_errors' || phase === 'error') && (
              <button
                onClick={handleStartPlan}
                disabled={isComingSoon || !backendReady}
                style={{
                  background: (isComingSoon || !backendReady) ? '#e2e8f0' : agent.color,
                  color: (isComingSoon || !backendReady) ? '#94a3b8' : '#fff', border: 'none', borderRadius: 10,
                  padding: '12px 28px', fontSize: 15, fontWeight: 700,
                  cursor: (isComingSoon || !backendReady) ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 8,
                  boxShadow: (isComingSoon || !backendReady) ? 'none' : '0 2px 8px rgba(0,0,0,0.15)',
                }}
              >
                <Play size={16} fill={(isComingSoon || !backendReady) ? '#94a3b8' : '#fff'} />
                {isComingSoon ? 'Not Available Yet' : !backendReady ? 'Backend Setup Pending' : 'Run Agent'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Error banner ────────────────────────────── */}
      {error && (
        <div style={{ background: '#fee2e2', border: '1.5px solid #fca5a5', borderRadius: 12, padding: '16px 20px', color: '#dc2626', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
          <XCircle size={20} style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, fontSize: 14 }}>{error}</div>
          <button onClick={() => { setError(null); setPhase('idle'); }} style={{ background: 'none', border: '1px solid #dc2626', borderRadius: 6, color: '#dc2626', padding: '4px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
            Dismiss
          </button>
        </div>
      )}

      {/* ── Backend Not Ready banner ────────────────── */}
      {!backendReady && phase === 'idle' && (
        <div style={{ background: '#fef3c7', border: '1.5px solid #fde68a', borderRadius: 12, padding: '16px 20px', color: '#92400e', marginBottom: 20, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <AlertTriangle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>Backend Setup Pending</div>
            <div style={{ fontSize: 13, lineHeight: 1.5 }}>
              The agent execution framework requires a database migration that hasn't been applied yet.
              The API is running but agent operations will fail until <strong>migration 022</strong> is executed.
              Contact your backend administrator to run the migration.
            </div>
          </div>
        </div>
      )}

      {/* ── Capabilities + Config (shown in idle/error only) ─── */}
      {(phase === 'idle' || phase === 'error') && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
          <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
            <h3 style={{ fontSize: 14, fontWeight: 800, color: c.text, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '.5px' }}>Capabilities</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {agent.capabilities.map((cap, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: c.textMuted }}>
                  <CheckCircle2 size={14} style={{ color: agent.color, marginTop: 2, flexShrink: 0 }} />
                  {cap}
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
            <h3 style={{ fontSize: 14, fontWeight: 800, color: c.text, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '.5px' }}>How It Works</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {[
                { step: '1', title: 'Analyze', desc: 'Agent loads data and identifies issues, matches, or risks using AI.' },
                { step: '2', title: 'Present Plan', desc: 'A structured plan of proposed actions is presented for your review.' },
                { step: '3', title: 'Approve', desc: 'You approve all, select specific actions, or reject the plan entirely.' },
                { step: '4', title: 'Execute & Report', desc: 'Approved actions are executed autonomously with a full outcome report.' },
              ].map(({ step, title, desc }) => (
                <div key={step} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: `${agent.color}18`, color: agent.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, flexShrink: 0 }}>{step}</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, color: c.text }}>{title}</div>
                    <div style={{ fontSize: 12, color: c.textMuted, lineHeight: 1.4 }}>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Planning phase (animated steps) ──────────── */}
      {phase === 'planning' && (
        <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: '48px 40px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
            <div style={{ width: 56, height: 56, borderRadius: '50%', background: `${agent.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={28} style={{ color: agent.color, animation: 'spin 3s linear infinite' }} />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: c.text }}>Agent is analyzing your data...</div>
              <div style={{ fontSize: 14, color: c.textMuted, marginTop: 4 }}>Building a plan of proposed actions for your review.</div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {planningSteps.map((label, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderRadius: 10, background: i <= planningStep ? `${agent.color}08` : c.subBg, border: `1.5px solid ${i <= planningStep ? `${agent.color}30` : c.cardBorder}`, transition: 'all .3s' }}>
                {i < planningStep ? (
                  <CheckCircle2 size={18} style={{ color: '#10b981' }} />
                ) : i === planningStep ? (
                  <Loader2 size={18} style={{ color: agent.color, animation: 'spin 1s linear infinite' }} />
                ) : (
                  <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${c.cardBorder}` }} />
                )}
                <span style={{ fontSize: 14, fontWeight: i <= planningStep ? 700 : 500, color: i <= planningStep ? c.text : c.textDim }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Executing phase ─────────────────────────── */}
      {phase === 'executing' && (
        <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: '48px 40px', textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 24 }}>
          <Loader2 size={40} style={{ color: agent.color, animation: 'spin 1s linear infinite', marginBottom: 16 }} />
          <div style={{ fontSize: 18, fontWeight: 700, color: c.text }}>Executing approved actions...</div>
          <div style={{ fontSize: 14, color: c.textMuted, marginTop: 6 }}>Processing {selectedIds.size || actions.length} actions. This may take a moment.</div>
          <div style={{ marginTop: 20, height: 4, background: c.cardBorder, borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ height: '100%', background: agent.color, borderRadius: 4, width: '60%', animation: 'shimmer 1.5s ease-in-out infinite' }} />
          </div>
        </div>
      )}

      {/* ── Empty Plan (no issues found) ────────────── */}
      {showEmptyPlan && (
        <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: '48px 40px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', marginBottom: 24, textAlign: 'center' }}>
          <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
            <CheckCircle2 size={32} style={{ color: '#15803d' }} />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: c.text, marginBottom: 8 }}>Analysis Complete — No Issues Found</div>
          <div style={{ fontSize: 14, color: c.textMuted, maxWidth: 500, margin: '0 auto', lineHeight: 1.6 }}>
            {planSummary.agent_summary ? String(planSummary.agent_summary) : 'The agent analyzed your data and found no actions to propose at this time.'}
          </div>
          <div style={{ marginTop: 24, display: 'flex', gap: 12, justifyContent: 'center' }}>
            <button onClick={resetToIdle} style={outlineBtnStyle(agent.color)}>
              <RotateCcw size={14} /> New Run
            </button>
          </div>
        </div>
      )}

      {/* ── Plan Ready / Report content ─────────────── */}
      {showActions && (
        <>
          {/* Execution Report banner (completed/completed_with_errors) */}
          {isReport && executionReport && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
              <div style={{ background: '#dcfce7', borderRadius: 12, padding: '16px 20px', borderLeft: '4px solid #10b981' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <CheckCircle2 size={18} style={{ color: '#15803d' }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#15803d' }}>Succeeded</span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#15803d' }}>{stats.succeeded}</div>
                <div style={{ fontSize: 12, color: '#16a34a' }}>actions completed successfully</div>
              </div>
              <div style={{ background: '#fef3c7', borderRadius: 12, padding: '16px 20px', borderLeft: '4px solid #f59e0b' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <AlertTriangle size={18} style={{ color: '#b45309' }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#b45309' }}>Manual Review</span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#b45309' }}>{stats.manual}</div>
                <div style={{ fontSize: 12, color: '#d97706' }}>items need manual intervention</div>
              </div>
              <div style={{ background: stats.failed > 0 ? '#fee2e2' : '#f1f5f9', borderRadius: 12, padding: '16px 20px', borderLeft: `4px solid ${stats.failed > 0 ? '#dc2626' : '#94a3b8'}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <XCircle size={18} style={{ color: stats.failed > 0 ? '#dc2626' : '#94a3b8' }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: stats.failed > 0 ? '#dc2626' : '#94a3b8' }}>Failed</span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: stats.failed > 0 ? '#dc2626' : '#94a3b8' }}>{stats.failed}</div>
                <div style={{ fontSize: 12, color: stats.failed > 0 ? '#ef4444' : '#94a3b8' }}>actions failed with errors</div>
              </div>
            </div>
          )}

          {/* Summary stats (plan_ready) */}
          {phase === 'plan_ready' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'Total Actions', value: stats.total, color: '#2563eb' },
                { label: 'High Severity', value: stats.highSeverity, color: '#dc2626' },
                { label: 'Medium Severity', value: stats.mediumSeverity, color: '#f59e0b' },
                { label: 'Low Severity', value: stats.lowSeverity, color: '#10b981' },
                { label: 'Est. $ Impact', value: `$${Math.abs(stats.totalImpact).toLocaleString(undefined, { maximumFractionDigits: 0 })}`, color: '#7c3aed' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: '16px 20px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', borderTop: `3px solid ${color}` }}>
                  <div style={{ fontSize: 24, fontWeight: 800, color }}>{value}</div>
                  <div style={{ fontSize: 12, color: c.textMuted, marginTop: 2 }}>{label}</div>
                </div>
              ))}
            </div>
          )}

          {/* Plan summary */}
          {planSummary && (
            <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', gap: 12 }}>
              <Shield size={20} style={{ color: agent.color, flexShrink: 0 }} />
              <div style={{ fontSize: 14, color: c.text, lineHeight: 1.5 }}>
                <strong>{isReport ? 'Execution Summary' : 'Plan Summary'}:</strong>{' '}
                {planSummary.agent_summary
                  ? String(planSummary.agent_summary)
                  : `Analyzed ${planSummary.records_analyzed ?? '—'} records against ${planSummary.placements_loaded ?? '—'} placements. Proposing ${planSummary.actions_proposed ?? actions.length} actions.`}
              </div>
            </div>
          )}

          {phase === 'cancelled' && (
            <div style={{ borderRadius: 12, padding: '16px 20px', marginBottom: 20, background: c.panelBg, border: `1.5px solid ${c.cardBorder}`, display: 'flex', alignItems: 'center', gap: 12 }}>
              <XCircle size={20} style={{ color: c.textMuted }} />
              <span style={{ fontSize: 14, color: c.text }}><strong>Plan rejected.</strong> No actions were executed. Click "Run Agent" to start a new analysis.</span>
            </div>
          )}

          {/* Approve/reject toolbar (plan_ready only) */}
          {phase === 'plan_ready' && (
            <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: '14px 20px', marginBottom: 16, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', display: 'flex', gap: 10, alignItems: 'center', position: 'sticky', top: 0, zIndex: 10 }}>
              <button onClick={handleApproveAll} style={primaryBtnStyle(agent.color)}>
                <CheckCircle2 size={16} /> Approve All ({actions.length})
              </button>
              {selectedIds.size < actions.length && selectedIds.size > 0 && (
                <button onClick={handleApproveSelected} style={outlineBtnStyle(agent.color)}>
                  <CheckCircle2 size={16} /> Approve Selected ({selectedIds.size})
                </button>
              )}
              <button onClick={handleCancel} style={outlineBtnStyle('#dc2626')}>
                <XCircle size={16} /> Reject Plan
              </button>
              <div style={{ flex: 1 }} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: c.textMuted, cursor: 'pointer', userSelect: 'none' }}>
                <input type="checkbox" checked={selectedIds.size === actions.length} onChange={toggleAll} style={{ accentColor: '#2563eb' }} />
                Select all
              </label>
            </div>
          )}

          {/* Column headers */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: phase === 'plan_ready' ? '32px 2.5fr 1fr 80px 80px 90px auto' : '2.5fr 1fr 80px 80px 90px auto',
            gap: 10, padding: '8px 16px', fontSize: 11, fontWeight: 700, color: c.textDim, textTransform: 'uppercase', letterSpacing: '.5px',
          }}>
            {phase === 'plan_ready' && <div />}
            <div>Action</div>
            <div>Type</div>
            <div>Confidence</div>
            <div>Severity</div>
            <div style={{ textAlign: 'right' }}>$ Impact</div>
            <div style={{ width: 16 }} />
          </div>

          {/* Action rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24 }}>
            {actions.map(action => (
              <ActionRow
                key={action.id}
                action={action}
                selected={selectedIds.has(action.id)}
                onToggle={toggleSelect}
                showCheckbox={phase === 'plan_ready'}
                c={c}
              />
            ))}
          </div>
        </>
      )}

      {/* ── Run History ─────────────────────────────── */}
      <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, color: c.text, textTransform: 'uppercase', letterSpacing: '.5px', display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
            <Clock size={16} /> Run History
          </h3>
          <button onClick={fetchPastRuns} style={{ background: 'none', border: 'none', color: c.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {loadingRuns ? (
          <div style={{ textAlign: 'center', padding: 20, color: c.textDim }}>
            <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : pastRuns.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: c.textDim }}>
            <Bot size={36} style={{ marginBottom: 8, opacity: 0.3 }} />
            <div style={{ fontWeight: 600, fontSize: 14 }}>No runs yet</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>Click "Run Agent" to start a plan-approve-execute cycle.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {pastRuns.map(run => {
              const isSelected = runId === run.id && phase !== 'idle';
              return (
                <div
                  key={run.id}
                  onClick={() => handleViewPastRun(run.id)}
                  style={{
                    border: `1.5px solid ${isSelected ? agent.color : c.cardBorder}`,
                    borderRadius: 10, padding: '12px 16px', cursor: 'pointer', transition: 'all .15s',
                    background: isSelected ? `${agent.color}06` : c.panelBg,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <RunStatusIcon status={run.status} />
                      <span style={{ fontWeight: 700, fontSize: 13, color: c.text, fontFamily: 'monospace' }}>{run.id.slice(0, 8)}</span>
                      <RunStatusBadge status={run.status} />
                      <span style={{ fontSize: 12, color: c.textDim }}>
                        {run.created_at ? new Date(run.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      {run.plan && (
                        <span style={{ fontSize: 12, color: c.textMuted }}>
                          <strong>{(run.plan as Record<string, unknown>).actions_proposed as number ?? '—'}</strong> actions
                        </span>
                      )}
                      {run.execution_report && (
                        <>
                          <span style={{ fontSize: 12, color: '#10b981', fontWeight: 600 }}>
                            {(run.execution_report as Record<string, unknown>).succeeded as number ?? 0} ✓
                          </span>
                          {((run.execution_report as Record<string, unknown>).failed as number ?? 0) > 0 && (
                            <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>
                              {(run.execution_report as Record<string, unknown>).failed as number} ✗
                            </span>
                          )}
                        </>
                      )}
                      <Eye size={14} style={{ color: c.textDim }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}


// ── Helper components ───────────────────────────────────────

function RunStatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle2 size={16} style={{ color: '#10b981' }} />;
  if (status === 'completed_with_errors') return <AlertTriangle size={16} style={{ color: '#f59e0b' }} />;
  if (status === 'cancelled') return <XCircle size={16} style={{ color: '#94a3b8' }} />;
  if (status === 'error') return <XCircle size={16} style={{ color: '#dc2626' }} />;
  if (status === 'plan_ready') return <Zap size={16} style={{ color: '#2563eb' }} />;
  if (status === 'executing' || status === 'planning') return <Loader2 size={16} style={{ color: '#f59e0b', animation: 'spin 1s linear infinite' }} />;
  return <Clock size={16} style={{ color: '#94a3b8' }} />;
}

function RunStatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; text: string; label: string }> = {
    planning: { bg: '#eff6ff', text: '#2563eb', label: 'Planning' },
    plan_ready: { bg: '#eff6ff', text: '#2563eb', label: 'Awaiting Approval' },
    approved: { bg: '#fef3c7', text: '#b45309', label: 'Approved' },
    executing: { bg: '#fef3c7', text: '#b45309', label: 'Executing' },
    completed: { bg: '#dcfce7', text: '#15803d', label: 'Completed' },
    completed_with_errors: { bg: '#fef3c7', text: '#b45309', label: 'Completed w/ Errors' },
    cancelled: { bg: '#f1f5f9', text: '#64748b', label: 'Cancelled' },
    error: { bg: '#fee2e2', text: '#dc2626', label: 'Error' },
    pending: { bg: '#f1f5f9', text: '#64748b', label: 'Pending' },
    running: { bg: '#fef3c7', text: '#b45309', label: 'Running' },
    success: { bg: '#dcfce7', text: '#15803d', label: 'Success' },
  };
  const s = styles[status] ?? { bg: '#f1f5f9', text: '#64748b', label: status };
  return (
    <span style={{ background: s.bg, color: s.text, fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, textTransform: 'uppercase', letterSpacing: '.3px' }}>
      {s.label}
    </span>
  );
}

function primaryBtnStyle(color: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    background: color, color: '#fff', border: 'none',
    borderRadius: 10, padding: '10px 24px', fontSize: 14, fontWeight: 700,
    cursor: 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
  };
}

function outlineBtnStyle(color: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    background: 'transparent', color, border: `1.5px solid ${color}`,
    borderRadius: 10, padding: '9px 22px', fontSize: 14, fontWeight: 700,
    cursor: 'pointer',
  };
}
