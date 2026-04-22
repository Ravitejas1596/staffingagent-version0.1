import { useState, useMemo, useEffect, useCallback } from 'react';
import {
  ArrowLeft, UserPlus, Shield, Mail, Trash2,
  ToggleLeft, ToggleRight, Search, ChevronDown,
  ChevronRight, Check, X, RefreshCw, Edit3, Loader2, AlertCircle, KeyRound,
} from 'lucide-react';
import type { AppUser, UserRole, UserPermissions } from '../../types';
import { ROLE_DEFAULT_PERMISSIONS } from '../../types';
import {
  fetchUsers as apiFetchUsers,
  updateUser as apiUpdateUser,
  inviteUser as apiInviteUser,
  deleteUser as apiDeleteUser,
  resendInvite as apiResendInvite,
  setUserPassword as apiSetUserPassword,
  apiUserToAppUser,
  ApiError,
} from '../../api/client';

interface UserManagementProps {
  onBack: () => void;
}

const ROLES: { value: UserRole; label: string; description: string; color: string; bg: string }[] = [
  { value: 'admin', label: 'Admin', description: 'Full access — manage users, settings, and all operations', color: '#7c3aed', bg: '#f5f3ff' },
  { value: 'manager', label: 'Manager', description: 'Operational access — dashboards, mass actions, agent approvals', color: '#2563eb', bg: '#eff6ff' },
  { value: 'viewer', label: 'Viewer', description: 'Read-only — view dashboards, reports, and alerts', color: '#64748b', bg: '#f8fafc' },
];

const PERMISSION_AREAS: { key: keyof UserPermissions; label: string; permissions: { key: string; label: string }[] }[] = [
  { key: 'dashboard', label: 'Dashboard', permissions: [{ key: 'view', label: 'View metrics & panels' }] },
  { key: 'timeops', label: 'TimeOps', permissions: [{ key: 'view', label: 'View data' }, { key: 'execute', label: 'Send reminders & mass actions' }] },
  { key: 'riskops', label: 'RiskOps', permissions: [{ key: 'view', label: 'View alerts' }, { key: 'resolve', label: 'Resolve alerts' }, { key: 'execute', label: 'Mass actions' }] },
  { key: 'agents', label: 'Agents', permissions: [{ key: 'view', label: 'View results' }, { key: 'trigger', label: 'Trigger runs' }, { key: 'approve', label: 'Approve / reject' }] },
  { key: 'settings', label: 'Admin Settings', permissions: [{ key: 'view', label: 'View settings' }, { key: 'edit', label: 'Edit configuration' }] },
  { key: 'users', label: 'User Management', permissions: [{ key: 'view', label: 'View user list' }, { key: 'manage', label: 'Add / edit / remove users' }] },
];

function deepClonePerms(p: UserPermissions): UserPermissions {
  return JSON.parse(JSON.stringify(p));
}

export default function UserManagement({ onBack }: UserManagementProps) {
  const [users, setUsers] = useState<AppUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<UserRole | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'invited' | 'disabled'>('all');

  // Invite modal
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState<UserRole>('viewer');
  const [invitePassword, setInvitePassword] = useState('');

  // Set password modal
  const [setPasswordUserId, setSetPasswordUserId] = useState<string | null>(null);
  const [setPasswordValue, setSetPasswordValue] = useState('');

  // Inline user detail editing
  const [editingDetails, setEditingDetails] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');

  // Permissions panel
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [editPerms, setEditPerms] = useState<UserPermissions | null>(null);
  const [expandedAreas, setExpandedAreas] = useState<Set<string>>(new Set());

  // Role reference panel
  const [showRoleReference, setShowRoleReference] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true);
    setApiError(null);
    try {
      const res = await apiFetchUsers();
      setUsers(res.users.map(apiUserToAppUser));
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Failed to load users';
      setApiError(msg);
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      if (roleFilter !== 'all' && u.role !== roleFilter) return false;
      if (statusFilter !== 'all' && u.status !== statusFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
      }
      return true;
    });
  }, [users, roleFilter, statusFilter, searchQuery]);

  const stats = useMemo(() => ({
    total: users.length,
    active: users.filter((u) => u.status === 'active').length,
    invited: users.filter((u) => u.status === 'invited').length,
    disabled: users.filter((u) => u.status === 'disabled').length,
    admins: users.filter((u) => u.role === 'admin').length,
    managers: users.filter((u) => u.role === 'manager').length,
    viewers: users.filter((u) => u.role === 'viewer').length,
  }), [users]);

  const handleInvite = async () => {
    if (!inviteEmail.trim() || !inviteName.trim()) return;
    setSaving(true);
    setApiError(null);
    try {
      const created = await apiInviteUser({
        email: inviteEmail.trim(),
        name: inviteName.trim(),
        role: inviteRole,
        password: invitePassword.trim() || undefined,
      });
      setUsers((prev) => [...prev, apiUserToAppUser(created)]);
      setInviteEmail('');
      setInviteName('');
      setInviteRole('viewer');
      setInvitePassword('');
      setShowInvite(false);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to invite user');
    } finally {
      setSaving(false);
    }
  };

  const handleSetPassword = async () => {
    if (!setPasswordUserId || !setPasswordValue.trim()) return;
    setSaving(true);
    setApiError(null);
    try {
      await apiSetUserPassword(setPasswordUserId, setPasswordValue.trim());
      setSetPasswordUserId(null);
      setSetPasswordValue('');
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to set password');
    } finally {
      setSaving(false);
    }
  };

  const startEditDetails = (user: AppUser) => {
    setEditingDetails(user.id);
    setEditName(user.name);
    setEditEmail(user.email);
  };

  const saveDetails = async () => {
    if (!editingDetails || !editName.trim() || !editEmail.trim()) return;
    setSaving(true);
    setApiError(null);
    try {
      const updated = await apiUpdateUser(editingDetails, { name: editName.trim(), email: editEmail.trim() });
      setUsers((prev) => prev.map((u) => u.id === editingDetails ? apiUserToAppUser(updated) : u));
      setEditingDetails(null);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to update user');
    } finally {
      setSaving(false);
    }
  };

  const cancelEditDetails = () => {
    setEditingDetails(null);
  };

  const updateRole = async (id: string, role: UserRole) => {
    setSaving(true);
    setApiError(null);
    try {
      const updated = await apiUpdateUser(id, { role });
      setUsers((prev) => prev.map((u) => u.id === id ? apiUserToAppUser(updated) : u));
      if (editingUser === id) {
        setEditPerms(deepClonePerms(ROLE_DEFAULT_PERMISSIONS[role]));
      }
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to update role');
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async (id: string) => {
    const user = users.find((u) => u.id === id);
    if (!user) return;
    const newActive = user.status !== 'active';
    setSaving(true);
    setApiError(null);
    try {
      const updated = await apiUpdateUser(id, { is_active: newActive });
      setUsers((prev) => prev.map((u) => u.id === id ? apiUserToAppUser(updated) : u));
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to toggle status');
    } finally {
      setSaving(false);
    }
  };

  const removeUser = async (id: string) => {
    if (!confirm('Remove this user? They will lose access immediately.')) return;
    setSaving(true);
    setApiError(null);
    try {
      await apiDeleteUser(id);
      setUsers((prev) => prev.filter((u) => u.id !== id));
      if (editingUser === id) { setEditingUser(null); setEditPerms(null); }
      if (editingDetails === id) setEditingDetails(null);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to remove user');
    } finally {
      setSaving(false);
    }
  };

  const openPermissions = (user: AppUser) => {
    setEditingUser(user.id);
    setEditPerms(deepClonePerms(user.permissions));
    setExpandedAreas(new Set());
  };

  const savePermissions = async () => {
    if (!editingUser || !editPerms) return;
    setSaving(true);
    setApiError(null);
    try {
      const updated = await apiUpdateUser(editingUser, { permissions: editPerms as unknown as Record<string, Record<string, boolean>> });
      setUsers((prev) => prev.map((u) => u.id === editingUser ? apiUserToAppUser(updated) : u));
      setEditingUser(null);
      setEditPerms(null);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : 'Failed to save permissions');
    } finally {
      setSaving(false);
    }
  };

  const togglePerm = (area: keyof UserPermissions, perm: string) => {
    if (!editPerms) return;
    setEditPerms((prev) => {
      if (!prev) return prev;
      const updated = deepClonePerms(prev);
      const areaPerms = updated[area] as Record<string, boolean>;
      areaPerms[perm] = !areaPerms[perm];
      return updated;
    });
  };

  const resetToDefaults = () => {
    if (!editingUser) return;
    const user = users.find((u) => u.id === editingUser);
    if (user) setEditPerms(deepClonePerms(ROLE_DEFAULT_PERMISSIONS[user.role]));
  };

  const toggleArea = (area: string) => {
    setExpandedAreas((prev) => {
      const next = new Set(prev);
      if (next.has(area)) next.delete(area);
      else next.add(area);
      return next;
    });
  };

  const roleBadge = (role: UserRole) => {
    const r = ROLES.find((x) => x.value === role);
    if (!r) return null;
    return (
      <span style={{
        fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 6,
        background: r.bg, color: r.color, textTransform: 'uppercase', letterSpacing: '.3px',
      }}>
        {r.label}
      </span>
    );
  };

  const statusBadge = (status: string) => {
    const map: Record<string, { bg: string; color: string; label: string }> = {
      active: { bg: '#dcfce7', color: '#065f46', label: 'Active' },
      invited: { bg: '#dbeafe', color: '#1d4ed8', label: 'Invited' },
      disabled: { bg: '#f1f5f9', color: '#64748b', label: 'Disabled' },
    };
    const s = map[status] || map.active;
    return (
      <span style={{
        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
        background: s.bg, color: s.color, textTransform: 'uppercase', letterSpacing: '.3px',
      }}>
        {s.label}
      </span>
    );
  };

  const permIcon = (enabled: boolean) => enabled
    ? <Check size={14} style={{ color: '#10b981' }} />
    : <X size={14} style={{ color: '#dc2626', opacity: 0.4 }} />;

  const editingUserData = editingUser ? users.find((u) => u.id === editingUser) : null;

  return (
    <div>
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={18} /> Back to Command Center
      </button>

      <div className="sub-header">
        <h1 style={{ fontSize: '2rem' }}>User Management</h1>
        <p>Manage team access, roles, permissions, and invitations.</p>
      </div>

      {/* Error banner */}
      {apiError && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderRadius: 10, background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', fontSize: 13, fontWeight: 500, marginBottom: 16 }}>
          <AlertCircle size={16} /> {apiError}
          <button onClick={() => setApiError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', fontWeight: 700 }}>&times;</button>
        </div>
      )}

      {/* Loading overlay for mutations */}
      {saving && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999, height: 3, background: 'linear-gradient(90deg, #2563eb, #0d9488, #2563eb)', backgroundSize: '200% 100%', animation: 'shimmer 1s linear infinite' }} />
      )}

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Shield size={20} style={{ color: '#2563eb' }} />
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, color: '#0f172a' }}>{stats.total}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>Total Users</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748b' }}>
            <span><span style={{ fontWeight: 700, color: '#065f46' }}>{stats.active}</span> active</span>
            <span><span style={{ fontWeight: 700, color: '#1d4ed8' }}>{stats.invited}</span> invited</span>
            <span><span style={{ fontWeight: 700, color: '#64748b' }}>{stats.disabled}</span> disabled</span>
          </div>
        </div>

        {ROLES.map((r) => (
          <div key={r.value} style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.06)', border: `2px solid ${r.bg}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              {roleBadge(r.value)}
              <span style={{ fontSize: 24, fontWeight: 800, color: r.color }}>
                {r.value === 'admin' ? stats.admins : r.value === 'manager' ? stats.managers : stats.viewers}
              </span>
            </div>
            <p style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5, margin: 0 }}>{r.description}</p>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ background: '#fff', borderRadius: '14px 14px 0 0', padding: '16px 24px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input
              type="text"
              placeholder="Search by name or email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ padding: '8px 12px 8px 34px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, width: 260, outline: 'none' }}
            />
          </div>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value as UserRole | 'all')}
            style={{ padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, cursor: 'pointer' }}
          >
            <option value="all">All Roles</option>
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'invited' | 'disabled')}
            style={{ padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, cursor: 'pointer' }}
          >
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="invited">Invited</option>
            <option value="disabled">Disabled</option>
          </select>
          <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
            {filteredUsers.length} of {users.length} users
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => setShowRoleReference(!showRoleReference)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: '1.5px solid #e2e8f0', background: showRoleReference ? '#f8fafc' : '#fff', fontWeight: 600, fontSize: 13, cursor: 'pointer', color: '#475569' }}
          >
            <Shield size={15} /> Role Reference
          </button>
          <button
            onClick={() => setShowInvite(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
          >
            <UserPlus size={16} /> Invite User
          </button>
        </div>
      </div>

      {/* Role Reference Panel */}
      {showRoleReference && (
        <div style={{ background: '#f8fafc', padding: 20, borderLeft: '1px solid #e2e8f0', borderRight: '1px solid #e2e8f0' }}>
          <h4 style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', marginBottom: 16, marginTop: 0 }}>Default Permissions by Role</h4>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #e2e8f0', fontWeight: 700, color: '#475569' }}>Permission</th>
                  {ROLES.map((r) => (
                    <th key={r.value} style={{ textAlign: 'center', padding: '6px 12px', borderBottom: '2px solid #e2e8f0' }}>
                      {roleBadge(r.value)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PERMISSION_AREAS.map((area) =>
                  area.permissions.map((perm, pi) => (
                    <tr key={`${area.key}-${perm.key}`} style={{ borderBottom: pi === area.permissions.length - 1 ? '2px solid #e2e8f0' : '1px solid #f1f5f9' }}>
                      <td style={{ padding: '6px 12px', color: '#334155' }}>
                        {pi === 0 && <span style={{ fontWeight: 700, color: '#0f172a' }}>{area.label}: </span>}
                        {perm.label}
                      </td>
                      {ROLES.map((r) => {
                        const val = (ROLE_DEFAULT_PERMISSIONS[r.value][area.key] as Record<string, boolean>)[perm.key];
                        return (
                          <td key={r.value} style={{ textAlign: 'center', padding: '6px 12px' }}>
                            {permIcon(val)}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* User Table */}
      <div style={{ background: '#fff', borderRadius: showRoleReference ? '0 0 14px 14px' : '0 0 14px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
        <div className="data-table-container" style={{ boxShadow: 'none' }}>
          <table className="data-table" style={{ minWidth: 1000 }}>
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last Login</th>
                <th>Invited By</th>
                <th>Invited</th>
                <th style={{ textAlign: 'center' }}>Permissions</th>
                <th style={{ textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingUsers && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                    <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8 }} />
                    Loading users...
                  </td>
                </tr>
              )}
              {!loadingUsers && filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
                    No users match the current filters.
                  </td>
                </tr>
              )}
              {filteredUsers.map((u) => (
                <tr key={u.id} style={{ background: editingUser === u.id ? '#f0f9ff' : editingDetails === u.id ? '#fffbeb' : undefined }}>
                  <td>
                    {editingDetails === u.id ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                          width: 36, height: 36, borderRadius: '50%',
                          background: '#fef3c7', color: '#92400e',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontWeight: 800, fontSize: 12, flexShrink: 0,
                        }}>
                          <Edit3 size={14} />
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            placeholder="Full name"
                            autoFocus
                            onKeyDown={(e) => { if (e.key === 'Enter') saveDetails(); if (e.key === 'Escape') cancelEditDetails(); }}
                            style={{
                              padding: '4px 8px', border: '1.5px solid #f59e0b', borderRadius: 6,
                              fontSize: 13, fontWeight: 700, outline: 'none', width: '100%',
                              background: '#fffbeb',
                            }}
                          />
                          <input
                            type="email"
                            value={editEmail}
                            onChange={(e) => setEditEmail(e.target.value)}
                            placeholder="email@company.com"
                            onKeyDown={(e) => { if (e.key === 'Enter') saveDetails(); if (e.key === 'Escape') cancelEditDetails(); }}
                            style={{
                              padding: '4px 8px', border: '1.5px solid #f59e0b', borderRadius: 6,
                              fontSize: 11, outline: 'none', width: '100%',
                              background: '#fffbeb', color: '#475569',
                            }}
                          />
                          <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
                            <button
                              onClick={saveDetails}
                              disabled={!editName.trim() || !editEmail.trim()}
                              style={{
                                padding: '2px 10px', borderRadius: 5, border: 'none',
                                background: '#10b981', color: '#fff', fontSize: 11,
                                fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3,
                                opacity: (!editName.trim() || !editEmail.trim()) ? 0.5 : 1,
                              }}
                            >
                              <Check size={11} /> Save
                            </button>
                            <button
                              onClick={cancelEditDetails}
                              style={{
                                padding: '2px 10px', borderRadius: 5, border: '1px solid #d1d5db',
                                background: '#fff', fontSize: 11, fontWeight: 600,
                                cursor: 'pointer', color: '#64748b',
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                          width: 36, height: 36, borderRadius: '50%',
                          background: u.role === 'admin' ? '#f5f3ff' : u.role === 'manager' ? '#eff6ff' : '#f8fafc',
                          color: u.role === 'admin' ? '#7c3aed' : u.role === 'manager' ? '#2563eb' : '#64748b',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontWeight: 800, fontSize: 12, flexShrink: 0,
                        }}>
                          {u.name.split(' ').map((n) => n[0]).join('')}
                        </div>
                        <div
                          style={{ cursor: 'pointer' }}
                          onClick={() => startEditDetails(u)}
                          title="Click to edit name and email"
                        >
                          <div style={{ fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
                            {u.name}
                            <Edit3 size={11} style={{ color: '#94a3b8', opacity: 0 }} className="edit-hint" />
                          </div>
                          <div style={{ fontSize: 11, color: '#64748b' }}>{u.email}</div>
                        </div>
                      </div>
                    )}
                  </td>
                  <td>
                    <select
                      value={u.role}
                      onChange={(e) => updateRole(u.id, e.target.value as UserRole)}
                      style={{
                        padding: '4px 8px', borderRadius: 6, border: '1px solid #d1d5db',
                        fontSize: 12, fontWeight: 600, cursor: 'pointer', background: '#fff',
                      }}
                    >
                      {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </td>
                  <td>{statusBadge(u.status)}</td>
                  <td style={{ fontSize: 12, color: u.lastLogin === '—' ? '#94a3b8' : '#475569' }}>{u.lastLogin}</td>
                  <td style={{ fontSize: 12, color: '#475569' }}>{u.invitedBy}</td>
                  <td style={{ fontSize: 12, color: '#475569' }}>{u.invitedDate}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      onClick={() => editingUser === u.id ? (setEditingUser(null), setEditPerms(null)) : openPermissions(u)}
                      title="Edit permissions"
                      style={{
                        background: editingUser === u.id ? '#2563eb' : 'none',
                        color: editingUser === u.id ? '#fff' : '#2563eb',
                        border: editingUser === u.id ? 'none' : '1px solid #2563eb',
                        borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11,
                        fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 4,
                      }}
                    >
                      <Edit3 size={12} /> {editingUser === u.id ? 'Close' : 'Edit'}
                    </button>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                      {u.status === 'invited' && (
                        <button
                          onClick={async () => { try { await apiResendInvite(u.id); alert(`Re-invitation sent to ${u.email}`); } catch { alert('Failed to resend invite'); } }}
                          title="Resend invitation"
                          style={{ background: 'none', border: '1px solid #d1d5db', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600, color: '#2563eb' }}
                        >
                          <Mail size={12} /> Resend
                        </button>
                      )}
                      <button
                        onClick={() => toggleStatus(u.id)}
                        title={u.status === 'active' ? 'Disable user' : 'Enable user'}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
                      >
                        {u.status === 'active'
                          ? <ToggleRight size={20} style={{ color: '#10b981' }} />
                          : <ToggleLeft size={20} style={{ color: '#94a3b8' }} />}
                      </button>
                      <button
                        onClick={() => { setSetPasswordUserId(u.id); setSetPasswordValue(''); }}
                        title="Set password"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: 4 }}
                      >
                        <KeyRound size={14} />
                      </button>
                      <button
                        onClick={() => removeUser(u.id)}
                        title="Remove user"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: 4 }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Permissions Editor Panel */}
      {editingUser && editPerms && editingUserData && (
        <div style={{
          background: '#fff', borderRadius: 14, padding: 24, marginTop: 16,
          boxShadow: '0 2px 8px rgba(0,0,0,0.06)', border: '2px solid #2563eb',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 800, color: '#0f172a', margin: 0 }}>
                Permissions — {editingUserData.name}
              </h3>
              <p style={{ fontSize: 12, color: '#64748b', margin: '4px 0 0' }}>
                Role: {roleBadge(editingUserData.role)}
                <span style={{ marginLeft: 8 }}>Override individual permissions below, or reset to role defaults.</span>
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={resetToDefaults}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', borderRadius: 8, border: '1.5px solid #e2e8f0', background: '#fff', fontWeight: 600, fontSize: 12, cursor: 'pointer', color: '#64748b' }}
              >
                <RefreshCw size={13} /> Reset to Defaults
              </button>
              <button
                onClick={() => { setEditingUser(null); setEditPerms(null); }}
                style={{ padding: '8px 14px', borderRadius: 8, border: '1.5px solid #e2e8f0', background: '#fff', fontWeight: 600, fontSize: 12, cursor: 'pointer', color: '#64748b' }}
              >
                Cancel
              </button>
              <button
                onClick={savePermissions}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}
              >
                <Check size={14} /> Save Permissions
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {PERMISSION_AREAS.map((area) => {
              const isExpanded = expandedAreas.has(area.key);
              const areaPerms = editPerms[area.key] as Record<string, boolean>;
              const defaults = ROLE_DEFAULT_PERMISSIONS[editingUserData.role][area.key] as Record<string, boolean>;
              const hasOverrides = area.permissions.some((p) => areaPerms[p.key] !== defaults[p.key]);

              return (
                <div
                  key={area.key}
                  style={{
                    border: hasOverrides ? '2px solid #f59e0b' : '1.5px solid #e2e8f0',
                    borderRadius: 10, overflow: 'hidden',
                    background: hasOverrides ? '#fffbeb' : '#fff',
                  }}
                >
                  <button
                    onClick={() => toggleArea(area.key)}
                    style={{
                      width: '100%', padding: '12px 16px', border: 'none', cursor: 'pointer',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      background: 'transparent',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span style={{ fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{area.label}</span>
                      {hasOverrides && (
                        <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: '#fef3c7', color: '#92400e', textTransform: 'uppercase' }}>
                          Custom
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {area.permissions.map((p) => (
                        <span key={p.key}>{permIcon(areaPerms[p.key])}</span>
                      ))}
                    </div>
                  </button>

                  {isExpanded && (
                    <div style={{ padding: '0 16px 12px', borderTop: '1px solid #e2e8f0' }}>
                      {area.permissions.map((perm) => {
                        const isOn = areaPerms[perm.key];
                        const isDefault = isOn === defaults[perm.key];
                        return (
                          <div
                            key={perm.key}
                            style={{
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              padding: '10px 0', borderBottom: '1px solid #f1f5f9',
                            }}
                          >
                            <div>
                              <span style={{ fontSize: 13, color: '#334155', fontWeight: 600 }}>{perm.label}</span>
                              {!isDefault && (
                                <span style={{ fontSize: 9, marginLeft: 8, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: '#fef3c7', color: '#92400e' }}>
                                  OVERRIDE
                                </span>
                              )}
                            </div>
                            <button
                              onClick={() => togglePerm(area.key, perm.key)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                            >
                              {isOn
                                ? <ToggleRight size={24} style={{ color: '#10b981' }} />
                                : <ToggleLeft size={24} style={{ color: '#dc2626', opacity: 0.6 }} />}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Invite Modal */}
      {setPasswordUserId && (
        <div className="modal-overlay" onClick={() => setSetPasswordUserId(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ position: 'relative', maxWidth: 400 }}>
            <button
              className="modal-close"
              onClick={() => setSetPasswordUserId(null)}
              style={{ position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#94a3b8' }}
            >
              &times;
            </button>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, marginBottom: 4 }}>Set Password</h2>
            <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
              Set a new password for <strong>{users.find(u => u.id === setPasswordUserId)?.name}</strong>.
            </p>
            <input
              type="password"
              value={setPasswordValue}
              onChange={(e) => setSetPasswordValue(e.target.value)}
              placeholder="New password"
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') handleSetPassword(); }}
              style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14, marginBottom: 16 }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => setSetPasswordUserId(null)}
                style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSetPassword}
                disabled={!setPasswordValue.trim() || saving}
                style={{
                  padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer',
                  opacity: !setPasswordValue.trim() ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <KeyRound size={14} />}
                Set Password
              </button>
            </div>
          </div>
        </div>
      )}

      {showInvite && (
        <div className="modal-overlay" onClick={() => setShowInvite(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ position: 'relative', maxWidth: 520 }}>
            <button
              className="modal-close"
              onClick={() => setShowInvite(false)}
              style={{ position: 'absolute', top: 16, right: 16, background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#94a3b8' }}
            >
              &times;
            </button>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 800, marginBottom: 4 }}>Invite User</h2>
            <p style={{ color: '#64748b', fontSize: 13, marginBottom: 20 }}>
              Send an invitation to join the StaffingAgent Command Center.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Full Name
                </label>
                <input
                  type="text" value={inviteName}
                  onChange={(e) => setInviteName(e.target.value)}
                  placeholder="Jane Smith"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Email Address
                </label>
                <input
                  type="email" value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="jane@company.com"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Role
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {ROLES.map((r) => (
                    <button
                      key={r.value}
                      onClick={() => setInviteRole(r.value)}
                      style={{
                        padding: '12px 16px', borderRadius: 10, cursor: 'pointer',
                        border: inviteRole === r.value ? `2px solid ${r.color}` : '1.5px solid #e2e8f0',
                        background: inviteRole === r.value ? r.bg : '#fff',
                        display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left',
                      }}
                    >
                      <div style={{
                        width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
                        border: inviteRole === r.value ? `2px solid ${r.color}` : '2px solid #d1d5db',
                        background: inviteRole === r.value ? r.color : '#fff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        {inviteRole === r.value && <Check size={12} style={{ color: '#fff' }} />}
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, color: r.color }}>{r.label}</div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{r.description}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                  Password <span style={{ fontWeight: 400, color: '#94a3b8', textTransform: 'none' }}>(optional — set now or later)</span>
                </label>
                <input
                  type="password" value={invitePassword}
                  onChange={(e) => setInvitePassword(e.target.value)}
                  placeholder="Leave blank to set later"
                  style={{ width: '100%', padding: '10px 12px', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 14 }}
                />
              </div>
            </div>

            <div style={{
              display: 'flex', justifyContent: 'flex-end', gap: 8,
              marginTop: 20, paddingTop: 16, borderTop: '1px solid #e2e8f0',
            }}>
              <button
                onClick={() => setShowInvite(false)}
                style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontWeight: 600, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleInvite}
                disabled={!inviteEmail.trim() || !inviteName.trim()}
                style={{
                  padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: '#2563eb', color: '#fff', fontWeight: 600, cursor: 'pointer',
                  opacity: (!inviteEmail.trim() || !inviteName.trim()) ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <Mail size={14} /> Send Invitation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
