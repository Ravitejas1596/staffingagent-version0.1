import { useState } from 'react';
import VMSMatchReview from '../VMSMatchReview/VMSMatchReview';
import type { VMSMatchRecord } from '../VMSMatchReview/VMSMatchReview';
import { ArrowLeft, RefreshCw } from 'lucide-react';

const MOCK_MATCHES: VMSMatchRecord[] = [
  {
    id: '1', vms_record_id: 'r1', placement_id: 'p-245', bullhorn_id: 12045,
    confidence: 0.98, match_method: 'exact', name_similarity: 1.0,
    rate_delta: 0, hours_delta: 0, financial_impact: 0, llm_explanation: null,
    status: 'pending', review_notes: null,
    candidate_name: 'Yuri Zabara', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0,
    bill_rate: 1430.00, vms_platform: 'Beeline', placement_ref: 'P-245',
  },
  {
    id: '2', vms_record_id: 'r2', placement_id: 'p-071', bullhorn_id: 11203,
    confidence: 0.82, match_method: 'fuzzy', name_similarity: 0.87,
    rate_delta: 12.50, hours_delta: 0, financial_impact: 500, llm_explanation: 'VMS name "R. Labibi" matched to Rahman Labibi via first-initial fuzzy strategy. Rate variance of $12.50/h detected.',
    status: 'pending', review_notes: null,
    candidate_name: 'R. Labibi', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0,
    bill_rate: 1440.00, vms_platform: 'Beeline', placement_ref: 'P-071',
  },
  {
    id: '3', vms_record_id: 'r3', placement_id: null, bullhorn_id: null,
    confidence: 0, match_method: 'unmatched', name_similarity: null,
    rate_delta: null, hours_delta: null, financial_impact: null, llm_explanation: 'Could not find a placement matching "SIDDIQUE FARRUKH" within acceptable threshold.',
    status: 'pending', review_notes: null,
    candidate_name: 'SIDDIQUE FARRUKH', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0,
    bill_rate: 1315.00, vms_platform: 'Beeline', placement_ref: 'P-230',
  },
  {
    id: '4', vms_record_id: 'r4', placement_id: 'p-148', bullhorn_id: 10987,
    confidence: 0.96, match_method: 'alias', name_similarity: 0.95,
    rate_delta: 0, hours_delta: 2.5, financial_impact: 3225, llm_explanation: null,
    status: 'pending', review_notes: null,
    candidate_name: 'van Niekerk, Justin', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 2.5,
    bill_rate: 1290.00, vms_platform: 'Beeline', placement_ref: 'P-148',
  },
  {
    id: '5', vms_record_id: 'r5', placement_id: 'p-092', bullhorn_id: 10456,
    confidence: 0.91, match_method: 'llm', name_similarity: 0.78,
    rate_delta: -5.00, hours_delta: 0, financial_impact: -187.5, llm_explanation: 'VMS shows "joy groves" (all lowercase). Matched to JOY GROVES via case-insensitive normalization. Minor rate discrepancy of $5/h.',
    status: 'pending', review_notes: null,
    candidate_name: 'joy groves', week_ending: '2026-04-04', regular_hours: 37.5, ot_hours: 0,
    bill_rate: 1185.00, vms_platform: 'Beeline', placement_ref: 'P-092',
  },
  {
    id: '6', vms_record_id: 'r6', placement_id: 'p-207', bullhorn_id: 10234,
    confidence: 0.99, match_method: 'exact', name_similarity: 1.0,
    rate_delta: 0, hours_delta: 0, financial_impact: 0, llm_explanation: null,
    status: 'approved', review_notes: null,
    candidate_name: 'Mladen Jaksic', week_ending: '2026-03-28', regular_hours: 40, ot_hours: 0,
    bill_rate: 1150.00, vms_platform: 'Beeline', placement_ref: 'P-207',
  },
  {
    id: '7', vms_record_id: 'r7', placement_id: 'p-458', bullhorn_id: 10891,
    confidence: 0.74, match_method: 'fuzzy', name_similarity: 0.81,
    rate_delta: 110.00, hours_delta: 0, financial_impact: 4400, llm_explanation: 'VMS name "Alex Nojkov" matched to Aleksandar Nojkov. Significant rate delta of $110/h — possible wrong rate tier applied.',
    status: 'pending', review_notes: null,
    candidate_name: 'Alex Nojkov', week_ending: '2026-04-04', regular_hours: 40, ot_hours: 0,
    bill_rate: 1210.00, vms_platform: 'Beeline', placement_ref: 'P-458',
  },
];

interface VMSReconProps {
  onBack: () => void;
  onLiveData: () => void;
}

export default function VMSRecon({ onBack, onLiveData }: VMSReconProps) {
  const [matches, setMatches] = useState<VMSMatchRecord[]>(MOCK_MATCHES);
  const [isRunning, setIsRunning] = useState(false);
  const [lastRun] = useState(new Date());

  const handleApprove = (id: string) => {
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'approved' as const } : m));
  };

  const handleReject = (id: string, notes: string) => {
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'rejected' as const, review_notes: notes } : m));
  };

  const handleDismiss = (id: string) => {
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'dismissed' as const } : m));
  };

  const handleRun = () => {
    setIsRunning(true);
    setTimeout(() => setIsRunning(false), 1500);
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button
            onClick={onBack}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: '6px 0' }}
          >
            <ArrowLeft size={16} /> Back
          </button>
          <div style={{ width: 1, height: 24, background: '#e2e8f0' }} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 22 }}>🔄</span>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#0f172a' }}>VMS Reconciliation</h1>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#fef3c7', color: '#92400e', textTransform: 'uppercase' }}>Beta</span>
              <button onClick={onLiveData} style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#eff6ff', color: '#2563eb', textTransform: 'uppercase', border: '1.5px solid #bfdbfe', cursor: 'pointer' }}>Live Data →</button>
            </div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>
              Last run: {lastRun.toLocaleString()} · Beeline upload vms_export_2026-04-08.csv · Sample data
            </div>
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={isRunning}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: '#ea580c', color: '#fff', border: 'none',
            borderRadius: 10, padding: '10px 20px', fontSize: 14, fontWeight: 700, cursor: 'pointer',
            opacity: isRunning ? 0.7 : 1,
          }}
        >
          <RefreshCw size={16} style={{ animation: isRunning ? 'spin 1s linear infinite' : 'none' }} />
          {isRunning ? 'Running Agent…' : 'Run Matching Agent'}
        </button>
      </div>

      <VMSMatchReview
        matches={matches}
        onApprove={handleApprove}
        onReject={handleReject}
        onDismiss={handleDismiss}
      />
    </div>
  );
}
