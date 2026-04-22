import { useState, useMemo, useCallback, useEffect } from 'react';
import { X } from 'lucide-react';
import type { AdminConfig } from '../../types';
import { getSettings, saveSettings, type TenantSettings } from '../../api/client';

interface AdminSettingsProps {
  onClose: () => void;
}

const ALL_USER_TYPES = [
  'ATS Standard User', 'ATS Manager User', 'ATS Admin User',
  'PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User',
  'Super Admin User',
];

const DEFAULT_ACCESS: AdminConfig['userAccess'] = {
  entityPanelAccess: [
    { panel: 'Placement', roles: ['ATS Standard User', 'ATS Manager User', 'ATS Admin User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
    { panel: 'Time & Expense', roles: ['ATS Manager User', 'ATS Admin User', 'PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
    { panel: 'Payroll', roles: ['PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
    { panel: 'Billing', roles: ['PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
    { panel: 'Invoices', roles: ['PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
  ],
  riskPanelAccess: [
    { panel: 'TimeOps Dashboard', roles: ['ATS Manager User', 'ATS Admin User', 'PayBill Standard User', 'PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
    { panel: 'RiskOps Dashboard', roles: ['PayBill Manager User', 'PayBill Admin User', 'Super Admin User'] },
  ],
  adminSettingsAccess: [
    { panel: 'Admin Settings', roles: ['PayBill Admin User', 'Super Admin User'] },
  ],
};

const DEFAULT_TOLERANCES: AdminConfig['riskTolerances'] = {
  approvedStatuses: 'Active, Confirmed, In Progress, Working',
  pendingStatuses: 'Draft, Onboarding, Pending Start, Under Review',
  inactiveStatuses: 'Closed, Ended, Terminated, Cancelled',
  belowFederalMinWage: 7.25,
  highPayRate: 150,
  highBillRate: 225,
  highHours: 60,
  highPayAmounts: 5000,
  highBillAmounts: 7500,
  lowMarkup: 10,
  highMarkup: 250,
};

function apiToAdminConfig(api: TenantSettings): AdminConfig {
  const rt = api.riskTolerances;
  const ua = api.userAccess;
  return {
    riskTolerances: {
      approvedStatuses:    rt.approvedStatuses    ?? DEFAULT_TOLERANCES.approvedStatuses,
      pendingStatuses:     rt.pendingStatuses     ?? DEFAULT_TOLERANCES.pendingStatuses,
      inactiveStatuses:    rt.inactiveStatuses    ?? DEFAULT_TOLERANCES.inactiveStatuses,
      belowFederalMinWage: rt.belowFederalMinWage ?? DEFAULT_TOLERANCES.belowFederalMinWage,
      highPayRate:         rt.highPayRate         ?? DEFAULT_TOLERANCES.highPayRate,
      highBillRate:        rt.highBillRate        ?? DEFAULT_TOLERANCES.highBillRate,
      highHours:           rt.highHours           ?? DEFAULT_TOLERANCES.highHours,
      highPayAmounts:      rt.highPayAmounts      ?? DEFAULT_TOLERANCES.highPayAmounts,
      highBillAmounts:     rt.highBillAmounts     ?? DEFAULT_TOLERANCES.highBillAmounts,
      lowMarkup:           rt.lowMarkup           ?? DEFAULT_TOLERANCES.lowMarkup,
      highMarkup:          rt.highMarkup          ?? DEFAULT_TOLERANCES.highMarkup,
    },
    userAccess: {
      entityPanelAccess:    (ua.entityPanelAccess    ?? DEFAULT_ACCESS.entityPanelAccess)!,
      riskPanelAccess:      (ua.riskPanelAccess      ?? DEFAULT_ACCESS.riskPanelAccess)!,
      adminSettingsAccess:  (ua.adminSettingsAccess  ?? DEFAULT_ACCESS.adminSettingsAccess)!,
    },
  };
}

function computeActiveStatuses(approved: string, pending: string): string {
  const a = approved.split(',').map((s) => s.trim()).filter(Boolean);
  const p = pending.split(',').map((s) => s.trim()).filter(Boolean);
  return [...new Set([...a, ...p])].join(', ');
}

interface TagPickerProps {
  panel: string;
  roles: string[];
  allRoles: string[];
  onAdd: (role: string) => void;
  onRemove: (role: string) => void;
}

function TagPicker({ panel, roles, allRoles, onAdd, onRemove }: TagPickerProps) {
  const available = useMemo(() => allRoles.filter((r) => !roles.includes(r)), [allRoles, roles]);

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6, color: '#1e293b' }}>{panel}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
        {roles.map((role) => (
          <span key={role} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 10px', borderRadius: 999, background: '#ede9fe', color: '#6d28d9', fontSize: 12, fontWeight: 600 }}>
            {role}
            <button onClick={() => onRemove(role)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a78bfa', fontWeight: 800, fontSize: 14, lineHeight: 1, padding: 0 }}>&times;</button>
          </span>
        ))}
      </div>
      {available.length > 0 && (
        <select
          value=""
          onChange={(e) => { if (e.target.value) onAdd(e.target.value); }}
          style={{ fontSize: 12, padding: '4px 8px', borderRadius: 6, border: '1px solid #d1d5db', color: '#6b7280', cursor: 'pointer' }}
        >
          <option value="">+ Add User Type</option>
          {available.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      )}
    </div>
  );
}

export default function AdminSettings({ onClose }: AdminSettingsProps) {
  const [config, setConfig] = useState<AdminConfig>({ riskTolerances: DEFAULT_TOLERANCES, userAccess: DEFAULT_ACCESS });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getSettings().then((api) => {
      setConfig(apiToAdminConfig(api));
      setLoading(false);
    }).catch((err) => {
      console.warn('[AdminSettings] failed to load settings:', err);
      setLoading(false);
    });
  }, []);

  const updateTolerance = useCallback(<K extends keyof AdminConfig['riskTolerances']>(key: K, value: AdminConfig['riskTolerances'][K]) => {
    setConfig((prev) => ({
      ...prev,
      riskTolerances: { ...prev.riskTolerances, [key]: value },
    }));
    setSaved(false);
  }, []);

  const updateAccess = useCallback((section: keyof AdminConfig['userAccess'], panelIdx: number, fn: (roles: string[]) => string[]) => {
    setConfig((prev) => {
      const updated = [...prev.userAccess[section]];
      updated[panelIdx] = { ...updated[panelIdx], roles: fn(updated[panelIdx].roles) };
      return { ...prev, userAccess: { ...prev.userAccess, [section]: updated } };
    });
    setSaved(false);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload: TenantSettings = {
        riskTolerances: {
          ...config.riskTolerances,
          // billRateMismatchPct defaults to 20 if not stored (new field)
          billRateMismatchPct: (config.riskTolerances as any).billRateMismatchPct ?? 20,
        },
        userAccess: config.userAccess,
      };
      await saveSettings(payload);
      setSaved(true);
    } catch (err: any) {
      setSaveError(err?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const activeStatuses = useMemo(
    () => computeActiveStatuses(config.riskTolerances.approvedStatuses, config.riskTolerances.pendingStatuses),
    [config.riskTolerances.approvedStatuses, config.riskTolerances.pendingStatuses],
  );

  const sectionBadge = (label: string, color: string, bg: string, border: string) => (
    <div style={{ fontSize: 11, fontWeight: 800, padding: '4px 12px', borderRadius: 6, display: 'inline-block', marginBottom: 12, background: bg, color, border: `1px solid ${border}`, letterSpacing: '.03em' }}>
      {label}
    </div>
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ position: 'relative', maxHeight: '85vh', overflowY: 'auto', maxWidth: 720 }}>
        <button className="modal-close" onClick={onClose}><X size={20} /></button>

        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: 8 }}>Admin Settings</h2>
        <p style={{ color: '#64748b', fontSize: '.9rem', marginBottom: 24 }}>Configure risk tolerances, placement statuses, and user access controls.</p>

        {loading && <div style={{ textAlign: 'center', padding: '32px 0', color: '#64748b' }}>Loading settings...</div>}

        {!loading && <>
          {/* ── Risk Tolerances ────────────────────────── */}
          <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 12, paddingBottom: 8, borderBottom: '2px solid #f1f5f9' }}>Risk Tolerances</h3>

          {sectionBadge('Placement Alignment', '#92400e', '#fef3c7', '#fcd34d')}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
            {(['approvedStatuses', 'pendingStatuses', 'inactiveStatuses'] as const).map((key) => (
              <div key={key}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  {key === 'approvedStatuses' ? 'Approved Placement Statuses' : key === 'pendingStatuses' ? 'Pending Placement Statuses' : 'Inactive Placement Statuses'}
                </label>
                <input
                  type="text"
                  value={config.riskTolerances[key]}
                  onChange={(e) => updateTolerance(key, e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, fontWeight: 500 }}
                />
              </div>
            ))}
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                Active Placement Statuses
                <span style={{ fontSize: 9, fontWeight: 800, padding: '1px 6px', borderRadius: 4, background: '#dbeafe', color: '#2563eb' }}>SYSTEM GENERATED</span>
              </label>
              <textarea
                readOnly
                value={activeStatuses}
                style={{ width: '100%', padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, background: '#f8fafc', color: '#64748b', resize: 'none', minHeight: 40 }}
              />
            </div>
          </div>

          {sectionBadge('Wage Compliance', '#166534', '#dcfce7', '#86efac')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12, marginBottom: 20 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Below Federal Min Wage</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>$</span>
                <input type="number" step="0.01" value={config.riskTolerances.belowFederalMinWage} onChange={(e) => updateTolerance('belowFederalMinWage', Number(e.target.value))} style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }} />
              </div>
            </div>
          </div>

          {sectionBadge('Rate Flags', '#1d4ed8', '#dbeafe', '#93c5fd')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            {[
              { key: 'highPayRate' as const, label: 'High Pay Rate', suffix: '/hr' },
              { key: 'highBillRate' as const, label: 'High Bill Rate', suffix: '/hr' },
            ].map((f) => (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>{f.label}</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>$</span>
                  <input type="number" value={config.riskTolerances[f.key]} onChange={(e) => updateTolerance(f.key, Number(e.target.value))} style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }} />
                  <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>{f.suffix}</span>
                </div>
              </div>
            ))}
          </div>

          {sectionBadge('Hours Flags', '#c2410c', '#ffedd5', '#fdba74')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>High Hours Threshold</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input type="number" value={config.riskTolerances.highHours} onChange={(e) => updateTolerance('highHours', Number(e.target.value))} style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }} />
                <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>hrs/wk</span>
              </div>
            </div>
          </div>

          {sectionBadge('Amounts Flags', '#dc2626', '#fef2f2', '#fca5a5')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            {[
              { key: 'highPayAmounts' as const, label: 'High Pay Amounts' },
              { key: 'highBillAmounts' as const, label: 'High Bill Amounts' },
            ].map((f) => (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>{f.label}</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>$</span>
                  <input type="number" value={config.riskTolerances[f.key]} onChange={(e) => updateTolerance(f.key, Number(e.target.value))} style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }} />
                </div>
              </div>
            ))}
          </div>

          {sectionBadge('Markup Analysis', '#7c3aed', '#ede9fe', '#c4b5fd')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 24 }}>
            {[
              { key: 'lowMarkup' as const, label: 'Low Markup', suffix: '%' },
              { key: 'highMarkup' as const, label: 'High Markup', suffix: '%' },
            ].map((f) => (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>{f.label}</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <input type="number" value={config.riskTolerances[f.key]} onChange={(e) => updateTolerance(f.key, Number(e.target.value))} style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }} />
                  <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>{f.suffix}</span>
                </div>
              </div>
            ))}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Bill Rate Mismatch</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="number"
                  value={(config.riskTolerances as any).billRateMismatchPct ?? 20}
                  onChange={(e) => updateTolerance('billRateMismatchPct' as any, Number(e.target.value))}
                  style={{ flex: 1, padding: '8px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontWeight: 600 }}
                />
                <span style={{ color: '#6b7280', fontWeight: 600, fontSize: 14 }}>%</span>
              </div>
            </div>
          </div>

          {/* ── User Access Control ────────────────────────── */}
          <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 12, paddingBottom: 8, borderBottom: '2px solid #f1f5f9' }}>User Access Control</h3>

          {sectionBadge('Entity Panel Access', '#1d4ed8', '#dbeafe', '#93c5fd')}
          {config.userAccess.entityPanelAccess.map((item, idx) => (
            <TagPicker
              key={item.panel}
              panel={item.panel}
              roles={item.roles}
              allRoles={ALL_USER_TYPES}
              onAdd={(role) => updateAccess('entityPanelAccess', idx, (roles) => [...roles, role])}
              onRemove={(role) => updateAccess('entityPanelAccess', idx, (roles) => roles.filter((r) => r !== role))}
            />
          ))}

          {sectionBadge('Risk Panel Access', '#c2410c', '#ffedd5', '#fdba74')}
          {config.userAccess.riskPanelAccess.map((item, idx) => (
            <TagPicker
              key={item.panel}
              panel={item.panel}
              roles={item.roles}
              allRoles={ALL_USER_TYPES}
              onAdd={(role) => updateAccess('riskPanelAccess', idx, (roles) => [...roles, role])}
              onRemove={(role) => updateAccess('riskPanelAccess', idx, (roles) => roles.filter((r) => r !== role))}
            />
          ))}

          {sectionBadge('Admin Settings Access', '#dc2626', '#fef2f2', '#fca5a5')}
          {config.userAccess.adminSettingsAccess.map((item, idx) => (
            <TagPicker
              key={item.panel}
              panel={item.panel}
              roles={item.roles}
              allRoles={ALL_USER_TYPES}
              onAdd={(role) => updateAccess('adminSettingsAccess', idx, (roles) => [...roles, role])}
              onRemove={(role) => updateAccess('adminSettingsAccess', idx, (roles) => roles.filter((r) => r !== role))}
            />
          ))}

          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, paddingTop: 16, borderTop: '1px solid #e2e8f0' }}>
            {saveError && <span style={{ fontSize: 13, color: '#dc2626', marginRight: 8 }}>{saveError}</span>}
            {saved && !saving && <span style={{ fontSize: 13, color: '#16a34a', marginRight: 8 }}>Saved!</span>}
            <button onClick={onClose} style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: saving ? '#94a3b8' : '#2563eb', color: '#fff', fontWeight: 600, cursor: saving ? 'default' : 'pointer' }}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </>}
      </div>
    </div>
  );
}
