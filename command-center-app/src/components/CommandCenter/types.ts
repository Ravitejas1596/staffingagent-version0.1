export type AgentId =
  | 'vms_reconciliation'
  | 'time_anomaly'
  | 'invoice_matching'
  | 'payment_prediction'
  | 'collections_comms'
  | 'compliance_monitor';

export type AgentStatus = 'active' | 'processing' | 'idle' | 'error' | 'maintenance';

export interface AgentMetrics {
  agentId: AgentId;
  displayName: string;
  status: AgentStatus;
  transactionsToday: number;
  accuracyRate: number;
  avgProcessingTimeMs: number;
  errorCount24h: number;
  lastHeartbeat: string;
  queueDepth: number;
}

export interface SummaryMetrics {
  activeAgents: number;
  totalAgents: number;
  transactionsToday: number;
  transactionsTrend: number;
  mtdCostSavings: number;
  projectedMonthlySavings: number;
  queueDepth: number;
  queueStatus: 'normal' | 'elevated' | 'critical';
  errorRate: number;
  errorRateTrend: number;
  lastUpdated: string;
}

export interface ROIMetrics {
  mtdCostSavings: number;
  mtdCostSavingsTrend: number;
  laborHoursSaved: number;
  laborHoursTrend: number;
  disputeReduction: number;
  disputesPrevented: number;
  dsoImprovement: number;
  cashVelocityImpact: number;
  periodStart: string;
  periodEnd: string;
}

export interface QualityMetrics {
  firstPassAccuracy: number;
  autoResolutionRate: number;
  humanOverrideRate: number;
  falsePositiveRate: number;
}

export interface TransactionVolumeData {
  date: string;
  vmsReconciliation: number;
  invoiceMatching: number;
  collections: number;
  timeAnomaly: number;
}

export interface ProcessingTimeDistribution {
  bucket: string;
  count: number;
}

export interface CumulativeSavings {
  month: string;
  actual: number | null;
  projected: number | null;
}

export interface AgentUtilization {
  agentId: AgentId;
  displayName: string;
  utilizationPercent: number;
}

export type ActivityType = 'success' | 'processing' | 'alert' | 'error';

export interface ActivityItem {
  id: string;
  type: ActivityType;
  title: string;
  agentId: AgentId;
  agentDisplayName: string;
  detail: string;
  timestamp: string;
  customerId?: string;
  entityType?: 'timesheet' | 'invoice' | 'placement' | 'credential';
  entityId?: string;
}

export interface PendingPlanApproval {
  runId: string;
  agentId: AgentId;
  agentDisplayName: string;
  actionCount: number;
  totalFinancialImpact: number;
  maxSeverity: string | null;
  createdAt: string;
}

export interface PendingResultReview {
  agentId: AgentId;
  agentDisplayName: string;
  pendingCount: number;
  totalFinancialImpact: number;
  maxSeverity: string | null;
  oldestItemAt: string;
}

export interface ActionQueue {
  planApprovals: PendingPlanApproval[];
  resultReviews: PendingResultReview[];
  totalItems: number;
}

export interface DashboardSnapshot {
  summary: SummaryMetrics;
  agents: AgentMetrics[];
  roi: ROIMetrics;
  quality: QualityMetrics;
  charts: {
    transactionVolume: TransactionVolumeData[];
    processingTime: ProcessingTimeDistribution[];
    cumulativeSavings: CumulativeSavings[];
    utilization: AgentUtilization[];
  };
  recentActivity: ActivityItem[];
  actionQueue: ActionQueue | null;
  generatedAt: string;
}

export const AGENT_COLORS: Record<AgentId, string> = {
  vms_reconciliation: '#06b6d4',
  time_anomaly: '#8b5cf6',
  invoice_matching: '#10b981',
  payment_prediction: '#f59e0b',
  collections_comms: '#ec4899',
  compliance_monitor: '#6366f1',
};

export const AGENT_DISPLAY_NAMES: Record<AgentId, string> = {
  vms_reconciliation: 'VMS Reconciliation',
  time_anomaly: 'Time Anomaly Detection',
  invoice_matching: 'Invoice Matching',
  payment_prediction: 'Payment Prediction',
  collections_comms: 'Collections Comms',
  compliance_monitor: 'Compliance Monitor',
};

export const AGENT_ICONS: Record<AgentId, string> = {
  time_anomaly: '⏱️',
  vms_reconciliation: '🔄',
  invoice_matching: '🧾',
  payment_prediction: '📊',
  collections_comms: '💰',
  compliance_monitor: '📋',
};

/** Maps Command Center AgentId to the ViewId used by App.tsx routing */
export const AGENT_VIEW_MAP: Record<AgentId, import('../../types').ViewId> = {
  time_anomaly: 'agent-time-anomaly',
  vms_reconciliation: 'agent-vms-reconciliation',
  invoice_matching: 'agent-invoice-matching',
  payment_prediction: 'agent-payment-prediction',
  collections_comms: 'agent-collections',
  compliance_monitor: 'agent-compliance',
};

/** Maps Command Center AgentId to the API agent-type slug used by POST /agents/{type}/plan */
export const AGENT_API_TYPE: Record<AgentId, string> = {
  time_anomaly: 'time-anomaly',
  vms_reconciliation: 'vms-reconciliation',
  invoice_matching: 'invoice-matching',
  payment_prediction: 'payment-prediction',
  collections_comms: 'collections',
  compliance_monitor: 'compliance',
};
