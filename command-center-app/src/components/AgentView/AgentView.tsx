import { useState } from 'react';
import { Play, Loader2, Clock, CheckCircle2, XCircle, AlertTriangle, ArrowLeft } from 'lucide-react';
import type { AgentConfig } from '../../types';
import VMSMatchReview, { type VMSMatchRecord } from '../VMSMatchReview/VMSMatchReview';
import { useUI } from '../../context/UIContext';

interface AgentViewProps {
  agent: AgentConfig;
  onBack: () => void;
}

interface RunRecord {
  id: string;
  timestamp: string;
  status: 'success' | 'warning' | 'failed';
  recordsProcessed: number;
  flagged: number;
  duration: string;
  summary: string;
}

const mockRuns: Record<string, RunRecord[]> = {
  'time-anomaly': [
    { id: 'R-001', timestamp: '09/05/2025 2:30 PM', status: 'success', recordsProcessed: 1847, flagged: 23, duration: '4.2s', summary: '23 anomalies detected: 15 overtime violations, 5 missing consecutive, 3 unusual patterns' },
    { id: 'R-002', timestamp: '09/04/2025 2:30 PM', status: 'success', recordsProcessed: 1832, flagged: 18, duration: '3.8s', summary: '18 anomalies detected: 12 overtime violations, 4 missing consecutive, 2 unusual patterns' },
    { id: 'R-003', timestamp: '09/03/2025 2:30 PM', status: 'warning', recordsProcessed: 1820, flagged: 31, duration: '5.1s', summary: '31 anomalies — spike in missing timesheets detected for South Region' },
  ],
  'risk-alert': [
    { id: 'R-010', timestamp: '09/05/2025 3:00 PM', status: 'success', recordsProcessed: 274, flagged: 12, duration: '2.1s', summary: '12 risk alerts: 4 placement mismatches, 3 rate flags, 5 hours flags' },
    { id: 'R-011', timestamp: '09/04/2025 3:00 PM', status: 'success', recordsProcessed: 271, flagged: 9, duration: '1.9s', summary: '9 risk alerts: 3 placement mismatches, 2 rate flags, 4 hours flags' },
  ],
  'invoice-matching': [
    { id: 'R-020', timestamp: '09/05/2025 4:00 PM', status: 'success', recordsProcessed: 962, flagged: 7, duration: '6.3s', summary: '7 mismatches found: 3 amount discrepancies, 2 missing line items, 2 duplicate charges' },
    { id: 'R-021', timestamp: '09/04/2025 4:00 PM', status: 'failed', recordsProcessed: 0, flagged: 0, duration: '0.8s', summary: 'Failed: Bullhorn API timeout — retried 3x, circuit breaker tripped' },
  ],
};

// Seed mock VMS matches for demo
const mockVMSMatches: VMSMatchRecord[] = [
  { id: 'm1', vms_record_id: 'v1', placement_id: 'p1', bullhorn_id: 245, confidence: 0.97, match_method: 'alias', name_similarity: 0.97, rate_delta: 0, hours_delta: 0, financial_impact: 0, llm_explanation: null, status: 'approved', review_notes: null, candidate_name: 'Zabara, Yuri', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0, bill_rate: 1430, vms_platform: 'Fieldglass', placement_ref: 'P-245' },
  { id: 'm2', vms_record_id: 'v2', placement_id: 'p2', bullhorn_id: 289, confidence: 0.93, match_method: 'fuzzy', name_similarity: 0.93, rate_delta: 0, hours_delta: 0, financial_impact: 0, llm_explanation: 'Typo detected: "Moraa" vs "Moraal" — 1 character difference.', status: 'pending', review_notes: null, candidate_name: 'Jonathan Moraa', week_ending: '2026-04-04', regular_hours: 37.5, ot_hours: 0, bill_rate: 1282.5, vms_platform: 'Fieldglass', placement_ref: 'P-289' },
  { id: 'm3', vms_record_id: 'v3', placement_id: 'p3', bullhorn_id: 405, confidence: 0.97, match_method: 'fuzzy', name_similarity: 0.97, rate_delta: -2.57, hours_delta: 0, financial_impact: 96.38, llm_explanation: null, status: 'pending', review_notes: null, candidate_name: 'K. Veloz', week_ending: '2026-04-04', regular_hours: 35, ot_hours: 0, bill_rate: 67.43, vms_platform: 'Fieldglass', placement_ref: 'P-405' },
  { id: 'm4', vms_record_id: 'v4', placement_id: null, bullhorn_id: null, confidence: 0, match_method: 'unmatched', name_similarity: 0, rate_delta: null, hours_delta: null, financial_impact: null, llm_explanation: 'No placement found matching "Yana Almeida-Smith" within date range.', status: 'pending', review_notes: null, candidate_name: 'Yana Almeida-Smith', week_ending: '2026-03-28', regular_hours: 40, ot_hours: 15.33, bill_rate: 72.41, vms_platform: 'Fieldglass', placement_ref: 'P-417' },
  { id: 'm5', vms_record_id: 'v5', placement_id: 'p5', bullhorn_id: 92, confidence: 0.97, match_method: 'fuzzy', name_similarity: 0.97, rate_delta: 0, hours_delta: 0, financial_impact: 0, llm_explanation: null, status: 'approved', review_notes: null, candidate_name: 'GROVES, JOY', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0, bill_rate: 1190, vms_platform: 'Fieldglass', placement_ref: 'P-092' },
  { id: 'm6', vms_record_id: 'v6', placement_id: 'p6', bullhorn_id: 228, confidence: 0.72, match_method: 'llm', name_similarity: 0.61, rate_delta: 42.03, hours_delta: 0, financial_impact: 1576.13, llm_explanation: 'Siddique Farrukh matched to Farrukh Siddique (P-228) by name reversal. Rate variance of $42.03/h flagged — VMS rate $1332.47 vs ATS $1315.00. Possible rate discrepancy.', status: 'pending', review_notes: null, candidate_name: 'Siddique Farrukh', week_ending: '2026-03-06', regular_hours: 37.5, ot_hours: 0, bill_rate: 1332.47, vms_platform: 'Fieldglass', placement_ref: 'P-230' },
];

export default function AgentView({ agent, onBack }: AgentViewProps) {
  const { c } = useUI();
  const [isRunning, setIsRunning] = useState(false);
  const [runs, setRuns] = useState<RunRecord[]>(mockRuns[agent.id] || []);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [vmsMatches, setVmsMatches] = useState<VMSMatchRecord[]>(mockVMSMatches);
  const isComingSoon = agent.status === 'coming-soon';

  const handleRun = () => {
    if (isComingSoon) return;
    setIsRunning(true);
    setTimeout(() => {
      const newRun: RunRecord = {
        id: `R-${Date.now()}`,
        timestamp: new Date().toLocaleString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true }),
        status: 'success',
        recordsProcessed: Math.floor(Math.random() * 1500) + 200,
        flagged: Math.floor(Math.random() * 25) + 1,
        duration: `${(Math.random() * 5 + 1).toFixed(1)}s`,
        summary: `Agent run completed. Review flagged items in the Action Queue.`,
      };
      setRuns([newRun, ...runs]);
      setIsRunning(false);
    }, 2000);
  };

  const handleApprove = (matchId: string) => {
    setVmsMatches(prev => prev.map(m => m.id === matchId ? { ...m, status: 'approved' } : m));
  };

  const handleReject = (matchId: string, notes: string) => {
    setVmsMatches(prev => prev.map(m => m.id === matchId ? { ...m, status: 'rejected', review_notes: notes } : m));
  };

  const handleDismiss = (matchId: string) => {
    setVmsMatches(prev => prev.map(m => m.id === matchId ? { ...m, status: 'dismissed' } : m));
  };

  const statusIcon = (s: RunRecord['status']) => {
    if (s === 'success') return <CheckCircle2 size={16} style={{ color: '#10b981' }} />;
    if (s === 'warning') return <AlertTriangle size={16} style={{ color: '#f59e0b' }} />;
    return <XCircle size={16} style={{ color: '#dc2626' }} />;
  };

  const phaseLabel = { P0: 'Phase 0 — Core', P1: 'Phase 1 — Advanced', P2: 'Phase 2 — Specialized' };

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Command Center
      </button>

      {/* Agent Header */}
      <div className="agent-header" style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 16, padding: 32, marginBottom: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.1)', position: 'relative', overflow: 'hidden' }}>
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

          <button
            onClick={handleRun}
            disabled={isRunning || isComingSoon}
            style={{
              background: isComingSoon ? '#e2e8f0' : isRunning ? '#93c5fd' : agent.color,
              color: isComingSoon ? '#94a3b8' : '#fff', border: 'none', borderRadius: 10,
              padding: '12px 28px', fontSize: 15, fontWeight: 700,
              cursor: isComingSoon ? 'not-allowed' : isRunning ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 8, transition: 'all .15s',
              boxShadow: isComingSoon ? 'none' : '0 2px 8px rgba(0,0,0,0.15)',
            }}
          >
            {isRunning ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={16} fill={isComingSoon ? '#94a3b8' : '#fff'} />}
            {isRunning ? 'Running...' : isComingSoon ? 'Not Available Yet' : 'Run Agent'}
          </button>
        </div>
      </div>

      {/* Capabilities + Config */}
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
          <h3 style={{ fontSize: 14, fontWeight: 800, color: c.text, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '.5px' }}>Agent Configuration</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {([
              ['Trigger Mode', 'Manual + Scheduled'],
              ['Human Approval', 'Required for actions'],
              ['Schedule', 'Daily at 2:30 PM CT'],
              ['LLM Model', 'Claude 3.5 Sonnet'],
              ['Permission Scope', 'Read + Flag (no write)'],
            ] as [string, string][]).map(([label, val]) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: c.textMuted, fontWeight: 600 }}>{label}</span>
                <span style={{ fontWeight: 700, color: c.text }}>{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Run History */}
      <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 14, padding: 24, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, color: c.text, textTransform: 'uppercase', letterSpacing: '.5px' }}>
            <Clock size={16} style={{ marginRight: 8, verticalAlign: 'middle' }} />
            Run History
          </h3>
          <span style={{ fontSize: 12, color: c.textDim }}>{runs.length} runs</span>
        </div>

        {runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: c.textDim }}>
            <Bot size={40} style={{ marginBottom: 12, opacity: 0.3 }} />
            <div style={{ fontWeight: 600, fontSize: 14 }}>No runs yet</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>{isComingSoon ? 'This agent is not yet available.' : 'Click "Run Agent" to execute.'}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {runs.map((run) => (
              <div
                key={run.id}
                onClick={() => agent.id === 'vms-reconciliation' ? setSelectedRunId(selectedRunId === run.id ? null : run.id) : undefined}
                style={{ border: `1.5px solid ${selectedRunId === run.id ? agent.color : c.cardBorder}`, borderRadius: 12, padding: '14px 16px', transition: 'all .15s', cursor: agent.id === 'vms-reconciliation' ? 'pointer' : 'default', background: c.panelBg }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {statusIcon(run.status)}
                    <span style={{ fontWeight: 700, fontSize: 13, color: c.text }}>{run.id}</span>
                    <span style={{ fontSize: 12, color: c.textDim }}>{run.timestamp}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <span style={{ fontSize: 12, color: c.textMuted }}><strong>{run.recordsProcessed.toLocaleString()}</strong> processed</span>
                    <span style={{ fontSize: 12, color: run.flagged > 0 ? '#f59e0b' : '#10b981', fontWeight: 700 }}>{run.flagged} flagged</span>
                    <span style={{ fontSize: 11, color: c.textDim }}>{run.duration}</span>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: c.textMuted, lineHeight: 1.5 }}>{run.summary}</div>

                {/* VMS Match Review panel — inline below the run row */}
                {agent.id === 'vms-reconciliation' && selectedRunId === run.id && (
                  <div style={{ marginTop: 16, borderTop: `1px solid ${c.cardBorder}`, paddingTop: 16 }}>
                    <VMSMatchReview
                      runId={run.id}
                      matches={vmsMatches}
                      onApprove={handleApprove}
                      onReject={handleReject}
                      onDismiss={handleDismiss}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Bot({ size, style }: { size: number; style?: React.CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={style}><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>;
}
