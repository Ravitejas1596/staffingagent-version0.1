import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Save } from 'lucide-react';
import { useUI } from '../../context/UIContext';
import { useAuth } from '../../auth/AuthContext';
import {
  ApiError,
  deleteMessageTemplateOverride,
  listMessageTemplates,
  upsertMessageTemplate,
  type MessageTemplate,
} from '../../api/client';

interface AgentSettingsProps {
  onBack: () => void;
}

type Tab = 'thresholds' | 'templates' | 'runtime';

const TEMPLATE_GROUPS: { label: string; keys: string[] }[] = [
  {
    label: 'Group A1 — First-miss missing timesheet',
    keys: ['time_anomaly.group_a1.sms', 'time_anomaly.group_a1.email_subject', 'time_anomaly.group_a1.email_body'],
  },
  {
    label: 'Group A2 — Consecutive missing timesheet',
    keys: ['time_anomaly.group_a2.sms', 'time_anomaly.group_a2.email_subject', 'time_anomaly.group_a2.email_body'],
  },
  {
    label: 'Group B — Hours over limit',
    keys: ['time_anomaly.group_b.sms'],
  },
  {
    label: 'Group C — Hours variance',
    keys: ['time_anomaly.group_c.sms'],
  },
];

export default function AgentSettings({ onBack }: AgentSettingsProps) {
  const { c } = useUI();
  const [tab, setTab] = useState<Tab>('thresholds');

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Dashboard
      </button>

      <div className="sub-header">
        <h1>Agent Settings — Time Anomaly</h1>
        <p>Configure detection thresholds, outreach message copy, and runtime mode for the Time Anomaly agent.</p>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20, borderBottom: `1px solid ${c.cardBorder}` }}>
        {(['thresholds', 'templates', 'runtime'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: tab === t ? `2px solid ${c.accent}` : '2px solid transparent',
              color: tab === t ? c.text : c.textMuted,
              padding: '10px 16px',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {t === 'templates' ? 'Message templates' : t}
          </button>
        ))}
      </div>

      {tab === 'thresholds' && <ThresholdsTab />}
      {tab === 'templates' && <TemplatesTab />}
      {tab === 'runtime' && <RuntimeTab />}
    </div>
  );
}

function ThresholdsTab() {
  const { c } = useUI();
  return (
    <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: 24 }}>
      <h3 style={{ marginTop: 0 }}>Detection thresholds</h3>
      <p style={{ color: c.textMuted, fontSize: 13, marginTop: 0 }}>
        These defaults ship with the agent. Tenant-level overrides are stored in the
        <code style={{ marginLeft: 4, marginRight: 4 }}>agent_settings</code> table and edited here.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <SettingCard label="Group A2 consecutive-miss threshold" value="2 cycles" description="Fire after this many consecutive missing timesheets." />
        <SettingCard label="Group B regular-hours limit" value="40 hr" description="W-2 weekly threshold for reg-over-limit alerts." />
        <SettingCard label="Group B overtime limit" value="20 hr" description="Weekly threshold for OT-over-limit alerts." />
        <SettingCard label="Group B total-hours limit" value="60 hr" description="Combined regular + overtime threshold." />
        <SettingCard label="Group C variance tolerance" value="25%" description="Variance from historical average that triggers Group C." />
        <SettingCard label="Group C re-fire multiplier" value="2.0x" description="New variance must be this multiple of the dismissed magnitude to re-fire." />
        <SettingCard label="Group C lookback window" value="6 weeks" description="History used by the benchmark provider." />
        <SettingCard label="Suppression window" value="30 days" description="Default expiry when a user dismisses a Group C alert." />
      </div>
      <div style={{ marginTop: 16, padding: 12, background: c.panelBg, borderRadius: 8, fontSize: 13, color: c.textMuted }}>
        Inline editing for these thresholds lands in the next iteration. For now,
        update <code>agent_settings</code> directly (keys such as
        <code> group_c.tolerance_pct</code>) and restart the agent workers.
      </div>
    </div>
  );
}

function SettingCard({ label, value, description }: { label: string; value: string; description: string }) {
  const { c } = useUI();
  return (
    <div style={{ border: `1px solid ${c.cardBorder}`, borderRadius: 10, padding: 16, background: c.cardBg }}>
      <div style={{ fontSize: 12, color: c.textMuted, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 22, color: c.text, fontWeight: 800, margin: '4px 0 6px' }}>{value}</div>
      <div style={{ fontSize: 12, color: c.textMuted }}>{description}</div>
    </div>
  );
}

function TemplatesTab() {
  const { c } = useUI();
  const { user } = useAuth();
  const tenantId = user?.tenantId ?? '';
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { subject: string; body: string }>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) {
      setError('Tenant context is missing. Are you logged in?');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rows = await listMessageTemplates(tenantId);
      setTemplates(rows);
      const next: Record<string, { subject: string; body: string }> = {};
      for (const r of rows) {
        next[`${r.template_key}:${r.tenant_id ?? 'default'}`] = {
          subject: r.subject ?? '',
          body: r.body ?? '',
        };
      }
      setDrafts(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);

  const forKey = (key: string) => templates.filter((t) => t.template_key === key);

  const save = async (t: MessageTemplate) => {
    const k = `${t.template_key}:${t.tenant_id ?? 'default'}`;
    const draft = drafts[k];
    if (!draft) return;
    setSaving(t.template_key);
    try {
      await upsertMessageTemplate(tenantId, {
        template_key: t.template_key,
        channel: t.channel,
        language: t.language,
        subject: draft.subject || null,
        body: draft.body,
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const resetOverride = async (t: MessageTemplate) => {
    if (!t.tenant_id) return;
    if (!window.confirm('Revert to the platform default for this template?')) return;
    try {
      await deleteMessageTemplateOverride(tenantId, t.template_key);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  if (loading) return <div style={{ color: c.textMuted }}>Loading templates…</div>;
  if (error) return <div style={{ color: '#dc2626' }}>Error: {error}</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {TEMPLATE_GROUPS.map((group) => (
        <div key={group.label} style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: 20 }}>
          <h3 style={{ marginTop: 0 }}>{group.label}</h3>
          {group.keys.map((key) => {
            const rows = forKey(key);
            const tenantRow = rows.find((r) => r.tenant_id);
            const defaultRow = rows.find((r) => !r.tenant_id);
            const active = tenantRow ?? defaultRow;
            if (!active) {
              return (
                <div key={key} style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: c.text }}>{key}</div>
                  <div style={{ fontSize: 12, color: c.textMuted }}>Not yet seeded. Ask an admin to install this template.</div>
                </div>
              );
            }
            const draftKey = `${active.template_key}:${active.tenant_id ?? 'default'}`;
            const draft = drafts[draftKey];
            return (
              <div key={key} style={{ marginBottom: 20, paddingBottom: 16, borderBottom: `1px dashed ${c.cardBorder}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: c.text }}>{key}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                    background: tenantRow ? '#e0f2fe' : '#f1f5f9',
                    color: tenantRow ? '#075985' : '#475569',
                    textTransform: 'uppercase', letterSpacing: '0.04em',
                  }}>
                    {tenantRow ? 'Tenant override' : 'Platform default'}
                  </span>
                </div>

                {active.channel === 'email_body' && (
                  <>
                    <label style={{ fontSize: 12, color: c.textMuted }}>Subject</label>
                    <input
                      type="text"
                      value={draft?.subject ?? ''}
                      onChange={(e) => setDrafts({ ...drafts, [draftKey]: { ...draft!, subject: e.target.value } })}
                      style={{ width: '100%', padding: '6px 10px', background: c.cardBg, color: c.text, border: `1px solid ${c.cardBorder}`, borderRadius: 6, marginBottom: 8 }}
                    />
                  </>
                )}

                <label style={{ fontSize: 12, color: c.textMuted }}>Body</label>
                <textarea
                  value={draft?.body ?? ''}
                  onChange={(e) => setDrafts({ ...drafts, [draftKey]: { ...(draft ?? { subject: active.subject ?? '' }), body: e.target.value } })}
                  rows={active.channel === 'sms' ? 3 : 6}
                  style={{ width: '100%', padding: '8px 10px', background: c.cardBg, color: c.text, border: `1px solid ${c.cardBorder}`, borderRadius: 6, fontFamily: 'inherit', fontSize: 13 }}
                />

                <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button
                    onClick={() => void save(active)}
                    disabled={saving === active.template_key}
                    style={{
                      background: '#2563eb', color: '#fff', border: 'none', padding: '6px 14px',
                      borderRadius: 6, fontWeight: 600, fontSize: 12, cursor: 'pointer',
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                    }}
                  >
                    <Save size={12} /> {tenantRow ? 'Save override' : 'Create tenant override'}
                  </button>
                  {tenantRow && (
                    <button
                      onClick={() => void resetOverride(tenantRow)}
                      style={{ background: 'transparent', color: '#dc2626', border: '1px solid #fecaca', padding: '6px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}
                    >
                      Revert to default
                    </button>
                  )}
                  <span style={{ fontSize: 11, color: c.textMuted, marginLeft: 'auto' }}>
                    Variables: {`{{employee_first_name}}, {{week_ending_date}}, {{bte_link}}, {{recruiter_name}}`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function RuntimeTab() {
  const { c } = useUI();
  return (
    <div style={{ background: c.cardBg, border: `1px solid ${c.cardBorder}`, borderRadius: 12, padding: 24 }}>
      <h3 style={{ marginTop: 0 }}>Runtime mode</h3>
      <p style={{ color: c.textMuted, fontSize: 13, marginTop: 0 }}>
        During pilot, the Time Anomaly agent runs in <strong>dry-run</strong> mode by default: it detects,
        writes alerts, and records intended actions — but does not send SMS or mutate Bullhorn until you
        flip it live. Flip the switch below once you've reviewed a week of dry-run alerts.
      </p>

      <div style={{
        border: `1px solid ${c.cardBorder}`,
        borderRadius: 10,
        padding: 20,
        background: c.panelBg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 16,
      }}>
        <div>
          <div style={{ fontWeight: 700, color: c.text }}>Dry run (read-only)</div>
          <div style={{ color: c.textMuted, fontSize: 13 }}>Agent reports what it would do without taking action.</div>
        </div>
        <span style={{ color: '#d97706', fontWeight: 700 }}>ENABLED (default)</span>
      </div>
      <div style={{
        border: `1px dashed ${c.cardBorder}`,
        borderRadius: 10,
        padding: 20,
        background: c.cardBg,
      }}>
        <div style={{ fontWeight: 700, color: c.text }}>Going live checklist</div>
        <ol style={{ margin: '10px 0 0 20px', color: c.text, fontSize: 13, lineHeight: 1.7 }}>
          <li>Twilio Messaging Service configured (see <code>docs/twilio-a2p-onboarding.md</code>)</li>
          <li>BTE service account credentials installed in <code>Secrets Manager</code></li>
          <li>7 days of dry-run alerts reviewed; no false-positive patterns outstanding</li>
          <li>HITL queue staffed during business hours for the first week</li>
          <li>Set <code>agent_settings.time_anomaly.dry_run=false</code> via the admin endpoint</li>
        </ol>
      </div>
    </div>
  );
}
