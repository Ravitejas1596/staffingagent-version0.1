import type { AppUser, TenantInfo, UserPermissions, UserRole } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.staffingagent.ai';
const TOKEN_KEY = 'sa_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Silent refresh (Security Sprint Workstream 7).
 *
 * Access tokens are now 60-minute-TTL (see JWT_SECRET hardening). On any 401
 * response we try once to trade our current token for a fresh one via
 * /api/v1/auth/refresh. If that succeeds, we retry the original request; if
 * it fails, we clear the token and bounce to the login flow.
 *
 * We de-duplicate concurrent refreshes with a module-level promise so that
 * a burst of 401s from parallel requests triggers exactly one refresh call.
 */
let refreshInFlight: Promise<string | null> | null = null;

async function attemptRefresh(): Promise<string | null> {
  const token = getToken();
  if (!token) return null;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) return null;
      const body = await res.json();
      if (body?.access_token) {
        setToken(body.access_token);
        return body.access_token as string;
      }
      return null;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function request<T>(path: string, options: RequestInit = {}, _retrying = false): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (err) {
    const detail = err instanceof TypeError ? err.message : String(err);
    throw new ApiError(0, `Network error — could not reach the server (${detail}). Check your internet connection or try refreshing the page.`);
  }

  if (res.status === 401 && !_retrying && path !== '/api/v1/auth/refresh' && path !== '/api/v1/auth/login') {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      return request<T>(path, options, true);
    }
    clearToken();
    window.location.reload();
    throw new ApiError(401, 'Session expired');
  }

  if (res.status === 401) {
    clearToken();
    window.location.reload();
    throw new ApiError(401, 'Session expired');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  user: ApiUserOut;
}

export interface ApiUserOut {
  id: string;
  email: string;
  name: string;
  role: string;
  permissions: Record<string, Record<string, boolean>>;
  is_active: boolean;
  tenant_id: string;
  invited_by: string | null;
  invited_by_name: string | null;
  invited_at: string | null;
  last_login_at: string | null;
  created_at: string;
}

export function apiUserToAppUser(u: ApiUserOut): AppUser {
  return {
    id: u.id,
    name: u.name,
    email: u.email,
    role: u.role as UserRole,
    status: u.is_active ? 'active' : 'disabled',
    permissions: u.permissions as unknown as UserPermissions,
    tenantId: u.tenant_id || '',
    lastLogin: u.last_login_at || '—',
    invitedBy: u.invited_by_name || '—',
    invitedDate: u.invited_at?.split('T')[0] || '—',
  };
}

export async function login(email: string, password: string, tenantSlug: string): Promise<LoginResponse> {
  return request<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password, tenant_slug: tenantSlug }),
  });
}

export async function getMe(): Promise<ApiUserOut> {
  return request<ApiUserOut>('/api/v1/auth/me');
}

// ── Users ─────────────────────────────────────────────────────

export interface UserListResponse {
  users: ApiUserOut[];
  total: number;
}

export async function fetchUsers(params?: { role?: string; is_active?: boolean; search?: string }): Promise<UserListResponse> {
  const qs = new URLSearchParams();
  if (params?.role) qs.set('role', params.role);
  if (params?.is_active !== undefined) qs.set('is_active', String(params.is_active));
  if (params?.search) qs.set('search', params.search);
  const query = qs.toString();
  return request<UserListResponse>(`/api/v1/users${query ? `?${query}` : ''}`);
}

export async function updateUser(userId: string, data: {
  name?: string;
  email?: string;
  role?: string;
  is_active?: boolean;
  permissions?: Record<string, Record<string, boolean>>;
}): Promise<ApiUserOut> {
  return request<ApiUserOut>(`/api/v1/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function createUser(data: {
  email: string;
  name: string;
  role?: string;
  password?: string;
}): Promise<ApiUserOut> {
  return request<ApiUserOut>('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function inviteUser(data: {
  email: string;
  name: string;
  role?: string;
  password?: string;
}): Promise<ApiUserOut> {
  return request<ApiUserOut>('/api/v1/users/invite', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function setUserPassword(userId: string, password: string): Promise<void> {
  return request<void>(`/api/v1/users/${userId}/set-password`, {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export async function deleteUser(userId: string): Promise<void> {
  return request<void>(`/api/v1/users/${userId}`, { method: 'DELETE' });
}

export async function resendInvite(userId: string): Promise<ApiUserOut> {
  return request<ApiUserOut>(`/api/v1/users/${userId}/invite`, { method: 'POST' });
}

// ── Dashboard ─────────────────────────────────────────────────

export interface DashboardMetrics {
  placements: {
    total: number; active: number; approved: number; pending: number;
    candidates_at_approved: number; customers_at_approved: number;
    starts_in_period: number; ends_in_period: number;
    by_status: Record<string, number>;
  };
  timesheets: {
    total: number; approved: number; submitted: number; rejected: number;
    disputed: number; did_not_work: number; btl_failures: number; total_hours: number;
  };
  payroll: {
    total: number; processed: number; not_processed: number;
    total_amount: number; processed_amount: number; not_processed_amount: number;
    by_status: Record<string, number>;
  };
  billing: {
    total: number; invoiced: number; not_invoiced: number;
    total_amount: number; invoiced_amount: number; not_invoiced_amount: number;
    by_status: Record<string, number>;
  };
  invoices: {
    total: number; finalized: number; not_finalized: number;
    total_amount: number; finalized_amount: number; not_finalized_amount: number;
    by_status: Record<string, number>;
  };
}

export async function getDashboardMetrics(params?: {
  date_from?: string;
  date_to?: string;
  branch?: string;
  employment_type?: string;
  employee_type?: string;
  legal_entity?: string;
  gl_segment?: string;
}): Promise<DashboardMetrics> {
  const qs = new URLSearchParams();
  if (params?.date_from) qs.set('date_from', params.date_from);
  if (params?.date_to) qs.set('date_to', params.date_to);
  if (params?.branch) qs.set('branch', params.branch);
  if (params?.employment_type) qs.set('employment_type', params.employment_type);
  if (params?.employee_type) qs.set('employee_type', params.employee_type);
  if (params?.legal_entity) qs.set('legal_entity', params.legal_entity);
  if (params?.gl_segment) qs.set('gl_segment', params.gl_segment);
  const query = qs.toString();
  return request<DashboardMetrics>(`/api/v1/dashboard/metrics${query ? `?${query}` : ''}`);
}

export async function getDashboardSnapshot(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/v1/dashboard/snapshot');
}

// ── Agent Plan-Approve-Execute ────────────────────────────────

export interface AgentPlanAction {
  id: string;
  run_id: string;
  action_type: string;
  target_ref: string | null;
  target_name: string | null;
  description: string;
  confidence: number | null;
  severity: string | null;
  financial_impact: number | null;
  details: Record<string, unknown> | null;
  approval_status: string;
  execution_status: string;
  execution_result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
}

export interface AgentRunOut {
  id: string;
  agent_type: string;
  status: string;
  triggered_by: string | null;
  trigger_type: string;
  config: Record<string, unknown>;
  plan: Record<string, unknown> | null;
  result_summary: Record<string, unknown> | null;
  execution_report: Record<string, unknown> | null;
  token_usage: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export async function createAgentPlan(
  agentType: string,
  config?: { weeks_back?: number; upload_id?: string; config?: Record<string, unknown> },
): Promise<{ run_id: string; status: string; summary: Record<string, unknown>; action_count: number }> {
  return request(`/api/v1/agents/${agentType}/plan`, {
    method: 'POST',
    body: JSON.stringify(config ?? {}),
  });
}

export async function getAgentPlan(runId: string): Promise<{ run: AgentRunOut; actions: AgentPlanAction[] }> {
  return request(`/api/v1/agents/runs/${runId}/plan`);
}

export async function approveAgentPlan(
  runId: string,
  actionIds?: string[],
): Promise<{ run_id: string; status: string; approved_count: number }> {
  return request(`/api/v1/agents/runs/${runId}/approve`, {
    method: 'POST',
    body: JSON.stringify(actionIds ? { action_ids: actionIds } : {}),
  });
}

export async function executeAgentPlan(
  runId: string,
): Promise<{ run_id: string; status: string; report: Record<string, unknown> }> {
  return request(`/api/v1/agents/runs/${runId}/execute`, { method: 'POST' });
}

export async function cancelAgentPlan(runId: string): Promise<{ run_id: string; status: string }> {
  return request(`/api/v1/agents/runs/${runId}/cancel`, { method: 'POST' });
}

export async function getExecutionReport(
  runId: string,
): Promise<{
  run: AgentRunOut;
  report: Record<string, unknown> | null;
  succeeded: AgentPlanAction[];
  failed: AgentPlanAction[];
  manual_required: AgentPlanAction[];
  skipped: AgentPlanAction[];
}> {
  return request(`/api/v1/agents/runs/${runId}/report`);
}

export async function listAgentRuns(
  agentType?: string,
  limit = 20,
): Promise<AgentRunOut[]> {
  const qs = new URLSearchParams();
  if (agentType) qs.set('agent_type', agentType);
  qs.set('limit', String(limit));
  return request(`/api/v1/agents/runs?${qs.toString()}`);
}

// ── Tenant Settings ───────────────────────────────────────────

export interface RiskTolerances {
  approvedStatuses: string;
  pendingStatuses: string;
  inactiveStatuses: string;
  belowFederalMinWage: number;
  highPayRate: number;
  highBillRate: number;
  highHours: number;
  highPayAmounts: number;
  highBillAmounts: number;
  lowMarkup: number;
  highMarkup: number;
  billRateMismatchPct: number;
}

export interface TenantSettings {
  riskTolerances: RiskTolerances;
  userAccess: {
    entityPanelAccess?: { panel: string; roles: string[] }[];
    riskPanelAccess?: { panel: string; roles: string[] }[];
    adminSettingsAccess?: { panel: string; roles: string[] }[];
  };
}

export async function getSettings(): Promise<TenantSettings> {
  return request<TenantSettings>('/api/v1/settings');
}

export async function saveSettings(data: TenantSettings): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/api/v1/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ── TimeOps ───────────────────────────────────────────────────

export interface TimeOpsResponse {
  records: import('../types').TimesheetRecord[];
  period_end: string;
}

export async function getTimeOpsRecords(periodEnd?: string): Promise<TimeOpsResponse> {
  const qs = new URLSearchParams();
  if (periodEnd) qs.set('period_end', periodEnd);
  const query = qs.toString();
  return request<TimeOpsResponse>(`/api/v1/timeops/records${query ? `?${query}` : ''}`);
}

export async function updateTimeOpsRecord(
  placementBullhornId: string,
  data: { is_excluded?: boolean; comments?: string; send_reminder?: boolean },
  periodEnd?: string,
): Promise<{ ok: boolean }> {
  const qs = new URLSearchParams();
  if (periodEnd) qs.set('period_end', periodEnd);
  const query = qs.toString();
  return request<{ ok: boolean }>(
    `/api/v1/timeops/records/${encodeURIComponent(placementBullhornId)}${query ? `?${query}` : ''}`,
    { method: 'PATCH', body: JSON.stringify(data) },
  );
}

// ── RiskOps ───────────────────────────────────────────────────

export interface RiskOpsRecordsResponse {
  records: import('../types').RiskRecord[];
}

export interface RiskOpsCategoriesResponse {
  categories: import('../types').RiskCategory[];
}

export async function getRiskOpsRecords(): Promise<RiskOpsRecordsResponse> {
  return request<RiskOpsRecordsResponse>('/api/v1/riskops/records');
}

export async function getRiskOpsCategories(): Promise<RiskOpsCategoriesResponse> {
  return request<RiskOpsCategoriesResponse>('/api/v1/riskops/categories');
}

export async function updateRiskOpsRecord(
  recordKey: string,
  data: { status: string; comments?: string },
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/api/v1/riskops/records/${encodeURIComponent(recordKey)}`,
    { method: 'PATCH', body: JSON.stringify(data) },
  );
}

// ── Admin (super_admin only) ──────────────────────────────────

interface ApiTenantOut {
  id: string;
  name: string;
  slug: string;
  tier: string;
  is_active: boolean;
  created_at: string;
  has_bullhorn_config: boolean;
  user_count: number;
}

function apiTenantToInfo(t: ApiTenantOut): TenantInfo {
  return {
    id: t.id,
    name: t.name,
    slug: t.slug,
    tier: t.tier,
    isActive: t.is_active,
    createdAt: t.created_at,
    hasBullhornConfig: t.has_bullhorn_config,
    userCount: t.user_count,
  };
}

export async function listTenants(): Promise<TenantInfo[]> {
  const raw = await request<ApiTenantOut[]>('/api/v1/admin/tenants');
  return raw.map(apiTenantToInfo);
}

export async function createTenant(data: {
  name: string;
  slug: string;
  tier?: string;
}): Promise<TenantInfo> {
  const raw = await request<ApiTenantOut>('/api/v1/admin/tenants', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return apiTenantToInfo(raw);
}

export async function getTenant(tenantId: string): Promise<TenantInfo> {
  const raw = await request<ApiTenantOut>(`/api/v1/admin/tenants/${tenantId}`);
  return apiTenantToInfo(raw);
}

export async function updateTenant(
  tenantId: string,
  data: { name?: string; tier?: string; is_active?: boolean },
): Promise<TenantInfo> {
  const raw = await request<ApiTenantOut>(`/api/v1/admin/tenants/${tenantId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return apiTenantToInfo(raw);
}

export async function updateTenantCredentials(
  tenantId: string,
  data: { client_id: string; client_secret: string; api_user: string; api_password: string },
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/admin/tenants/${tenantId}/credentials`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function testTenantConnection(
  tenantId: string,
): Promise<{ ok: boolean; error?: string; message?: string }> {
  return request<{ ok: boolean; error?: string; message?: string }>(
    `/api/v1/admin/tenants/${tenantId}/test-connection`,
    { method: 'POST' },
  );
}

export async function listTenantUsers(tenantId: string): Promise<ApiUserOut[]> {
  return request<ApiUserOut[]>(`/api/v1/admin/tenants/${tenantId}/users`);
}

export async function createTenantUser(
  tenantId: string,
  data: { email: string; name: string; role?: string; password: string },
): Promise<ApiUserOut> {
  return request<ApiUserOut>(`/api/v1/admin/tenants/${tenantId}/users`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ── Agent Alerts (HITL queue) ─────────────────────────────────

export interface AgentAlertSummary {
  id: string;
  agent_type: string;
  alert_type: string;
  severity: string;
  state: string;
  detected_at: string;
  outreach_sent_at: string | null;
  escalated_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
  placement_id: string | null;
  pay_period_start: string | null;
  pay_period_end: string | null;
  trigger_context: Record<string, unknown>;
}

export interface AgentAlertEvent {
  id: string;
  event_type: string;
  actor_type: string;
  actor_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
  reversal_available: boolean;
}

export interface AgentAlertDetail extends AgentAlertSummary {
  events: AgentAlertEvent[];
}

export interface ListAlertsParams {
  state?: string;
  agent_type?: string;
  severity?: string;
  limit?: number;
}

export async function listAlerts(params: ListAlertsParams = {}): Promise<AgentAlertSummary[]> {
  const qs = new URLSearchParams();
  if (params.state) qs.set('state', params.state);
  if (params.agent_type) qs.set('agent_type', params.agent_type);
  if (params.severity) qs.set('severity', params.severity);
  if (params.limit) qs.set('limit', String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<AgentAlertSummary[]>(`/api/v1/alerts${suffix}`);
}

export async function getAlert(alertId: string): Promise<AgentAlertDetail> {
  return request<AgentAlertDetail>(`/api/v1/alerts/${alertId}`);
}

export interface ResolveAlertBody {
  resolution: string;
  notes?: string;
  action?: 'mark_dnw' | 'set_hold' | 'release_hold';
  dry_run?: boolean;
}

export interface ResolveAlertResult {
  alert_id: string;
  state: string;
  resolution: string;
  action_result: Record<string, unknown> | null;
}

export async function resolveAlert(
  alertId: string,
  body: ResolveAlertBody,
): Promise<ResolveAlertResult> {
  return request<ResolveAlertResult>(`/api/v1/alerts/${alertId}/resolve`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export interface ReverseAlertResult {
  alert_id: string;
  state: string;
  reversed_event_id: string;
  action_result: Record<string, unknown>;
}

export async function reverseAlert(
  alertId: string,
  reason: string,
): Promise<ReverseAlertResult> {
  return request<ReverseAlertResult>(`/api/v1/alerts/${alertId}/reverse`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export interface AgentAlertMetrics {
  window_days: number;
  alerts_triggered: number;
  hitl_required: number;
  auto_resolved: number;
  currently_open: number;
  currently_hitl: number;
  auto_resolved_rate_pct: number;
  by_alert_type: Record<string, number>;
}

export async function getAgentAlertMetrics(
  params: { window_days?: number; agent_type?: string } = {},
): Promise<AgentAlertMetrics> {
  const qs = new URLSearchParams();
  if (params.window_days) qs.set('window_days', String(params.window_days));
  if (params.agent_type !== undefined) qs.set('agent_type', params.agent_type);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<AgentAlertMetrics>(`/api/v1/alerts/metrics${suffix}`);
}

// ── Message Templates (super_admin) ───────────────────────────

export interface MessageTemplate {
  id: string;
  tenant_id: string | null;
  template_key: string;
  channel: string;
  language: string;
  subject: string | null;
  body: string;
  active: boolean;
  updated_at: string;
}

export async function listMessageTemplates(tenantId: string, language = 'en'): Promise<MessageTemplate[]> {
  return request<MessageTemplate[]>(
    `/api/v1/admin/message-templates?tenant_id=${encodeURIComponent(tenantId)}&language=${language}`,
  );
}

export async function upsertMessageTemplate(
  tenantId: string,
  body: { template_key: string; channel: string; language?: string; subject?: string | null; body: string },
): Promise<MessageTemplate> {
  const { template_key, ...rest } = body;
  return request<MessageTemplate>(
    `/api/v1/admin/message-templates/${encodeURIComponent(template_key)}?tenant_id=${encodeURIComponent(tenantId)}`,
    {
      method: 'PUT',
      body: JSON.stringify(rest),
    },
  );
}

export async function deleteMessageTemplateOverride(
  tenantId: string,
  templateKey: string,
): Promise<void> {
  return request<void>(
    `/api/v1/admin/message-templates/${encodeURIComponent(templateKey)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'DELETE' },
  );
}

export { ApiError };
