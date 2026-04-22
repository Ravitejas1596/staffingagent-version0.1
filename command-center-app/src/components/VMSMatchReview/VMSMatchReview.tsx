import { useState } from 'react';
import {
  CheckCircle2, XCircle, MinusCircle, ChevronDown, ChevronUp,
  Zap, Search, ArrowRight,
} from 'lucide-react';

export interface VMSMatchRecord {
  id: string;
  vms_record_id: string;
  placement_id: string | null;
  bullhorn_id: number | null;
  confidence: number | null;
  match_method: 'alias' | 'exact' | 'fuzzy' | 'llm' | 'manual' | 'unmatched';
  name_similarity: number | null;
  rate_delta: number | null;
  hours_delta: number | null;
  financial_impact: number | null;
  llm_explanation: string | null;
  status: 'pending' | 'approved' | 'rejected' | 'dismissed' | 'corrected';
  review_notes: string | null;
  // VMS record fields (joined)
  candidate_name?: string;
  week_ending?: string;
  regular_hours?: number;
  ot_hours?: number;
  bill_rate?: number;
  vms_platform?: string;
  placement_ref?: string;
}

interface VMSMatchReviewProps {
  runId: string;
  matches: VMSMatchRecord[];
  onApprove: (matchId: string) => void;
  onReject: (matchId: string, notes: string) => void;
  onDismiss: (matchId: string) => void;
}

const METHOD_LABELS: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  alias:     { label: 'Learned',  color: '#7c3aed', icon: <Zap size={12} /> },
  exact:     { label: 'Exact',    color: '#059669', icon: <CheckCircle2 size={12} /> },
  fuzzy:     { label: 'Fuzzy',    color: '#2563eb', icon: <Search size={12} /> },
  llm:       { label: 'AI',       color: '#d97706', icon: <span style={{ fontSize: 11 }}>✦</span> },
  manual:    { label: 'Manual',   color: '#64748b', icon: <CheckCircle2 size={12} /> },
  unmatched: { label: 'No Match', color: '#dc2626', icon: <XCircle size={12} /> },
};

function confidenceTier(conf: number | null): { bg: string; text: string; label: string } {
  if (conf === null || conf === 0) return { bg: '#fee2e2', text: '#dc2626', label: 'Unmatched' };
  if (conf >= 0.95) return { bg: '#dcfce7', text: '#15803d', label: 'Auto' };
  if (conf >= 0.70) return { bg: '#fef3c7', text: '#b45309', label: 'Review' };
  return { bg: '#fee2e2', text: '#dc2626', label: 'Low' };
}

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  const tier = confidenceTier(confidence);
  return (
    <span style={{
      background: tier.bg, color: tier.text,
      fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
      textTransform: 'uppercase', letterSpacing: '.3px',
    }}>
      {tier.label} {confidence !== null && confidence > 0 ? `${Math.round(confidence * 100)}%` : ''}
    </span>
  );
}

function MethodBadge({ method }: { method: string }) {
  const m = METHOD_LABELS[method] ?? METHOD_LABELS.unmatched;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: `${m.color}18`, color: m.color,
      fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 6,
    }}>
      {m.icon} {m.label}
    </span>
  );
}

function DeltaCell({ value, suffix = '' }: { value: number | null; suffix?: string }) {
  if (value === null) return <span style={{ color: '#94a3b8' }}>—</span>;
  const abs = Math.abs(value);
  const color = abs < 0.01 ? '#10b981' : abs < 5 ? '#f59e0b' : '#dc2626';
  return (
    <span style={{ color, fontWeight: 700, fontSize: 13 }}>
      {value > 0 ? '+' : ''}{value.toFixed(2)}{suffix}
    </span>
  );
}

function MatchRow({ match, onApprove, onReject, onDismiss }: {
  match: VMSMatchRecord;
  onApprove: (id: string) => void;
  onReject: (id: string, notes: string) => void;
  onDismiss: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [rejectMode, setRejectMode] = useState(false);
  const [notes, setNotes] = useState('');
  const isPending = match.status === 'pending';

  const statusIcon = () => {
    if (match.status === 'approved' || match.status === 'corrected') return <CheckCircle2 size={16} style={{ color: '#10b981' }} />;
    if (match.status === 'rejected') return <XCircle size={16} style={{ color: '#dc2626' }} />;
    if (match.status === 'dismissed') return <MinusCircle size={16} style={{ color: '#94a3b8' }} />;
    return null;
  };

  return (
    <div style={{
      border: `1.5px solid ${isPending && (match.confidence ?? 0) < 0.95 ? '#fde68a' : '#e2e8f0'}`,
      borderRadius: 12, overflow: 'hidden',
      opacity: match.status !== 'pending' ? 0.75 : 1,
    }}>
      {/* Row summary */}
      <div
        style={{ display: 'grid', gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1fr 1fr auto', gap: 12, padding: '12px 16px', alignItems: 'center', cursor: 'pointer', background: '#fff' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {statusIcon()}
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{match.candidate_name ?? '—'}</div>
            <div style={{ fontSize: 11, color: '#94a3b8' }}>{match.vms_platform} · {match.placement_ref}</div>
          </div>
        </div>
        <div style={{ fontSize: 13, color: '#475569' }}>{match.week_ending ?? '—'}</div>
        <div>
          <MethodBadge method={match.match_method} />
        </div>
        <div>
          <ConfidenceBadge confidence={match.confidence} />
        </div>
        <div>
          <DeltaCell value={match.rate_delta} suffix=" $/h" />
        </div>
        <div style={{ fontSize: 12, fontWeight: 600, color: (match.financial_impact ?? 0) > 50 ? '#dc2626' : '#64748b' }}>
          {match.financial_impact != null ? `$${match.financial_impact.toFixed(0)}` : '—'}
        </div>
        <div>{expanded ? <ChevronUp size={16} style={{ color: '#94a3b8' }} /> : <ChevronDown size={16} style={{ color: '#94a3b8' }} />}</div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ borderTop: '1px solid #f1f5f9', background: '#f8fafc', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 16 }}>
            {/* VMS side */}
            <div style={{ background: '#fff', borderRadius: 10, padding: 16, border: '1.5px solid #e2e8f0' }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>VMS Record</div>
              <Row label="Name" value={match.candidate_name} />
              <Row label="Week Ending" value={match.week_ending} />
              <Row label="Regular Hours" value={match.regular_hours?.toString()} />
              <Row label="OT Hours" value={match.ot_hours?.toString()} />
              <Row label="Bill Rate" value={match.bill_rate != null ? `$${match.bill_rate}` : undefined} />
              <Row label="Platform" value={match.vms_platform} />
              <Row label="Placement Ref" value={match.placement_ref} />
            </div>

            {/* ATS side */}
            <div style={{ background: '#fff', borderRadius: 10, padding: 16, border: `1.5px solid ${match.placement_id ? '#e2e8f0' : '#fee2e2'}` }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>
                Bullhorn Placement {match.match_method === 'unmatched' ? <span style={{ color: '#dc2626' }}>(No Match)</span> : ''}
              </div>
              {match.match_method === 'unmatched' || !match.placement_id ? (
                <div style={{ color: '#dc2626', fontSize: 13, fontWeight: 600, padding: '8px 0' }}>
                  No matching placement found. Approve to skip or reject to manually link.
                </div>
              ) : (
                <>
                  <Row label="Bullhorn ID" value={match.bullhorn_id?.toString()} />
                  <Row label="Similarity" value={match.name_similarity != null ? `${Math.round(match.name_similarity * 100)}%` : undefined} highlight={match.name_similarity != null && match.name_similarity < 0.90} />
                  <Row label="Rate Delta" value={match.rate_delta != null ? `${match.rate_delta > 0 ? '+' : ''}$${match.rate_delta.toFixed(2)}/h` : undefined} highlight={(Math.abs(match.rate_delta ?? 0)) > 5} />
                  <Row label="$ Impact" value={match.financial_impact != null ? `$${match.financial_impact.toFixed(2)}` : undefined} highlight={(match.financial_impact ?? 0) > 100} />
                </>
              )}
              {match.llm_explanation && (
                <div style={{ marginTop: 10, padding: '8px 10px', background: '#fef3c7', borderRadius: 8, fontSize: 12, color: '#92400e', lineHeight: 1.5 }}>
                  <span style={{ fontWeight: 700 }}>AI: </span>{match.llm_explanation}
                </div>
              )}
            </div>
          </div>

          {/* Action buttons */}
          {isPending && !rejectMode && (
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => onApprove(match.id)} style={btnStyle('#10b981')}>
                <CheckCircle2 size={14} /> Approve Match
              </button>
              <button onClick={() => setRejectMode(true)} style={btnStyle('#dc2626', true)}>
                <XCircle size={14} /> Reject
              </button>
              <button onClick={() => onDismiss(match.id)} style={btnStyle('#64748b', true)}>
                <MinusCircle size={14} /> Dismiss
              </button>
            </div>
          )}

          {isPending && rejectMode && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <textarea
                placeholder="Optional: describe the correct match or reason for rejection..."
                value={notes}
                onChange={e => setNotes(e.target.value)}
                style={{ width: '100%', minHeight: 64, borderRadius: 8, border: '1.5px solid #e2e8f0', padding: '8px 12px', fontSize: 13, resize: 'vertical', boxSizing: 'border-box' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => { onReject(match.id, notes); setRejectMode(false); }} style={btnStyle('#dc2626')}>
                  <ArrowRight size={14} /> Confirm Rejection
                </button>
                <button onClick={() => setRejectMode(false)} style={btnStyle('#94a3b8', true)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value, highlight = false }: { label: string; value?: string; highlight?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
      <span style={{ color: '#64748b', fontWeight: 600 }}>{label}</span>
      <span style={{ fontWeight: 700, color: highlight ? '#dc2626' : '#0f172a' }}>{value ?? '—'}</span>
    </div>
  );
}

function btnStyle(color: string, outline = false): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: outline ? 'transparent' : color,
    color: outline ? color : '#fff',
    border: `1.5px solid ${color}`,
    borderRadius: 8, padding: '7px 16px', fontSize: 13, fontWeight: 700,
    cursor: 'pointer',
  };
}

export default function VMSMatchReview({ matches, onApprove, onReject, onDismiss }: Omit<VMSMatchReviewProps, 'runId'> & { runId?: string }) {
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected' | 'unmatched'>('pending');

  const counts = {
    all: matches.length,
    pending: matches.filter(m => m.status === 'pending').length,
    approved: matches.filter(m => m.status === 'approved' || m.status === 'corrected').length,
    rejected: matches.filter(m => m.status === 'rejected').length,
    unmatched: matches.filter(m => m.match_method === 'unmatched').length,
  };

  const visible = matches.filter(m => {
    if (filter === 'all') return true;
    if (filter === 'unmatched') return m.match_method === 'unmatched';
    return m.status === filter;
  });

  // Sort: low confidence first, then unmatched
  const sorted = [...visible].sort((a, b) => {
    if (a.match_method === 'unmatched' && b.match_method !== 'unmatched') return 1;
    if (b.match_method === 'unmatched' && a.match_method !== 'unmatched') return -1;
    return (a.confidence ?? 0) - (b.confidence ?? 0);
  });

  const filterBtn = (key: typeof filter, label: string, count: number) => (
    <button
      key={key}
      onClick={() => setFilter(key)}
      style={{
        padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 700,
        border: '1.5px solid',
        borderColor: filter === key ? '#2563eb' : '#e2e8f0',
        background: filter === key ? '#eff6ff' : '#fff',
        color: filter === key ? '#2563eb' : '#64748b',
        cursor: 'pointer',
      }}
    >
      {label} <span style={{ fontWeight: 400 }}>({count})</span>
    </button>
  );

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Records', value: counts.all, color: '#2563eb' },
          { label: 'Auto-Accepted', value: matches.filter(m => (m.confidence ?? 0) >= 0.95 && m.status === 'approved').length, color: '#10b981' },
          { label: 'Needs Review', value: counts.pending, color: '#f59e0b' },
          { label: 'Unmatched', value: counts.unmatched, color: '#dc2626' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: '#fff', borderRadius: 12, padding: '16px 20px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', borderTop: `3px solid ${color}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {filterBtn('pending', 'Needs Review', counts.pending)}
        {filterBtn('unmatched', 'Unmatched', counts.unmatched)}
        {filterBtn('approved', 'Approved', counts.approved)}
        {filterBtn('rejected', 'Rejected', counts.rejected)}
        {filterBtn('all', 'All', counts.all)}
      </div>

      {/* Column headers */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1fr 1fr auto', gap: 12, padding: '8px 16px', fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '.5px' }}>
        <div>Candidate</div>
        <div>Week Ending</div>
        <div>Method</div>
        <div>Confidence</div>
        <div>Rate Δ</div>
        <div>$ Impact</div>
        <div style={{ width: 16 }} />
      </div>

      {/* Match rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sorted.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 14 }}>
            No matches in this filter.
          </div>
        ) : (
          sorted.map(match => (
            <MatchRow
              key={match.id}
              match={match}
              onApprove={onApprove}
              onReject={onReject}
              onDismiss={onDismiss}
            />
          ))
        )}
      </div>
    </div>
  );
}
