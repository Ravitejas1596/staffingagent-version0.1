import { useState, useEffect, useCallback } from 'react';
import VMSMatchReview from '../VMSMatchReview/VMSMatchReview';
import type { VMSMatchRecord } from '../VMSMatchReview/VMSMatchReview';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';

const API_BASE = import.meta.env.VITE_API_URL ?? 'https://api.staffingagent.ai';

interface VMSReconLiveProps {
  onBack: () => void;
}

export default function VMSReconLive({ onBack }: VMSReconLiveProps) {
  const { user } = useAuth();
  const tenantId = user?.tenantId ?? '';
  const [matches, setMatches] = useState<VMSMatchRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchMatches = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/vms/matches?tenant_id=${tenantId}&limit=500`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();
      setMatches(data.matches ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load matches');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { fetchMatches(); }, [fetchMatches]);

  const handleApprove = async (id: string) => {
    await fetch(`${API_BASE}/vms/matches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'approved' }),
    });
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'approved' as const } : m));
  };

  const handleReject = async (id: string, notes: string) => {
    await fetch(`${API_BASE}/vms/matches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'rejected', review_notes: notes }),
    });
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'rejected' as const, review_notes: notes } : m));
  };

  const handleRunAgent = async () => {
    setRunning(true);
    setRunResult(null);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/vms/run-matching?tenant_id=${tenantId}`, { method: 'POST' });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();
      setRunResult(data.message ?? 'Done');
      await fetchMatches();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent run failed');
    } finally {
      setRunning(false);
    }
  };

  const handleDismiss = async (id: string) => {
    await fetch(`${API_BASE}/vms/matches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'dismissed' }),
    });
    setMatches(prev => prev.map(m => m.id === id ? { ...m, status: 'dismissed' as const } : m));
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
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
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 6, background: '#dcfce7', color: '#15803d', textTransform: 'uppercase' }}>Live Data</span>
            </div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>
              {loading ? 'Loading…' : error ? error : `${total} match records from database`}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={fetchMatches}
            disabled={loading || running}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: '#fff', color: '#475569', border: '1.5px solid #e2e8f0',
              borderRadius: 10, padding: '10px 18px', fontSize: 14, fontWeight: 700, cursor: 'pointer',
              opacity: loading ? 0.7 : 1,
            }}
          >
            <RefreshCw size={16} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Refresh
          </button>
          <button
            onClick={handleRunAgent}
            disabled={loading || running}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: '#ea580c', color: '#fff', border: 'none',
              borderRadius: 10, padding: '10px 20px', fontSize: 14, fontWeight: 700, cursor: 'pointer',
              opacity: running ? 0.7 : 1,
            }}
          >
            <RefreshCw size={16} style={{ animation: running ? 'spin 1s linear infinite' : 'none' }} />
            {running ? 'Running Agent…' : 'Run Matching Agent'}
          </button>
        </div>
      </div>

      {runResult && (
        <div style={{ background: '#dcfce7', border: '1.5px solid #86efac', borderRadius: 10, padding: '14px 20px', color: '#15803d', marginBottom: 20, fontSize: 14, fontWeight: 600 }}>
          {runResult}
        </div>
      )}

      {error && (
        <div style={{ background: '#fee2e2', border: '1.5px solid #fca5a5', borderRadius: 10, padding: '14px 20px', color: '#dc2626', marginBottom: 20, fontSize: 14 }}>
          {error}
        </div>
      )}

      {!loading && !error && matches.length === 0 && (
        <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8', fontSize: 15 }}>
          No VMS match records found. Run the matching agent to generate matches.
        </div>
      )}

      {!loading && matches.length > 0 && (
        <VMSMatchReview
          matches={matches}
          onApprove={handleApprove}
          onReject={handleReject}
          onDismiss={handleDismiss}
        />
      )}
    </div>
  );
}
