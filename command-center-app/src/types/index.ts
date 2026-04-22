export interface FilterState {
  dateType: string;
  timeFrame: string;
  dateFrom: string;
  dateTo: string;
  branch: string;
  employmentType: string;
  employeeType: string;
  legalEntity: string;
  glSegment: string;
  productServiceCode: string;
}

export interface EntityMetric {
  label: string;
  value: string | number;
  percentage?: string;
  amount?: string;
  isAlert?: boolean;
  isTile?: boolean;
  dataKey?: string;
  subMetrics?: SubMetric[];
}

export interface SubMetric {
  label: string;
  value: string | number;
  percentage?: string;
  amount?: string;
  clickable?: boolean;
}

export interface EntityPanelData {
  id: string;
  title: string;
  type: 'placement' | 'time-expense' | 'payroll' | 'billing' | 'invoices';
  metrics: EntityMetric[];
  progressBar?: { value: number; label: string; status: 'success' | 'warning' | 'danger' };
}

export interface RiskSubCategory {
  label: string;
  count: number;
  errorType: string;
}

export interface RiskCategory {
  id: string;
  label: string;
  count: number;
  severity: 'HIGH' | 'MED' | 'LOW' | 'CRT';
  color: string;
  subCategories?: RiskSubCategory[];
}

export interface TimesheetRecord {
  id: number;
  timesheetId: string;
  excluded: boolean;
  lastReminderSent: string;
  placementId: string;
  customerName: string;
  jobTitle: string;
  candidateName: string;
  placementStart: string;
  placementEnd: string;
  periodEndDate: string;
  candidateEmail: string;
  comments: string;
  excludedBy: string;
  excludedDate: string;
  branch: string;
}

export interface RiskRecord {
  id: number;
  timesheetId: string;
  resolvedStatus: 'Open' | 'Pending' | 'Resolved';
  category: string;
  errorType: string;
  customerName: string;
  candidateName: string;
  placementId: string;
  tsPeriod: string;
  hoursWorked: number;
  payHours: number;
  billHours: number;
  paid: string;
  billed: string;
  markupPct: string;
  comments: string;
  resolvedBy: string;
  resolvedDate: string;
  severity: 'HIGH' | 'MED' | 'LOW' | 'CRT';
  branch: string;
}

export interface RoleEntitlement {
  role: string;
  access: string[];
}

export interface AdminConfig {
  riskTolerances: {
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
  };
  userAccess: {
    entityPanelAccess: { panel: string; roles: string[] }[];
    riskPanelAccess: { panel: string; roles: string[] }[];
    adminSettingsAccess: { panel: string; roles: string[] }[];
  };
}

export type ViewId =
  | 'command-center'
  | 'dashboard'
  | 'timeops'
  | 'riskops'
  | 'bullhorn'
  | 'agent-time-anomaly'
  | 'agent-risk-alert'
  | 'agent-invoice-matching'
  | 'agent-collections'
  | 'agent-compliance'
  | 'agent-payment-prediction'
  | 'agent-vms-reconciliation'
  | 'agent-vms-reconciliation-live'
  | 'alert-queue'
  | 'agent-settings'
  | 'user-management'
  | 'client-management';

export interface AgentConfig {
  id: string;
  viewId: ViewId;
  name: string;
  shortName: string;
  description: string;
  phase: 'P0' | 'P1' | 'P2';
  status: 'active' | 'beta' | 'coming-soon';
  icon: string;
  color: string;
  capabilities: string[];
}

export type UserRole = 'super_admin' | 'admin' | 'manager' | 'viewer';

export interface UserPermissions {
  dashboard: { view: boolean };
  timeops: { view: boolean; execute: boolean };
  riskops: { view: boolean; resolve: boolean; execute: boolean };
  agents: { view: boolean; trigger: boolean; approve: boolean };
  settings: { view: boolean; edit: boolean };
  users: { view: boolean; manage: boolean };
}

export interface AppUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: 'active' | 'invited' | 'disabled';
  permissions: UserPermissions;
  tenantId: string;
  lastLogin: string;
  invitedBy: string;
  invitedDate: string;
}

export const ROLE_DEFAULT_PERMISSIONS: Record<UserRole, UserPermissions> = {
  super_admin: {
    dashboard: { view: true },
    timeops: { view: true, execute: true },
    riskops: { view: true, resolve: true, execute: true },
    agents: { view: true, trigger: true, approve: true },
    settings: { view: true, edit: true },
    users: { view: true, manage: true },
  },
  admin: {
    dashboard: { view: true },
    timeops: { view: true, execute: true },
    riskops: { view: true, resolve: true, execute: true },
    agents: { view: true, trigger: true, approve: true },
    settings: { view: true, edit: true },
    users: { view: true, manage: true },
  },
  manager: {
    dashboard: { view: true },
    timeops: { view: true, execute: true },
    riskops: { view: true, resolve: true, execute: true },
    agents: { view: true, trigger: true, approve: true },
    settings: { view: false, edit: false },
    users: { view: false, manage: false },
  },
  viewer: {
    dashboard: { view: true },
    timeops: { view: true, execute: false },
    riskops: { view: true, resolve: false, execute: false },
    agents: { view: true, trigger: false, approve: false },
    settings: { view: false, edit: false },
    users: { view: false, manage: false },
  },
};

export interface TenantInfo {
  id: string;
  name: string;
  slug: string;
  tier: string;
  isActive: boolean;
  createdAt: string;
  hasBullhornConfig: boolean;
  userCount: number;
}
