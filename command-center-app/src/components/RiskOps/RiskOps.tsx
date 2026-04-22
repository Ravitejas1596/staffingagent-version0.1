import { useState, useMemo, useCallback, useEffect } from 'react';
import { ArrowLeft, ChevronDown } from 'lucide-react';
import type { RiskRecord, RiskCategory } from '../../types';
import { useUI } from '../../context/UIContext';
import { getRiskOpsRecords, getRiskOpsCategories, updateRiskOpsRecord, ApiError } from '../../api/client';
import { TableSkeleton, RiskCategoriesSkeleton } from '../Skeleton/Skeleton';

interface RiskOpsProps {
  onBack: () => void;
  initialFilter: string | null;
}

type ResolvedFilter = 'All' | 'Open' | 'Pending' | 'Resolved';

export default function RiskOps({ onBack, initialFilter }: RiskOpsProps) {
  const { c } = useUI();
  const parsedCat = initialFilter?.includes(':') ? initialFilter.split(':')[0] : (initialFilter || 'all');
  const parsedError = initialFilter?.includes(':') ? initialFilter.split(':')[1] : null;

  const [records, setRecords] = useState<RiskRecord[]>([]);
  const [categories, setCategories] = useState<RiskCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>(parsedCat);
  const [errorFilter, setErrorFilter] = useState<string | null>(parsedError);
  const [resolvedFilter, setResolvedFilter] = useState<ResolvedFilter>('All');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showMassActions, setShowMassActions] = useState(false);
  const [expandedTiles, setExpandedTiles] = useState<Set<string>>(new Set(parsedError ? [parsedCat] : []));

  useEffect(() => {
    let cancelled = false;
    Promise.all([getRiskOpsRecords(), getRiskOpsCategories()]).then(([recRes, catRes]) => {
      if (cancelled) return;
      setRecords(recRes.records);
      setCategories(catRes.categories);
      setLoading(false);
    }).catch((err) => {
      if (cancelled) return;
      const message = err instanceof ApiError ? err.message : 'Unable to load risk alerts.';
      console.warn('[RiskOps] API request failed:', err);
      setLoadError(message);
      setRecords([]);
      setCategories([]);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  // Record key helper — each record from the API has a unique timesheetId that doubles as the key prefix
  const getRecordKey = (r: RiskRecord) => `${r.category}:${r.timesheetId}`;

  const riskOpsCats = categories.filter((cat) => cat.id !== 'timesheet');

  const filtered = useMemo(() => {
    let f = records;
    if (categoryFilter !== 'all') {
      f = f.filter((r) => r.category === categoryFilter);
    }
    if (errorFilter) {
      const cat = riskOpsCats.find((cat) => cat.id === categoryFilter);
      const sub = cat?.subCategories?.find((s) => s.errorType === errorFilter);
      if (sub) {
        f = f.filter((r) => r.errorType === sub.label);
      }
    }
    if (resolvedFilter !== 'All') {
      f = f.filter((r) => r.resolvedStatus === resolvedFilter);
    }
    return f;
  }, [categoryFilter, errorFilter, resolvedFilter, records, riskOpsCats]);

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

  const toggleTileExpand = (id: string) => {
    setExpandedTiles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onStatusChange = useCallback((id: number, value: RiskRecord['resolvedStatus']) => {
    const now = new Date();
    const ts = `${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}/${now.getFullYear()} ${now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
    setRecords((prev) => prev.map((r) => {
      if (r.id !== id) return r;
      // Persist to API
      updateRiskOpsRecord(getRecordKey(r), { status: value }).catch(console.warn);
      if (value === 'Open') {
        return { ...r, resolvedStatus: value, resolvedBy: '—', resolvedDate: '—' };
      }
      return { ...r, resolvedStatus: value, resolvedBy: 'Current User', resolvedDate: ts };
    }));
  }, []);

  const onCommentChange = useCallback((id: number, value: string) => {
    setRecords((prev) => prev.map((r) => r.id === id ? { ...r, comments: value } : r));
  }, []);

  const onCommentBlur = useCallback((id: number, value: string) => {
    setRecords((prev) => {
      const r = prev.find((rec) => rec.id === id);
      if (r) {
        updateRiskOpsRecord(getRecordKey(r), { status: r.resolvedStatus, comments: value }).catch(console.warn);
      }
      return prev;
    });
  }, []);

  const handleMassAction = (action: string) => {
    const ids = Array.from(selectedIds);
    const now = new Date();
    const ts = `${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}/${now.getFullYear()} ${now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;

    if (action === 'resolved' || action === 'pending') {
      const status = action === 'resolved' ? 'Resolved' as const : 'Pending' as const;
      setRecords((prev) => prev.map((r) => {
        if (!ids.includes(r.id)) return r;
        updateRiskOpsRecord(getRecordKey(r), { status }).catch(console.warn);
        return { ...r, resolvedStatus: status, resolvedBy: 'Current User', resolvedDate: ts };
      }));
      alert(`${ids.length} record(s) updated to ${status}.`);
    } else if (action === 'comment') {
      const text = prompt(`Enter comment for ${ids.length} record(s):`);
      if (text) {
        setRecords((prev) => prev.map((r) => {
          if (!ids.includes(r.id)) return r;
          updateRiskOpsRecord(getRecordKey(r), { status: r.resolvedStatus, comments: text }).catch(console.warn);
          return { ...r, comments: text };
        }));
      }
    } else if (action === 'export') {
      alert(`Exporting ${ids.length} record(s) to Excel...`);
    }
    setSelectedIds(new Set());
    setShowMassActions(false);
  };

  const totalAlerts = records.length;
  const resolvedStatuses: ResolvedFilter[] = ['All', 'Open', 'Pending', 'Resolved'];
  const resolvedColors: Record<ResolvedFilter, string> = { All: '#2563eb', Open: '#dc2626', Pending: '#d97706', Resolved: '#16a34a' };

  const statusSelectStyle = (status: string): React.CSSProperties => {
    const colors: Record<string, { bg: string; border: string; color: string }> = {
      Open: { bg: '#fef2f2', border: '#fca5a5', color: '#dc2626' },
      Pending: { bg: '#fffbeb', border: '#fcd34d', color: '#d97706' },
      Resolved: { bg: '#f0fdf4', border: '#86efac', color: '#16a34a' },
    };
    const col = colors[status] || colors.Open;
    return { padding: '4px 8px', borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: 'pointer', border: `1.5px solid ${col.border}`, background: col.bg, color: col.color };
  };

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Dashboard
      </button>

      <div className="sub-header">
        <h1>RiskOps Dashboard</h1>
        <p>Identify and Manage Risk in your PayBill Process</p>
      </div>

      {loadError && (
        <div
          role="alert"
          style={{
            marginBottom: 16,
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

      {loading && categories.length === 0 ? <RiskCategoriesSkeleton /> : (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        <div
          className="tile"
          onClick={() => { setCategoryFilter('all'); setErrorFilter(null); setSelectedIds(new Set()); }}
          style={{ borderColor: categoryFilter === 'all' ? '#6d28d9' : undefined, boxShadow: categoryFilter === 'all' ? '0 0 0 3px #6d28d922' : undefined }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="tile-header">All Risk Alerts</span>
            {loading && <span style={{ fontSize: 11, color: c.textMuted }}>Loading...</span>}
            {categoryFilter === 'all' && <span style={{ fontSize: 9, fontWeight: 800, padding: '2px 6px', borderRadius: 6, background: '#6d28d9', color: '#fff', textTransform: 'uppercase' }}>Active</span>}
          </div>
          <span className="tile-value">{totalAlerts}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
          {riskOpsCats.map((cat) => {
            const isActive = categoryFilter === cat.id;
            const isExpanded = expandedTiles.has(cat.id);
            return (
              <div key={cat.id}>
                <div
                  className="tile"
                  onClick={() => {
                    setCategoryFilter(cat.id);
                    setErrorFilter(null);
                    setSelectedIds(new Set());
                    if (cat.subCategories && cat.subCategories.length > 0) toggleTileExpand(cat.id);
                  }}
                  style={{
                    borderColor: isActive ? cat.color : undefined,
                    boxShadow: isActive ? `0 0 0 3px ${cat.color}22` : undefined,
                    borderRadius: isExpanded ? '14px 14px 0 0' : undefined,
                  }}
                >
                  <div>
                    <span className="tile-header">{cat.label}</span>
                    <span className={`severity-badge ${cat.severity}`} style={{ marginLeft: 8 }}>{cat.severity}</span>
                  </div>
                  <span className="tile-value">{cat.count}</span>
                </div>
                {cat.subCategories && isExpanded && (
                  <div style={{ background: c.subBg, border: `1.5px solid ${c.cardBorder}`, borderTop: `1px solid ${c.cardBorder}`, borderRadius: '0 0 14px 14px', padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {cat.subCategories.map((sub) => (
                      <div
                        key={sub.errorType}
                        onClick={(e) => { e.stopPropagation(); setCategoryFilter(cat.id); setErrorFilter(sub.errorType); setSelectedIds(new Set()); }}
                        style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          background: errorFilter === sub.errorType ? c.selectedBg : c.cardBg,
                          border: errorFilter === sub.errorType ? `1.5px solid ${c.selectedBorder}` : `1px solid ${c.cardBorder}`,
                          borderRadius: 8, padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontWeight: 700, transition: 'all .15s',
                        }}
                      >
                        <span style={{ color: c.textMuted }}>{sub.label}</span>
                        <span style={{ color: c.accent, fontWeight: 800 }}>{sub.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* Resolved status filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {resolvedStatuses.map((s) => {
          const isActive = resolvedFilter === s;
          const activeBg = s === 'All' ? c.selectedBg : s === 'Open' ? c.open.bg : s === 'Pending' ? c.pending.bg : c.resolved.bg;
          return (
            <button
              key={s}
              onClick={() => { setResolvedFilter(s); setSelectedIds(new Set()); }}
              style={{
                padding: '6px 16px', borderRadius: 999, fontWeight: 700, fontSize: 13,
                border: `1.5px solid ${isActive ? resolvedColors[s] : c.cardBorder}`,
                background: isActive ? activeBg : c.cardBg,
                color: isActive ? resolvedColors[s] : c.textMuted,
                cursor: 'pointer', transition: 'all .15s',
              }}
            >
              {s}
            </button>
          );
        })}
      </div>

      <div className="search-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontWeight: 700, fontSize: '1.1rem' }}>
            Risk Alerts
            <span style={{ marginLeft: 8, fontSize: 14, color: '#6b7280' }}>({filtered.length})</span>
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
                <div className="mass-action-item" onClick={() => handleMassAction('export')}>Export {selectedIds.size} to Excel</div>
                <div className="mass-action-item" onClick={() => handleMassAction('pending')}>Update {selectedIds.size} Resolved Status to Pending</div>
                <div className="mass-action-item" onClick={() => handleMassAction('resolved')}>Update {selectedIds.size} Resolved Status to Resolved</div>
                <div className="mass-action-item" onClick={() => handleMassAction('comment')}>Update {selectedIds.size} Comment</div>
              </div>
            )}
          </div>
        </div>

        {loading ? (
          <div className="data-table-container" style={{ padding: 16 }}>
            <TableSkeleton rows={8} columns={14} />
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
            No risk alerts match the current filters.
          </div>
        ) : (
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th><input type="checkbox" checked={selectedIds.size === filtered.length && filtered.length > 0} onChange={toggleAll} /></th>
                <th>Timesheet ID</th>
                <th>Resolved Status</th>
                <th>Risk Category</th>
                <th>Risk Error</th>
                <th>Customer Name</th>
                <th>Candidate</th>
                <th>Placement ID</th>
                <th>TS Period</th>
                <th>Hours Worked</th>
                <th>Pay Hours</th>
                <th>Bill Hours</th>
                <th>Paid</th>
                <th>Billed</th>
                <th>Mark-Up%</th>
                <th>Comments</th>
                <th>Updated Last By</th>
                <th>Update Last Date</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td><input type="checkbox" checked={selectedIds.has(r.id)} onChange={() => toggleSelect(r.id)} /></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, fontWeight: 600, textDecoration: 'none' }}>{r.timesheetId}</a></td>
                  <td>
                    <select
                      value={r.resolvedStatus}
                      onChange={(e) => onStatusChange(r.id, e.target.value as RiskRecord['resolvedStatus'])}
                      style={statusSelectStyle(r.resolvedStatus)}
                    >
                      <option value="Open">Open</option>
                      <option value="Pending">Pending</option>
                      <option value="Resolved">Resolved</option>
                    </select>
                  </td>
                  <td>{r.category.replace(/-/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase())}</td>
                  <td>{r.errorType}</td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, textDecoration: 'none' }}>{r.customerName}</a></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, fontWeight: 600, textDecoration: 'none' }}>{r.candidateName}</a></td>
                  <td><a href="#" onClick={(e) => e.preventDefault()} style={{ color: c.link, textDecoration: 'none' }}>{r.placementId}</a></td>
                  <td>{r.tsPeriod}</td>
                  <td>{r.hoursWorked}</td>
                  <td>{r.payHours}</td>
                  <td>{r.billHours}</td>
                  <td>{r.paid}</td>
                  <td>{r.billed}</td>
                  <td>{r.markupPct}</td>
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
                  <td style={{ color: r.resolvedBy === '—' ? c.textDim : c.text, fontWeight: r.resolvedBy === '—' ? 400 : 600 }}>{r.resolvedBy}</td>
                  <td style={{ color: r.resolvedDate === '—' ? c.textDim : c.text, fontSize: 12 }}>{r.resolvedDate}</td>
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
