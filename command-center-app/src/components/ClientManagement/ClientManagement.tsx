import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowLeft, Building2, Plus, Search, Users, Key,
  Check, X, Loader2, AlertCircle, ChevronRight, Wifi, WifiOff,
  UserPlus, Shield, ToggleLeft, ToggleRight,
} from 'lucide-react';
import type { TenantInfo, UserRole } from '../../types';
import {
  listTenants,
  createTenant,
  updateTenant,
  updateTenantCredentials,
  testTenantConnection,
  listTenantUsers,
  createTenantUser,
  apiUserToAppUser,
  ApiError,
} from '../../api/client';
import type { ApiUserOut } from '../../api/client';
import type { AppUser } from '../../types';

interface ClientManagementProps {
  onBack: () => void;
}

const TIERS = [
  { value: 'assess', label: 'Assess', price: '$5,000/mo', color: '#2563eb', bg: '#eff6ff' },
  { value: 'transform', label: 'Transform', price: '$12,500/mo', color: '#7c3aed', bg: '#f5f3ff' },
  { value: 'enterprise', label: 'Enterprise', price: '$20,000/mo', color: '#0d9488', bg: '#f0fdfa' },
];

const USER_ROLES: { value: string; label: string; color: string }[] = [
  { value: 'admin', label: 'Admin', color: '#7c3aed' },
  { value: 'manager', label: 'Manager', color: '#2563eb' },
  { value: 'viewer', label: 'Viewer', color: '#64748b' },
];

export default function ClientManagement({ onBack }: ClientManagementProps) {
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSlug, setCreateSlug] = useState('');
  const [createTier, setCreateTierValue] = useState('assess');

  // Detail panel
  const [selectedTenant, setSelectedTenant] = useState<TenantInfo | null>(null);
  const [detailTab, setDetailTab] = useState<'users' | 'credentials'>('users');

  // Users tab
  const [tenantUsers, setTenantUsers] = useState<AppUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [showAddUser, setShowAddUser] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserName, setNewUserName] = useState('');
  const [newUserRole, setNewUserRole] = useState('admin');
  const [newUserPassword, setNewUserPassword] = useState('');

  // Inline name editing
  const [editingName, setEditingName] = useState(false);
  const [editNameValue, setEditNameValue] = useState('');

  const handleRenameTenant = async () => {
    if (!selectedTenant || !editNameValue.trim() || editNameValue.trim() === selectedTenant.name) {
      setEditingName(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTenant(selectedTenant.id, { name: editNameValue.trim() });
      setTenants(prev => prev.map(t => t.id === selectedTenant.id ? updated : t));
      setSelectedTenant(updated);
      setEditingName(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to rename tenant');
    } finally {
      setSaving(false);
    }
  };

  // Credentials tab
  const [bhClientId, setBhClientId] = useState('');
  const [bhClientSecret, setBhClientSecret] = useState('');
  const [bhApiUser, setBhApiUser] = useState('');
  const [bhApiPassword, setBhApiPassword] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; message?: string; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const loadTenants = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTenants();
      setTenants(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load tenants');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTenants(); }, [loadTenants]);

  const filteredTenants = useMemo(() => {
    if (!searchQuery) return tenants;
    const q = searchQuery.toLowerCase();
    return tenants.filter(t =>
      t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q)
    );
  }, [tenants, searchQuery]);

  const handleCreate = async () => {
    if (!createName.trim() || !createSlug.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createTenant({
        name: createName.trim(),
        slug: createSlug.trim(),
        tier: createTier,
      });
      setTenants(prev => [created, ...prev]);
      setShowCreate(false);
      setCreateName('');
      setCreateSlug('');
      setCreateTierValue('assess');
      setSelectedTenant(created);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create tenant');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (tenant: TenantInfo) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTenant(tenant.id, { is_active: !tenant.isActive });
      setTenants(prev => prev.map(t => t.id === tenant.id ? updated : t));
      if (selectedTenant?.id === tenant.id) setSelectedTenant(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update tenant');
    } finally {
      setSaving(false);
    }
  };

  const selectTenant = async (tenant: TenantInfo) => {
    setSelectedTenant(tenant);
    setDetailTab('users');
    setTestResult(null);
    setBhClientId('');
    setBhClientSecret('');
    setBhApiUser('');
    setBhApiPassword('');
    setLoadingUsers(true);
    try {
      const users = await listTenantUsers(tenant.id);
      setTenantUsers(users.map((u: ApiUserOut) => apiUserToAppUser(u)));
    } catch {
      setTenantUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleAddUser = async () => {
    if (!selectedTenant || !newUserEmail.trim() || !newUserName.trim() || !newUserPassword.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createTenantUser(selectedTenant.id, {
        email: newUserEmail.trim(),
        name: newUserName.trim(),
        role: newUserRole,
        password: newUserPassword.trim(),
      });
      setTenantUsers(prev => [...prev, apiUserToAppUser(created)]);
      setTenants(prev => prev.map(t =>
        t.id === selectedTenant.id ? { ...t, userCount: t.userCount + 1 } : t
      ));
      setShowAddUser(false);
      setNewUserEmail('');
      setNewUserName('');
      setNewUserRole('admin');
      setNewUserPassword('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create user');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCredentials = async () => {
    if (!selectedTenant || !bhClientId.trim() || !bhClientSecret.trim() || !bhApiUser.trim() || !bhApiPassword.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await updateTenantCredentials(selectedTenant.id, {
        client_id: bhClientId.trim(),
        client_secret: bhClientSecret.trim(),
        api_user: bhApiUser.trim(),
        api_password: bhApiPassword.trim(),
      });
      setTenants(prev => prev.map(t =>
        t.id === selectedTenant.id ? { ...t, hasBullhornConfig: true } : t
      ));
      setSelectedTenant((prev: TenantInfo | null) => prev ? { ...prev, hasBullhornConfig: true } : prev);
      setTestResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save credentials');
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (!selectedTenant) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testTenantConnection(selectedTenant.id);
      setTestResult(result);
    } catch (err) {
      setTestResult({ ok: false, error: err instanceof ApiError ? err.message : 'Test failed' });
    } finally {
      setTesting(false);
    }
  };

  const tierBadge = (tier: string) => {
    const t = TIERS.find(x => x.value === tier) || TIERS[0];
    return (
      <span style={{
        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
        background: t.bg, color: t.color, textTransform: 'uppercase', letterSpacing: '.3px',
      }}>
        {t.label}
      </span>
    );
  };

  const roleBadge = (role: UserRole) => {
    const r = USER_ROLES.find(x => x.value === role);
    const color = r?.color ?? '#64748b';
    return (
      <span style={{
        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
        background: `${color}15`, color, textTransform: 'uppercase', letterSpacing: '.3px',
      }}>
        {r?.label ?? role}
      </span>
    );
  };

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Command Center
      </button>

      <div className="sub-header">
        <h1 style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: 12 }}>
          <Building2 size={28} /> Client Management
        </h1>
        <p>Set up new companies, manage Bullhorn credentials, and create initial users.</p>
      </div>

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderRadius: 10, background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', fontSize: 13, fontWeight: 500, marginBottom: 16 }}>
          <AlertCircle size={16} /> {error}
          <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', fontWeight: 700 }}>&times;</button>
        </div>
      )}

      {saving && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999, height: 3, background: 'linear-gradient(90deg, #2563eb, #0d9488, #2563eb)', backgroundSize: '200% 100%', animation: 'shimmer 1s linear infinite' }} />
      )}

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Building2 size={20} style={{ color: '#2563eb' }} />
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, color: '#0f172a' }}>{tenants.length}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>Total Clients</div>
            </div>
          </div>
          <div style={{ fontSize: 11, color: '#64748b' }}>
            <span style={{ fontWeight: 700, color: '#065f46' }}>{tenants.filter(t => t.isActive).length}</span> active
            {' '}
            <span style={{ fontWeight: 700, color: '#94a3b8' }}>{tenants.filter(t => !t.isActive).length}</span> inactive
          </div>
        </div>
        {TIERS.map(tier => {
          const count = tenants.filter(t => t.tier === tier.value).length;
          return (
            <div key={tier.value} style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', border: `2px solid ${tier.bg}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                {tierBadge(tier.value)}
                <span style={{ fontSize: 24, fontWeight: 800, color: tier.color }}>{count}</span>
              </div>
              <p style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5, margin: 0 }}>{tier.price}</p>
            </div>
          );
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selectedTenant ? '380px 1fr' : '1fr', gap: 20 }}>
        {/* Tenant list */}
        <div>
          <div style={{ background: '#fff', borderRadius: 14, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ position: 'relative', flex: 1, marginRight: 12 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                <input
                  type="text"
                  placeholder="Search clients..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px 8px 32px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, outline: 'none' }}
                />
              </div>
              <button
                onClick={() => setShowCreate(true)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                <Plus size={14} /> New Client
              </button>
            </div>

            <div style={{ maxHeight: 600, overflowY: 'auto' }}>
              {loading && (
                <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                  <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8 }} />
                  Loading clients...
                </div>
              )}
              {!loading && filteredTenants.length === 0 && (
                <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                  {tenants.length === 0 ? 'No clients yet. Create your first client above.' : 'No clients match your search.'}
                </div>
              )}
              {filteredTenants.map(tenant => (
                <div
                  key={tenant.id}
                  onClick={() => selectTenant(tenant)}
                  style={{
                    padding: '14px 20px',
                    borderBottom: '1px solid #f1f5f9',
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: selectedTenant?.id === tenant.id ? '#eff6ff' : undefined,
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (selectedTenant?.id !== tenant.id) (e.currentTarget as HTMLDivElement).style.background = '#f8fafc'; }}
                  onMouseLeave={e => { if (selectedTenant?.id !== tenant.id) (e.currentTarget as HTMLDivElement).style.background = ''; }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>{tenant.name}</span>
                      {tierBadge(tenant.tier)}
                      {!tenant.isActive && (
                        <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: '#f1f5f9', color: '#94a3b8', textTransform: 'uppercase' }}>
                          Inactive
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#64748b' }}>
                      <span>{tenant.slug}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                        <Users size={10} /> {tenant.userCount} users
                      </span>
                      {tenant.hasBullhornConfig ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#10b981' }}>
                          <Wifi size={10} /> Connected
                        </span>
                      ) : (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#f59e0b' }}>
                          <WifiOff size={10} /> No credentials
                        </span>
                      )}
                    </div>
                  </div>
                  <ChevronRight size={16} style={{ color: '#94a3b8' }} />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Detail panel */}
        {selectedTenant && (
          <div style={{ background: '#fff', borderRadius: 14, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    {editingName ? (
                      <>
                        <input
                          autoFocus
                          value={editNameValue}
                          onChange={e => setEditNameValue(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') handleRenameTenant(); if (e.key === 'Escape') setEditingName(false); }}
                          style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', border: '1.5px solid #2563eb', borderRadius: 6, padding: '2px 8px', outline: 'none', width: 220 }}
                        />
                        <button onClick={handleRenameTenant} disabled={saving} style={{ background: '#2563eb', border: 'none', borderRadius: 6, padding: '4px 10px', color: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>
                          Save
                        </button>
                        <button onClick={() => setEditingName(false)} style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 10px', color: '#64748b', fontWeight: 600, fontSize: 12, cursor: 'pointer' }}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <h2
                          style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0, cursor: 'pointer' }}
                          title="Click to rename"
                          onClick={() => { setEditNameValue(selectedTenant.name); setEditingName(true); }}
                        >
                          {selectedTenant.name}
                        </h2>
                        {tierBadge(selectedTenant.tier)}
                        <button
                          onClick={() => { setEditNameValue(selectedTenant.name); setEditingName(true); }}
                          style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 6, padding: '2px 8px', fontSize: 11, color: '#64748b', cursor: 'pointer', fontWeight: 600 }}
                        >
                          Rename
                        </button>
                      </>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>
                    Slug: <strong>{selectedTenant.slug}</strong> &middot; Created: {selectedTenant.createdAt.split('T')[0]}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    onClick={() => handleToggleActive(selectedTenant)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: '#475569' }}
                  >
                    {selectedTenant.isActive ? (
                      <><ToggleRight size={16} style={{ color: '#10b981' }} /> Active</>
                    ) : (
                      <><ToggleLeft size={16} style={{ color: '#94a3b8' }} /> Inactive</>
                    )}
                  </button>
                  <button
                    onClick={() => setSelectedTenant(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0' }}>
              <button
                onClick={() => setDetailTab('users')}
                style={{
                  padding: '12px 24px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 700,
                  borderBottom: detailTab === 'users' ? '2px solid #2563eb' : '2px solid transparent',
                  color: detailTab === 'users' ? '#2563eb' : '#64748b',
                  background: 'none', display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <Users size={14} /> Users ({tenantUsers.length})
              </button>
              <button
                onClick={() => setDetailTab('credentials')}
                style={{
                  padding: '12px 24px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 700,
                  borderBottom: detailTab === 'credentials' ? '2px solid #2563eb' : '2px solid transparent',
                  color: detailTab === 'credentials' ? '#2563eb' : '#64748b',
                  background: 'none', display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <Key size={14} /> Bullhorn Credentials
              </button>
            </div>

            {/* Tab content */}
            <div style={{ padding: 24 }}>
              {detailTab === 'users' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <span style={{ fontSize: 12, color: '#64748b' }}>
                      {tenantUsers.length} user{tenantUsers.length !== 1 ? 's' : ''} in this tenant
                    </span>
                    <button
                      onClick={() => setShowAddUser(true)}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}
                    >
                      <UserPlus size={14} /> Add User
                    </button>
                  </div>

                  {loadingUsers ? (
                    <div style={{ padding: 30, textAlign: 'center', color: '#94a3b8' }}>
                      <Loader2 size={18} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8 }} />
                      Loading users...
                    </div>
                  ) : tenantUsers.length === 0 ? (
                    <div style={{ padding: 30, textAlign: 'center', color: '#94a3b8', fontSize: 13, background: '#f8fafc', borderRadius: 10 }}>
                      No users yet. Add the first admin user for this client.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {tenantUsers.map(user => (
                        <div
                          key={user.id}
                          style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '12px 16px', borderRadius: 10, border: '1px solid #e2e8f0',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div style={{
                              width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                              background: '#eff6ff', color: '#2563eb',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontWeight: 800, fontSize: 11,
                            }}>
                              {user.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                            </div>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{user.name}</div>
                              <div style={{ fontSize: 11, color: '#64748b' }}>{user.email}</div>
                            </div>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {roleBadge(user.role)}
                            <span style={{
                              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                              background: user.status === 'active' ? '#dcfce7' : '#f1f5f9',
                              color: user.status === 'active' ? '#065f46' : '#94a3b8',
                              textTransform: 'uppercase',
                            }}>
                              {user.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {detailTab === 'credentials' && (
                <div>
                  <div style={{ marginBottom: 20 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <Shield size={16} style={{ color: '#475569' }} />
                      <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>Bullhorn API Credentials</span>
                    </div>
                    <p style={{ fontSize: 12, color: '#64748b', margin: 0 }}>
                      Credentials are stored securely and never displayed after saving.
                      {selectedTenant.hasBullhornConfig && ' Re-enter all fields to update.'}
                    </p>
                    {selectedTenant.hasBullhornConfig && (
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 8, padding: '4px 12px', borderRadius: 6, background: '#dcfce7', color: '#065f46', fontSize: 11, fontWeight: 700 }}>
                        <Check size={12} /> Credentials configured
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                        Client ID
                      </label>
                      <input
                        type="text"
                        value={bhClientId}
                        onChange={e => setBhClientId(e.target.value)}
                        placeholder="Enter Bullhorn Client ID"
                        style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none' }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                        Client Secret
                      </label>
                      <input
                        type="password"
                        value={bhClientSecret}
                        onChange={e => setBhClientSecret(e.target.value)}
                        placeholder="Enter Client Secret"
                        style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none' }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                        API Username
                      </label>
                      <input
                        type="text"
                        value={bhApiUser}
                        onChange={e => setBhApiUser(e.target.value)}
                        placeholder="API user login"
                        style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none' }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                        API Password
                      </label>
                      <input
                        type="password"
                        value={bhApiPassword}
                        onChange={e => setBhApiPassword(e.target.value)}
                        placeholder="API user password"
                        style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none' }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <button
                      onClick={handleSaveCredentials}
                      disabled={saving || !bhClientId.trim() || !bhClientSecret.trim() || !bhApiUser.trim() || !bhApiPassword.trim()}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px', borderRadius: 8,
                        border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, fontSize: 13,
                        cursor: 'pointer',
                        opacity: (!bhClientId.trim() || !bhClientSecret.trim() || !bhApiUser.trim() || !bhApiPassword.trim()) ? 0.5 : 1,
                      }}
                    >
                      {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Key size={14} />}
                      Save Credentials
                    </button>
                    {selectedTenant.hasBullhornConfig && (
                      <button
                        onClick={handleTestConnection}
                        disabled={testing}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px', borderRadius: 8,
                          border: '1.5px solid #e2e8f0', background: '#fff', fontWeight: 600, fontSize: 13,
                          cursor: 'pointer', color: '#475569',
                        }}
                      >
                        {testing ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Wifi size={14} />}
                        Test Connection
                      </button>
                    )}
                  </div>

                  {testResult && (
                    <div style={{
                      marginTop: 16, padding: '12px 16px', borderRadius: 10,
                      background: testResult.ok ? '#dcfce7' : '#fef2f2',
                      border: `1px solid ${testResult.ok ? '#86efac' : '#fecaca'}`,
                      color: testResult.ok ? '#065f46' : '#b91c1c',
                      fontSize: 13, fontWeight: 500,
                      display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                      {testResult.ok ? <Check size={16} /> : <X size={16} />}
                      {testResult.ok ? (testResult.message || 'Connection successful') : (testResult.error || 'Connection failed')}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Create Tenant Modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ position: 'relative', maxWidth: 520 }}>
            <button
              className="modal-close"
              onClick={() => setShowCreate(false)}
              style={{ position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#94a3b8' }}
            >
              &times;
            </button>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Building2 size={22} /> New Client
            </h2>
            <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
              Set up a new staffing company on the StaffingAgent platform.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Company Name
                </label>
                <input
                  type="text"
                  value={createName}
                  onChange={e => {
                    setCreateName(e.target.value);
                    if (!createSlug || createSlug === createName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')) {
                      setCreateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
                    }
                  }}
                  placeholder="Acme Staffing Inc."
                  autoFocus
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Slug <span style={{ fontWeight: 400, color: '#94a3b8', textTransform: 'none' }}>(used for login URL)</span>
                </label>
                <input
                  type="text"
                  value={createSlug}
                  onChange={e => setCreateSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                  placeholder="acme-staffing"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, fontFamily: 'monospace' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Tier
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  {TIERS.map(tier => (
                    <button
                      key={tier.value}
                      onClick={() => setCreateTierValue(tier.value)}
                      style={{
                        flex: 1, padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
                        border: createTier === tier.value ? `2px solid ${tier.color}` : '1.5px solid #e2e8f0',
                        background: createTier === tier.value ? tier.bg : '#fff',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: 14, color: tier.color }}>{tier.label}</div>
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{tier.price}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{
              display: 'flex', justifyContent: 'flex-end', gap: 8,
              marginTop: 20, paddingTop: 16, borderTop: '1px solid #e2e8f0',
            }}>
              <button
                onClick={() => setShowCreate(false)}
                style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!createName.trim() || !createSlug.trim() || saving}
                style={{
                  padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer',
                  opacity: (!createName.trim() || !createSlug.trim()) ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Plus size={14} />}
                Create Client
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add User Modal */}
      {showAddUser && selectedTenant && (
        <div className="modal-overlay" onClick={() => setShowAddUser(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ position: 'relative', maxWidth: 480 }}>
            <button
              className="modal-close"
              onClick={() => setShowAddUser(false)}
              style={{ position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#94a3b8' }}
            >
              &times;
            </button>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: 4 }}>Add User to {selectedTenant.name}</h2>
            <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
              Create a new user account for this client.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Full Name</label>
                <input
                  type="text" value={newUserName} onChange={e => setNewUserName(e.target.value)}
                  placeholder="Jane Smith" autoFocus
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Email</label>
                <input
                  type="email" value={newUserEmail} onChange={e => setNewUserEmail(e.target.value)}
                  placeholder="jane@company.com"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Role</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {USER_ROLES.map(r => (
                    <button
                      key={r.value}
                      onClick={() => setNewUserRole(r.value)}
                      style={{
                        flex: 1, padding: '10px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
                        border: newUserRole === r.value ? `2px solid ${r.color}` : '1.5px solid #e2e8f0',
                        background: newUserRole === r.value ? `${r.color}10` : '#fff',
                        fontWeight: 700, fontSize: 13, color: newUserRole === r.value ? r.color : '#64748b',
                      }}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>Password</label>
                <input
                  type="password" value={newUserPassword} onChange={e => setNewUserPassword(e.target.value)}
                  placeholder="Set initial password"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
            </div>

            <div style={{
              display: 'flex', justifyContent: 'flex-end', gap: 8,
              marginTop: 20, paddingTop: 16, borderTop: '1px solid #e2e8f0',
            }}>
              <button
                onClick={() => setShowAddUser(false)}
                style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleAddUser}
                disabled={!newUserEmail.trim() || !newUserName.trim() || !newUserPassword.trim() || saving}
                style={{
                  padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer',
                  opacity: (!newUserEmail.trim() || !newUserName.trim() || !newUserPassword.trim()) ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <UserPlus size={14} />}
                Add User
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
