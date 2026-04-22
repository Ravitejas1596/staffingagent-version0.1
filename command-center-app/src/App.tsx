import { useState, useCallback, useMemo } from 'react';
import { UIContext, buildUIContext } from './context/UIContext';
import './styles/global.css';
import { AuthProvider, useAuth } from './auth/AuthContext';
import Login from './components/Login/Login';
import NavBar from './components/NavBar/NavBar';
import Header from './components/Header/Header';
import Dashboard from './components/Dashboard/Dashboard';
import CommandCenter from './components/CommandCenter/CommandCenter';
import TimeOps from './components/TimeOps/TimeOps';
import RiskOps from './components/RiskOps/RiskOps';
import AgentPlanView from './components/AgentPlanView/AgentPlanView';
import UserManagement from './components/UserManagement/UserManagement';
import ClientManagement from './components/ClientManagement/ClientManagement';
import AdminSettings from './components/AdminSettings/AdminSettings';
import ConfigureFilters from './components/ConfigureFilters/ConfigureFilters';
import ChatWidget from './components/ChatWidget/ChatWidget';
import VMSReconLive from './components/VMSRecon/VMSReconLive';
import AlertQueue from './components/AlertQueue/AlertQueue';
import AgentSettings from './components/AgentSettings/AgentSettings';
import { DashboardSkeleton, RiskCategoriesSkeleton } from './components/Skeleton/Skeleton';
import { getDashboardMetrics, getRiskOpsCategories, ApiError, type DashboardMetrics } from './api/client';
import type { ViewId, FilterState, EntityPanelData, RiskCategory, AgentConfig, EntityMetric } from './types';

const agents: AgentConfig[] = [
  {
    id: 'time-anomaly', viewId: 'agent-time-anomaly', name: 'Time Anomaly Detection', shortName: 'Time Anomaly',
    description: 'Detects overtime violations, missing consecutive timesheets, unusual hour patterns, and time entry anomalies across all active placements.',
    phase: 'P0', status: 'active', icon: '⏱️', color: '#2563eb',
    capabilities: ['Overtime pattern detection (>40h, >50h thresholds)', 'Missing consecutive timesheet identification', 'Unusual hours spike detection vs historical average', 'Auto-flag for HITL review with confidence scoring', 'Bulk reminder generation for missing timesheets'],
  },
  {
    id: 'risk-alert', viewId: 'agent-risk-alert', name: 'Risk Alert Agent', shortName: 'Risk Alert',
    description: 'Monitors all placement, rate, hours, and financial data for compliance risks and anomalies that require immediate attention.',
    phase: 'P0', status: 'active', icon: '🚨', color: '#dc2626',
    capabilities: ['Pay/bill rate mismatch detection', 'Minimum wage compliance monitoring', 'Negative markup identification', 'High amount threshold alerting', 'Placement date alignment validation'],
  },
  {
    id: 'invoice-matching', viewId: 'agent-invoice-matching', name: 'Invoice Matching Agent', shortName: 'Invoice Match',
    description: 'Reconciles invoices against billable charges, identifies discrepancies in amounts, line items, and delivery status.',
    phase: 'P0', status: 'active', icon: '🧾', color: '#7c3aed',
    capabilities: ['Line-item matching between charges and invoices', 'Amount discrepancy detection with tolerance thresholds', 'Duplicate charge identification', 'GL export reconciliation', 'Invoice delivery status tracking'],
  },
  {
    id: 'collections', viewId: 'agent-collections', name: 'Collections Communications', shortName: 'Collections',
    description: 'Generates personalized collection communications based on aging AR data, client history, and payment patterns.',
    phase: 'P0', status: 'active', icon: '💰', color: '#16a34a',
    capabilities: ['AI-generated collection email drafts', 'Aging bucket prioritization (30/60/90+ days)', 'Client payment history analysis', 'Escalation path recommendations', 'Communication tone calibration by client relationship'],
  },
  {
    id: 'compliance', viewId: 'agent-compliance', name: 'Compliance Monitoring', shortName: 'Compliance',
    description: 'Continuous monitoring for regulatory compliance across placements, ensuring FLSA, state wage laws, and contractual obligations are met.',
    phase: 'P1', status: 'active', icon: '📋', color: '#0ea5e9',
    capabilities: ['FLSA overtime classification monitoring', 'State-by-state minimum wage validation', 'Contract term compliance checking', 'Worker classification risk flagging', 'Regulatory change impact analysis'],
  },
  {
    id: 'vms-reconciliation', viewId: 'agent-vms-reconciliation', name: 'VMS Reconciliation', shortName: 'VMS Recon',
    description: 'Reconciles VMS platform data against ATS records, identifying mismatches in hours, rates, and placement details using fuzzy matching.',
    phase: 'P2', status: 'active', icon: '🔄', color: '#ea580c',
    capabilities: ['Fuzzy name matching (RapidFuzz) across VMS and ATS', 'Hours and rate discrepancy detection', 'Multi-VMS platform support (Beeline, Fieldglass, VectorVMS)', 'Confidence scoring with LLM reasoning for edge cases', 'HITL dashboard for flagged mismatches'],
  },
  {
    id: 'gl-reconciliation', viewId: 'agent-gl-reconciliation', name: 'GL Reconciliation', shortName: 'GL Recon',
    description: 'Reconciles General Ledger exports against billable and payable charges to ensure financial integrity.',
    phase: 'P3', status: 'beta', icon: '📖', color: '#6366f1',
    capabilities: ['Match GL entries to source charges', 'Orphaned entry detection', 'Discrepancy reporting with remediation', 'Duplicate posting identification', 'Automatic GL adjustment drafts'],
  },
  {
    id: 'payroll-reconciliation', viewId: 'agent-payroll-reconciliation', name: 'Payroll Reconciliation', shortName: 'Payroll Recon',
    description: 'Reconciles payroll run data from providers against expected payable charges to detect payment errors.',
    phase: 'P3', status: 'beta', icon: '🏦', color: '#f43f5e',
    capabilities: ['Identify underpayments and overpayments', 'Tax withholding anomaly detection', 'Missing payment identification', 'Payroll-to-payable matching', 'Detailed variance analysis'],
  },
  {
    id: 'forecasting', viewId: 'agent-forecasting', name: 'Financial Forecasting', shortName: 'Forecasting',
    description: 'Predicts future cash flow, revenue, and staffing demand based on historical trends and current pipeline.',
    phase: 'P3', status: 'beta', icon: '🔭', color: '#2dd4bf',
    capabilities: ['12-week cash flow prediction', 'Scenario modeling (Best/Worst/Expected)', 'Seasonal trend identification', 'Growth assumption analysis', 'Revenue gap alerting'],
  },
  {
    id: 'kpi', viewId: 'agent-kpi', name: 'Agency KPI Monitor', shortName: 'KPI Monitor',
    description: 'Monitors key performance indicators across the platform and provides actionable business insights.',
    phase: 'P3', status: 'beta', icon: '🎯', color: '#a855f7',
    capabilities: ['Fill rate and gross margin tracking', 'DSO (Days Sales Outstanding) monitoring', 'Anomaly detection for performance drops', 'Actionable business recommendations', 'Automated management reporting'],
  },
  {
    id: 'commissions', viewId: 'agent-commissions', name: 'Commissions Agent', shortName: 'Commissions',
    description: 'Calculates and validates recruiter and sales commissions based on complex spread and volume rules.',
    phase: 'P3', status: 'beta', icon: '🎖️', color: '#fbbf24',
    capabilities: ['Complex spread-based commission calculation', 'Split-commission handling', 'Adjustment and error detection', 'Detailed recruiter/sales reports', 'Payroll-ready export generation'],
  },
  {
    id: 'contract-compliance', viewId: 'agent-contract-compliance', name: 'Contract Compliance', shortName: 'Contract Comp',
    description: 'Monitors placements against Master Service Agreements (MSAs) and SOWs to ensure contractual adherence.',
    phase: 'P3', status: 'beta', icon: '🖋️', color: '#ec4899',
    capabilities: ['MSA/SOW rate limit validation', 'Worker tenure monitoring', 'Upcoming assignment end notifications', 'Policy violation flagging', 'Contractual risk analysis'],
  },
];

const defaultFilters: FilterState = {
  dateType: 'Period End Date',
  timeFrame: 'Date Range',
  dateFrom: '2025-01-01',
  dateTo: '2025-09-08',
  branch: 'All Branches',
  employmentType: 'All Types',
  employeeType: 'All Types',
  legalEntity: 'All Entities',
  glSegment: 'All Segments',
  productServiceCode: 'All Codes',
};

function fmtNum(n: number): string {
  return n >= 1000 ? n.toLocaleString('en-US') : String(n);
}
function fmtDollar(n: number): string {
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (n >= 1000) return '$' + Math.round(n).toLocaleString('en-US');
  return '$' + Math.round(n).toString();
}
function pctOf(part: number, total: number): string {
  if (total === 0) return '0.0%';
  return ((part / total) * 100).toFixed(1) + '%';
}

function mapApiToEntityPanels(d: DashboardMetrics): EntityPanelData[] {
  const { placements: p, timesheets: t, payroll: pr, billing: bi, invoices: inv } = d;

  // Placements
  const placementMetrics: EntityMetric[] = [
    { label: 'Total Active Placements', value: p.active, isTile: true, dataKey: 'total-active-placements' },
    { label: 'Approved Placements', value: p.approved, isTile: true, dataKey: 'approved-placements' },
    { label: 'Pending Placements', value: p.pending, isTile: true, dataKey: 'pending-placements' },
    { label: 'Candidates at Approved Placements', value: p.candidates_at_approved, isTile: true, dataKey: 'candidates-at-approved' },
    { label: 'Customers at Approved Placements', value: p.customers_at_approved, isTile: true, dataKey: 'customers-at-approved' },
    { label: 'Placement Starts', value: p.starts_in_period, isTile: true, dataKey: 'placement-starts' },
    { label: 'Placement Ends', value: p.ends_in_period, isTile: true, dataKey: 'placement-ends' },
  ];

  // Timesheets
  const tTotal = t.total;
  const tApproved = t.approved;
  const tOpen = tTotal - tApproved - t.did_not_work;
  const tPct = tTotal > 0 ? (tApproved / tTotal) * 100 : 0;
  const timesheetMetrics: EntityMetric[] = [
    { label: 'Total Timesheets Expected', value: fmtNum(tTotal) },
    { label: 'Approved Timesheets', value: fmtNum(tApproved), percentage: pctOf(tApproved, tTotal) },
    { label: 'Open Timesheets', value: Math.max(0, tOpen), percentage: pctOf(Math.max(0, tOpen), tTotal),
      subMetrics: [
        { label: 'Submitted Timesheets', value: fmtNum(t.submitted), percentage: pctOf(t.submitted, tTotal), clickable: true },
        { label: 'Rejected Timesheets', value: t.rejected, percentage: pctOf(t.rejected, tTotal) },
        { label: 'Disputed Timesheets', value: t.disputed, percentage: pctOf(t.disputed, tTotal) },
      ],
    },
    { label: 'Did Not Work Timesheets', value: t.did_not_work, percentage: pctOf(t.did_not_work, tTotal) },
    { label: 'BTL Processing Failures', value: t.btl_failures, percentage: pctOf(t.btl_failures, tTotal) },
  ];

  // Payroll
  const prPct = pr.total > 0 ? (pr.processed / pr.total) * 100 : 0;
  const prNotProcessedSubs = Object.entries(pr.by_status)
    .filter(([s]) => s.toLowerCase() !== 'processed')
    .map(([s, cnt]) => ({ label: s, value: cnt }));
  const payrollMetrics: EntityMetric[] = [
    { label: 'Total Payable Charges', value: fmtNum(pr.total), amount: fmtDollar(pr.total_amount) },
    { label: 'Payable Charges Processed (Exported)', value: fmtNum(pr.processed), percentage: pctOf(pr.processed, pr.total), amount: fmtDollar(pr.processed_amount) },
    { label: 'Payable Charges Not Processed', value: pr.not_processed, percentage: pctOf(pr.not_processed, pr.total), amount: fmtDollar(pr.not_processed_amount),
      subMetrics: prNotProcessedSubs.length > 0 ? prNotProcessedSubs : undefined,
    },
  ];

  // Billing
  const biPct = bi.total > 0 ? (bi.invoiced / bi.total) * 100 : 0;
  const biNotInvoicedSubs = Object.entries(bi.by_status)
    .filter(([s]) => s.toLowerCase() !== 'invoiced' && s.toLowerCase() !== 'true')
    .map(([s, cnt]) => ({ label: s, value: cnt }));
  const billingMetrics: EntityMetric[] = [
    { label: 'Total Billable Charges', value: fmtNum(bi.total), amount: fmtDollar(bi.total_amount) },
    { label: 'Billable Charges Invoiced', value: fmtNum(bi.invoiced), percentage: pctOf(bi.invoiced, bi.total), amount: fmtDollar(bi.invoiced_amount) },
    { label: 'Billable Charges Not Invoiced', value: bi.not_invoiced, percentage: pctOf(bi.not_invoiced, bi.total), amount: fmtDollar(bi.not_invoiced_amount),
      subMetrics: biNotInvoicedSubs.length > 0 ? biNotInvoicedSubs : undefined,
    },
  ];

  // Invoices
  const invPct = inv.total > 0 ? (inv.finalized / inv.total) * 100 : 0;
  const invNotFinalizedSubs = Object.entries(inv.by_status)
    .filter(([s]) => !['paid', 'voided', 'finalized'].includes(s.toLowerCase()))
    .map(([s, cnt]) => ({ label: s, value: cnt }));
  const invoiceMetrics: EntityMetric[] = [
    { label: 'Total Invoices', value: fmtNum(inv.total), amount: fmtDollar(inv.total_amount) },
    { label: 'Finalized Invoices', value: fmtNum(inv.finalized), percentage: pctOf(inv.finalized, inv.total), amount: fmtDollar(inv.finalized_amount) },
    { label: 'Not Finalized', value: inv.not_finalized, percentage: pctOf(inv.not_finalized, inv.total), amount: fmtDollar(inv.not_finalized_amount),
      subMetrics: invNotFinalizedSubs.length > 0 ? invNotFinalizedSubs : undefined,
    },
  ];

  return [
    { id: 'placement', title: 'Placements', type: 'placement', metrics: placementMetrics },
    {
      id: 'time-expense', title: 'Time & Expense', type: 'time-expense', metrics: timesheetMetrics,
      progressBar: { value: Math.min(100, Math.round(tPct * 10) / 10), label: `${tPct.toFixed(1)}% Approved`, status: tPct >= 85 ? 'success' : tPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'payroll', title: 'Payroll', type: 'payroll', metrics: payrollMetrics,
      progressBar: { value: Math.min(100, Math.round(prPct * 10) / 10), label: `${prPct.toFixed(1)}% Processed`, status: prPct >= 85 ? 'success' : prPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'billing', title: 'Billing', type: 'billing', metrics: billingMetrics,
      progressBar: { value: Math.min(100, Math.round(biPct * 10) / 10), label: `${biPct.toFixed(1)}% Invoiced`, status: biPct >= 85 ? 'success' : biPct >= 70 ? 'warning' : 'danger' },
    },
    {
      id: 'invoices', title: 'Invoices', type: 'invoices', metrics: invoiceMetrics,
      progressBar: { value: Math.min(100, Math.round(invPct * 10) / 10), label: `${invPct.toFixed(1)}% Finalized`, status: invPct >= 85 ? 'success' : invPct >= 70 ? 'warning' : 'danger' },
    },
  ];
}

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const [currentView, setCurrentView] = useState<ViewId>('command-center');
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [panels, setPanels] = useState<EntityPanelData[] | null>(null);
  const [riskCats, setRiskCats] = useState<RiskCategory[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<Date | null>(null);
  const [showAdminSettings, setShowAdminSettings] = useState(false);
  const [showConfigureFilters, setShowConfigureFilters] = useState(false);
  const [riskFilter, setRiskFilter] = useState<string | null>(null);
  const [newUI, setNewUI] = useState<boolean>(() => localStorage.getItem('sa_new_ui') !== 'false');

  const toggleNewUI = useCallback(() => {
    setNewUI((prev) => {
      const next = !prev;
      localStorage.setItem('sa_new_ui', String(next));
      return next;
    });
  }, []);

  const handleRun = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [metrics, cats] = await Promise.all([
        getDashboardMetrics({
          date_from: filters.dateFrom,
          date_to: filters.dateTo,
          branch: filters.branch,
          employment_type: filters.employmentType,
          employee_type: filters.employeeType,
          legal_entity: filters.legalEntity,
          gl_segment: filters.glSegment,
        }),
        getRiskOpsCategories(),
      ]);
      setPanels(mapApiToEntityPanels(metrics));
      setRiskCats(cats.categories);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load dashboard data.';
      console.warn('[App] Dashboard load failed:', err);
      setLoadError(message);
    } finally {
      setLastRun(new Date());
      setIsLoading(false);
    }
  }, [filters]);

  const navigateTo = useCallback((view: ViewId, riskCat?: string) => {
    setCurrentView(view);
    if (riskCat) setRiskFilter(riskCat);
    else setRiskFilter(null);
  }, []);

  const goHome = useCallback(() => {
    setCurrentView('command-center');
    setRiskFilter(null);
  }, []);

  const activeAgent = useMemo(() => {
    if (!currentView.startsWith('agent-')) return null;
    return agents.find((a) => a.viewId === currentView) || null;
  }, [currentView]);

  const canViewUsers = user?.permissions?.users?.view ?? false;
  const canViewSettings = user?.permissions?.settings?.view ?? false;

  const uiCtx = buildUIContext(newUI, toggleNewUI);

  return (
    <UIContext.Provider value={uiCtx}>
    <div className="app-layout" data-theme={newUI ? 'dark' : undefined}>
      <NavBar
        currentView={currentView}
        onNavigate={(view) => navigateTo(view)}
        onOpenSettings={() => setShowAdminSettings(true)}
        onLogout={logout}
        agents={agents}
        currentUser={user}
        canViewUsers={canViewUsers}
        canViewSettings={canViewSettings}
        newUI={newUI}
        onToggleNewUI={toggleNewUI}
      />

      <main className="app-main">
        <div className="dashboard-container">
          {currentView === 'command-center' && <CommandCenter onNavigate={navigateTo} />}

          {currentView === 'dashboard' && (
            <>
              <Header
                filters={filters}
                onFilterChange={setFilters}
                onRun={handleRun}
                isLoading={isLoading}
                lastRun={lastRun}
                onOpenConfigFilters={() => setShowConfigureFilters(true)}
              />
              {loadError && (
                <div
                  role="alert"
                  style={{
                    margin: '0 0 16px',
                    padding: '12px 16px',
                    border: '1.5px solid #fca5a5',
                    background: '#fef2f2',
                    color: '#991b1b',
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 600,
                  }}
                >
                  {loadError} Click Run to retry.
                </div>
              )}
              {panels && riskCats ? (
                <Dashboard
                  panels={panels}
                  riskCategories={riskCats}
                  isLoading={isLoading}
                  onNavigateToTimeOps={() => navigateTo('timeops')}
                  onNavigateToRiskOps={(cat) => navigateTo('riskops', cat)}
                  onOpenAlertQueue={() => navigateTo('alert-queue')}
                />
              ) : (
                <div>
                  <RiskCategoriesSkeleton />
                  <DashboardSkeleton />
                  {!isLoading && !loadError && (
                    <div
                      style={{
                        marginTop: 16,
                        padding: '12px 16px',
                        background: '#f8fafc',
                        border: '1px dashed #cbd5e1',
                        borderRadius: 10,
                        color: '#475569',
                        fontSize: 13,
                        textAlign: 'center',
                      }}
                    >
                      Select filters and click Run to load dashboard data.
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {currentView === 'timeops' && <TimeOps onBack={goHome} />}
          {currentView === 'riskops' && <RiskOps onBack={goHome} initialFilter={riskFilter} />}
          {currentView === 'user-management' && canViewUsers && <UserManagement onBack={goHome} />}
          {currentView === 'client-management' && user?.role === 'super_admin' && <ClientManagement onBack={goHome} />}
          {currentView === 'agent-vms-reconciliation-live' && <VMSReconLive onBack={goHome} />}
          {currentView === 'alert-queue' && <AlertQueue onBack={goHome} />}
          {currentView === 'agent-settings' && canViewSettings && <AgentSettings onBack={goHome} />}
          {activeAgent && currentView !== 'agent-vms-reconciliation-live' && currentView !== 'agent-time-anomaly' && <AgentPlanView agent={activeAgent} onBack={goHome} />}
          {currentView === 'agent-time-anomaly' && <AlertQueue onBack={goHome} />}
        </div>
      </main>

      {showAdminSettings && <AdminSettings onClose={() => setShowAdminSettings(false)} />}
      {showConfigureFilters && <ConfigureFilters onClose={() => setShowConfigureFilters(false)} />}
      <ChatWidget />
    </div>
    </UIContext.Provider>
  );
}

function AppGate() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#080d1a', color: '#94a3b8', fontFamily: "'Inter', sans-serif",
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 24, marginBottom: 8, animation: 'spin 1s linear infinite', display: 'inline-block' }}>⏳</div>
          <div>Loading...</div>
        </div>
      </div>
    );
  }

  if (!user) return <Login />;
  return <AuthenticatedApp />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppGate />
    </AuthProvider>
  );
}
