import { Loader2, Play } from 'lucide-react';
import type { FilterState } from '../../types';

interface HeaderProps {
  filters: FilterState;
  onFilterChange: (filters: FilterState) => void;
  onRun: () => void;
  isLoading: boolean;
  lastRun: Date | null;
  onOpenConfigFilters: () => void;
}

export default function Header({ filters, onFilterChange, onRun, isLoading, lastRun, onOpenConfigFilters }: HeaderProps) {
  const update = (key: keyof FilterState, value: string) => {
    onFilterChange({ ...filters, [key]: value });
  };

  const formatTime = (d: Date) =>
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });

  return (
    <div className="header-section">
      <h1 className="header-title">Command Center</h1>

      <div className="filters-grid">
        <div className="filter-group">
          <label className="filter-label">Date Type</label>
          <select value={filters.dateType} onChange={(e) => update('dateType', e.target.value)}>
            <option>Period End Date</option>
            <option>Date Added</option>
            <option>Transaction Date</option>
            <option>Systematic Accounting Date</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Time Frame</label>
          <select value={filters.timeFrame} onChange={(e) => update('timeFrame', e.target.value)}>
            <option>Date Range</option>
            <option>YTD</option>
            <option>Q1</option>
            <option>Q2</option>
            <option>Q3</option>
            <option>Q4</option>
            <option>All Time</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Date From</label>
          <input type="date" value={filters.dateFrom} onChange={(e) => update('dateFrom', e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">Date To</label>
          <input type="date" value={filters.dateTo} onChange={(e) => update('dateTo', e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">BTE Branch</label>
          <select value={filters.branch} onChange={(e) => update('branch', e.target.value)}>
            <option>All Branches</option>
            <option>North Region</option>
            <option>South Region</option>
            <option>East Region</option>
            <option>West Region</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Employment Type</label>
          <select value={filters.employmentType} onChange={(e) => update('employmentType', e.target.value)}>
            <option>All Types</option>
            <option>Temporary</option>
            <option>Contract</option>
            <option>Permanent</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Employee Type</label>
          <select value={filters.employeeType} onChange={(e) => update('employeeType', e.target.value)}>
            <option>All Types</option>
            <option>W2</option>
            <option>1099</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Legal Entity</label>
          <select value={filters.legalEntity} onChange={(e) => update('legalEntity', e.target.value)}>
            <option>All Entities</option>
            <option>Corporate HQ</option>
            <option>Regional Office</option>
            <option>Subsidiary</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">GL Segment</label>
          <select value={filters.glSegment} onChange={(e) => update('glSegment', e.target.value)}>
            <option>All Segments</option>
            <option>Operations</option>
            <option>Administrative</option>
            <option>IT Services</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Product/Service Code</label>
          <select value={filters.productServiceCode} onChange={(e) => update('productServiceCode', e.target.value)}>
            <option>All Codes</option>
            <option>Product A</option>
            <option>Product B</option>
            <option>Service X</option>
          </select>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={onOpenConfigFilters}
            style={{
              background: 'none', border: '1px solid #d1d5db', borderRadius: 8,
              padding: '6px 14px', fontSize: 13, fontWeight: 600, color: '#6b7280',
              cursor: 'pointer',
            }}
          >
            Configure Filters
          </button>
          {lastRun && (
            <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 500 }}>
              Last run: {formatTime(lastRun)}
            </span>
          )}
        </div>
        <button
          onClick={onRun}
          disabled={isLoading}
          style={{
            background: isLoading ? '#93c5fd' : '#2563eb', color: 'white', border: 'none', borderRadius: 8,
            padding: '8px 32px', fontSize: 14, fontWeight: 700,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 8,
            transition: 'background .15s',
          }}
        >
          {isLoading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={14} fill="white" />}
          {isLoading ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  );
}
