import { useState, useMemo, useCallback, useEffect } from 'react';
import { ArrowLeft, ChevronDown } from 'lucide-react';
import type { TimesheetRecord } from '../../types';
import { useUI } from '../../context/UIContext';
import { getTimeOpsRecords, updateTimeOpsRecord, ApiError } from '../../api/client';
import { TableSkeleton } from '../Skeleton/Skeleton';

interface TimeOpsProps {
  onBack: () => void;
}

type FilterType = 'all' | 'excluded' | 'not-excluded';

export default function TimeOps({ onBack }: TimeOpsProps) {
  const { c } = useUI();
  const [records, setRecords] = useState<TimesheetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [periodEnd, setPeriodEnd] = useState<string | undefined>();
  const [filter, setFilter] = useState<FilterType>('all');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showMassActions, setShowMassActions] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getTimeOpsRecords().then((res) => {
      if (cancelled) return;
      setRecords(res.records);
      setPeriodEnd(res.period_end);
      setLoading(false);
    }).catch((err) => {
      if (cancelled) return;
      const message = err instanceof ApiError ? err.message : 'Unable to load timesheet records.';
      console.warn('[TimeOps] API request failed:', err);
      setLoadError(message);
      setRecords([]);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    if (filter === 'excluded') return records.filter((r) => r.excluded);
    if (filter === 'not-excluded') return records.filter((r) => !r.excluded);
    return records;
  }, [filter, records]);

  const totalAll = records.length;
  const totalExcluded = records.filter((r) => r.excluded).length;
  const totalNotExcluded = totalAll - totalExcluded;

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === filtered.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map((r) => r.id)));
  };

  const onExcludedChange = useCallback((id: number, value: string) => {
    const now = new Date();
    const ts = `${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}/${now.getFullYear()} ${now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
    setRecords((prev) => prev.map((r) => {
      if (r.id !== id) return r;
      const excluded = value === 'Yes';
      // Persist to API
      updateTimeOpsRecord(r.placementId, { is_excluded: excluded }, periodEnd).catch(console.warn);
      if (excluded) {
        return { ...r, excluded: true, excludedBy: 'Current User', excludedDate: ts };
      }
      return { ...r, excluded: false, excludedBy: '—', excludedDate: '—' };
    }));
  }, [periodEnd]);

  const onCommentChange = useCallback((id: number, value: string) => {
    setRecords((prev) => prev.map((r) => r.id === id ? { ...r, comments: value } : r));
  }, []);

  const onCommentBlur = useCallback((id: number, value: string) => {
    const r = records.find((rec) => rec.id === id);
    if (r) {
      updateTimeOpsRecord(r.placementId, { comments: value }, periodEnd).catch(console.warn);
    }
  }, [records, periodEnd]);

  const handleMassAction = (action: string) => {
    const ids = Array.from(selectedIds);
    const now = new Date();
    const ts = `${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}/${now.getFullYear()} ${now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;

    if (action === 'reminders') {
      setRecords((prev) => prev.map((r) => {
        if (!ids.includes(r.id)) return r;
        updateTimeOpsRecord(r.placementId, { send_reminder: true }, periodEnd).catch(console.warn);
        return { ...r, lastReminderSent: ts.split(' ')[0] };
      }));
      alert(`Timesheet reminders sent to ${ids.length} candidate(s).`);
    } else if (action === 'exclude') {
      setRecords((prev) => prev.map((r) => {
        if (!ids.includes(r.id)) return r;
        updateTimeOpsRecord(r.placementId, { is_excluded: true }, periodEnd).catch(console.warn);
        return { ...r, excluded: true, excludedBy: 'Current User', excludedDate: ts };
      }));
      alert(`${ids.length} timesheet(s) excluded from missing.`);
    } else if (action === 'export') {
      alert(`Exporting ${ids.length} record(s) to Excel...`);
    }
    setSelectedIds(new Set());
    setShowMassActions(false);
  };

  const tiles: { key: FilterType; label: string; count: number; color: string }[] = [
    { key: 'all', label: 'Missing Timesheets', count: totalAll, color: '#2563eb' },
    { key: 'excluded', label: 'Timesheets Excluded from Missing', count: totalExcluded, color: '#16a34a' },
    { key: 'not-excluded', label: 'Missing Timesheets After Exclusions', count: totalNotExcluded, color: '#dc2626' },
  ];

  const excludedSelectStyle = (val: boolean): React.CSSProperties => ({
    padding: '4px 8px', borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: 'pointer',
    border: `1.5px solid ${val ? '#16a34a' : '#dc2626'}`,
    background: val ? '#f0fdf4' : '#fef2f2',
    color: val ? '#16a34a' : '#dc2626',
  });

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Dashboard
      </button>

      <div className="sub-header">
        <h1>TimeOps Dashboard</h1>
        <p>Track and Manage Missing Timesheets</p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
        {tiles.map((t) => (
          <div
            key={t.key}
            onClick={() => { setFilter(t.key); setSelectedIds(new Set()); }}
            style={{
              flex: 1, background: c.cardBg, border: `1.5px solid ${filter === t.key ? t.color : c.cardBorder}`,
              borderRadius: 14, padding: '16px 20px', cursor: 'pointer',
              boxShadow: filter === t.key ? `0 0 0 3px ${t.color}22` : '0 2px 10px rgba(2,6,23,.06)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              transition: 'all .2s', position: 'relative',
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 800, color: c.text }}>{t.label}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 20, fontWeight: 800, color: t.color }}>{t.count}</span>
              {filter === t.key && (
                <span style={{ fontSize: 9, fontWeight: 800, padding: '2px 6px', borderRadius: 6, background: t.color, color: '#fff', textTransform: 'uppercase', letterSpacing: '.5px' }}>Active</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="search-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontWeight: 700, fontSize: '1.1rem' }}>
            {filter === 'all' ? 'All Missing Timesheets' : filter === 'excluded' ? 'Excluded Timesheets' : 'Actionable Missing Timesheets'}
            <span style={{ marginLeft: 8, fontSize: 14, color: '#6b7280' }}>({filtered.length})</span>
            {loading && <span style={{ marginLeft: 8, fontSize: 12, color: c.textMuted }}>Loading…</span>}
          </h3>

          <div className="mass-actions-container">
            <button
              className="mass-actions-btn"
              onClick={() => setShowMassActions(!showMassActions)}
              disabled={selectedIds.size === 0}
              style={{ opacity: selectedIds.size === 0 ? 0.5 : 1 }}
            >
              Mass Actions ({selectedIds.size})
              <ChevronDown size={16} />
            </button>
            {showMassActions && selectedIds.size > 0 && (
              <div className="mass-actions-dropdown show">
                <div className="mass-action-item" onClick={() => handleMassAction('reminders')}>
                  Send Timesheet Reminders to {selectedIds.size}
                </div>
                <div className="mass-action-item" onClick={() => handleMassAction('exclude')}>
                  Exclude {selectedIds.size} from Missing Timesheet for Pay Period
                </div>
                <div className="mass-action-item" onClick={() => handleMassAction('export')}>
                  Export {selectedIds.size} to Excel
                </div>
              </div>
            )}
          </div>
        </div>

        {loadError && (
          <div
            role="alert"
            style={{
              marginBottom: 12,
              padding: '10px 14px',
              border: '1.5px solid #fca5a5',
              background: '#fef2f2',
              color: '#991b1b',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {loadError}
          </div>
        )}

        {loading ? (
          <div className="data-table-container" style={{ padding: 16 }}>
            <TableSkeleton rows={8} columns={12} />
          </div>
        ) : !loadError && records.length === 0 ? (
          <div
            style={{
              padding: '24px 16px',
              border: '1px dashed #cbd5e1',
              borderRadius: 10,
              textAlign: 'center',
              color: c.textMuted,
              fontSize: 13,
            }}
          >
            No missing timesheets for this pay period.
          </div>
        ) : (
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th><input type="checkbox" checked={selectedIds.size === filtered.length && filtered.length > 0} onChange={toggleAll} /></th>
                <th>Timesheet ID</th>
                <th>Excluded?</th>
                <th>Last Reminder Sent</th>
                <th>Placement ID</th>
                <th>Customer Name</th>
                <th>Job Title</th>
                <th>Candidate Name</th>
                <th>Placement Start</th>
                <th>Placement End</th>
                <th>Period End Date</th>
                <th>Candidate Email</th>
                <th>Comments</th>
                <th>Excluded By</th>
                <th>Excluded Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td><input type="checkbox" checked={selectedIds.has(r.id)} onChange={() => toggleSelect(r.id)} /></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, fontWeight: 600, textDecoration: 'none' }}>{r.timesheetId}</a></td>
                  <td>
                    <select
                      value={r.excluded ? 'Yes' : 'No'}
                      onChange={(e) => onExcludedChange(r.id, e.target.value)}
                      style={excludedSelectStyle(r.excluded)}
                    >
                      <option value="No">No</option>
                      <option value="Yes">Yes</option>
                    </select>
                  </td>
                  <td>{r.lastReminderSent}</td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, textDecoration: 'none' }}>{r.placementId}</a></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, textDecoration: 'none' }}>{r.customerName}</a></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, textDecoration: 'none' }}>{r.jobTitle}</a></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, fontWeight: 600, textDecoration: 'none' }}>{r.candidateName}</a></td>
                  <td>{r.placementStart}</td>
                  <td>{r.placementEnd}</td>
                  <td>{r.periodEndDate}</td>
                  <td>{r.candidateEmail}</td>
                  <td>
                    <input
                      type="text"
                      value={r.comments}
                      onChange={(e) => onCommentChange(r.id, e.target.value)}
                      onBlur={(e) => onCommentBlur(r.id, e.target.value)}
                      placeholder="Add comment..."
                      style={{ border: `1px solid ${c.inputBorder}`, borderRadius: 6, padding: '4px 8px', fontSize: 12, width: '100%', minWidth: 120, background: c.inputBg, color: c.text }}
                    />
                  </td>
                  <td style={{ color: r.excludedBy === '—' ? '#94a3b8' : '#1f2937', fontWeight: r.excludedBy === '—' ? 400 : 600 }}>{r.excludedBy}</td>
                  <td style={{ color: r.excludedDate === '—' ? '#94a3b8' : '#1f2937', fontSize: 12 }}>{r.excludedDate}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </div>
    </div>
  );
}
