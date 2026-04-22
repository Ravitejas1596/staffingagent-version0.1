import { useState } from 'react';
import { X, Plus, Trash2, Pencil } from 'lucide-react';

interface ConfigureFiltersProps {
  onClose: () => void;
}

interface FilterConfig {
  id: string;
  label: string;
  bullhornField: string;
  fieldType: string;
  defaultValue: string;
  required: boolean;
}

let nextId = 100;

const defaultFilters: FilterConfig[] = [
  { id: 'req-1', label: 'Date Type', bullhornField: 'dateType', fieldType: 'Dropdown', defaultValue: 'Period End Date', required: true },
  { id: 'req-2', label: 'Time Frame', bullhornField: 'timeFrame', fieldType: 'Dropdown', defaultValue: 'Date Range', required: true },
  { id: 'req-3', label: 'Date From', bullhornField: 'dateFrom', fieldType: 'Date Picker', defaultValue: '2025-01-01', required: true },
  { id: 'req-4', label: 'Date To', bullhornField: 'dateTo', fieldType: 'Date Picker', defaultValue: '2025-09-08', required: true },
  { id: '1', label: 'BTE Branch', bullhornField: 'customText1', fieldType: 'Dropdown', defaultValue: 'All Branches', required: false },
  { id: '2', label: 'Employment Type', bullhornField: 'employmentType', fieldType: 'Dropdown', defaultValue: 'All Types', required: false },
  { id: '3', label: 'Employee Type', bullhornField: 'customText2', fieldType: 'Dropdown', defaultValue: 'All Types', required: false },
  { id: '4', label: 'Legal Entity', bullhornField: 'customText3', fieldType: 'Dropdown', defaultValue: 'All Entities', required: false },
  { id: '5', label: 'GL Segment', bullhornField: 'customText4', fieldType: 'Dropdown', defaultValue: 'All Segments', required: false },
  { id: '6', label: 'Product/Service Code', bullhornField: 'customText5', fieldType: 'Dropdown', defaultValue: 'All Codes', required: false },
];

export default function ConfigureFilters({ onClose }: ConfigureFiltersProps) {
  const [filters, setFilters] = useState(defaultFilters);

  const requiredFilters = filters.filter((f) => f.required);
  const customFilters = filters.filter((f) => !f.required);

  const remove = (id: string) => {
    setFilters((prev) => prev.filter((f) => f.id !== id));
  };

  const editFilter = (id: string) => {
    const f = filters.find((fl) => fl.id === id);
    if (!f) return;
    const newLabel = prompt('Edit filter display name:', f.label);
    if (newLabel && newLabel.trim()) {
      setFilters((prev) => prev.map((fl) => fl.id === id ? { ...fl, label: newLabel.trim() } : fl));
    }
  };

  const addFilter = () => {
    const label = prompt('Enter filter display name:');
    if (!label || !label.trim()) return;
    const field = prompt('Enter Bullhorn field name (e.g., customText6):');
    if (!field || !field.trim()) return;
    const defaultVal = prompt('Enter default value:', 'All');
    setFilters((prev) => [...prev, {
      id: String(nextId++),
      label: label.trim(),
      bullhornField: field.trim(),
      fieldType: 'Dropdown',
      defaultValue: defaultVal || 'All',
      required: false,
    }]);
  };

  const thStyle: React.CSSProperties = { textAlign: 'left', padding: '8px 12px', fontWeight: 700, color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' };
  const tdStyle: React.CSSProperties = { padding: '10px 12px' };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ position: 'relative', maxWidth: 780, maxHeight: '85vh', overflowY: 'auto' }}>
        <button className="modal-close" onClick={onClose}><X size={20} /></button>

        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>Filter Configuration Settings</h2>
        <p style={{ color: '#64748b', fontSize: '.9rem', marginBottom: 24 }}>Configure which filters appear on your dashboard and set default values.</p>

        {/* Required Date Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 6, background: '#dbeafe', color: '#1d4ed8', border: '1px solid #93c5fd', letterSpacing: '.03em' }}>SYSTEM</span>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>Required Date Filters</span>
        </div>
        <p style={{ color: '#94a3b8', fontSize: 12, marginBottom: 12 }}>These date filters are required and cannot be modified or removed.</p>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 24 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              <th style={thStyle}>Filter Name</th>
              <th style={thStyle}>Bullhorn Field</th>
              <th style={thStyle}>Field Type</th>
              <th style={thStyle}>Default Value</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {requiredFilters.map((f) => (
              <tr key={f.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{f.label}</td>
                <td style={{ ...tdStyle, color: '#6b7280', fontFamily: 'monospace', fontSize: 12 }}>{f.bullhornField}</td>
                <td style={{ ...tdStyle, color: '#6b7280' }}>{f.fieldType}</td>
                <td style={{ ...tdStyle, color: '#6b7280' }}>{f.defaultValue}</td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 999, background: '#fef3c7', color: '#92400e' }}>REQUIRED</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Configured Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 6, background: '#dcfce7', color: '#166534', border: '1px solid #86efac', letterSpacing: '.03em' }}>CUSTOM</span>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#1e293b' }}>Configured Filters</span>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              <th style={thStyle}>Filter Name</th>
              <th style={thStyle}>Bullhorn Field</th>
              <th style={thStyle}>Field Type</th>
              <th style={thStyle}>Default Value</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {customFilters.map((f) => (
              <tr key={f.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{f.label}</td>
                <td style={{ ...tdStyle, color: '#6b7280', fontFamily: 'monospace', fontSize: 12 }}>{f.bullhornField}</td>
                <td style={{ ...tdStyle, color: '#6b7280' }}>{f.fieldType}</td>
                <td style={{ ...tdStyle, color: '#6b7280' }}>{f.defaultValue}</td>
                <td style={{ ...tdStyle, textAlign: 'center' }}>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                    <button onClick={() => editFilter(f.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb' }} title="Edit">
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => remove(f.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }} title="Delete">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <button
          onClick={addFilter}
          style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, border: '1px dashed #F15A29', background: '#fff7ed', color: '#F15A29', fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
        >
          <Plus size={14} /> Add Filter
        </button>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 16, marginTop: 16, borderTop: '1px solid #e2e8f0' }}>
          <button onClick={onClose} style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
          <button onClick={onClose} style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>Save Changes</button>
        </div>
      </div>
    </div>
  );
}
