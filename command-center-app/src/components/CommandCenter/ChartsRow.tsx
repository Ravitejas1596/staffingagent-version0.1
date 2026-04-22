import {
  LineChart, Line, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type {
  TransactionVolumeData,
  ProcessingTimeDistribution,
  CumulativeSavings,
  AgentUtilization,
} from './types';
import { AGENT_COLORS } from './types';

interface ChartsRowProps {
  transactionVolume: TransactionVolumeData[];
  processingTime: ProcessingTimeDistribution[];
  cumulativeSavings: CumulativeSavings[];
  utilization: AgentUtilization[];
  isLoading: boolean;
}

const AXIS_STYLE = { fill: '#94a3b8', fontFamily: "'Outfit', sans-serif", fontSize: 12 };
const GRID_COLOR = 'rgba(42, 54, 73, 0.5)';
const TOOLTIP_STYLE = { background: '#1a2332', border: '1px solid #2a3649', borderRadius: 8, color: '#f1f5f9' };

const PROCESSING_COLORS = [
  'rgba(16, 185, 129, 0.8)',
  'rgba(6, 182, 212, 0.8)',
  'rgba(139, 92, 246, 0.8)',
  'rgba(245, 158, 11, 0.8)',
  'rgba(249, 115, 22, 0.8)',
  'rgba(239, 68, 68, 0.8)',
];

const UTIL_COLORS = Object.values(AGENT_COLORS);

function ChartSkeleton() {
  return (
    <div className="cc-chart-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="cc-skeleton" style={{ width: '90%', height: '80%' }} />
    </div>
  );
}

export function TransactionVolumeChart({ data, isLoading }: { data: TransactionVolumeData[]; isLoading: boolean }) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">📈</div>
          Transaction Volume (7 Days)
        </div>
      </div>
      {isLoading ? <ChartSkeleton /> : (
        <div className="cc-chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="date" tick={AXIS_STYLE} axisLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#94a3b8' }} />
              <Legend iconType="circle" wrapperStyle={{ paddingTop: 12, fontSize: 12 }} />
              <Line type="monotone" dataKey="vmsReconciliation" name="VMS Recon" stroke={AGENT_COLORS.vms_reconciliation} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="invoiceMatching" name="Invoice Match" stroke={AGENT_COLORS.invoice_matching} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="collections" name="Collections" stroke={AGENT_COLORS.collections_comms} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="timeAnomaly" name="Time Anomaly" stroke={AGENT_COLORS.time_anomaly} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function ProcessingTimeChart({ data, isLoading }: { data: ProcessingTimeDistribution[]; isLoading: boolean }) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">⏱️</div>
          Processing Time Distribution
        </div>
      </div>
      {isLoading ? <ChartSkeleton /> : (
        <div className="cc-chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="bucket" tick={AXIS_STYLE} axisLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={PROCESSING_COLORS[i % PROCESSING_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function CumulativeSavingsChart({ data, isLoading }: { data: CumulativeSavings[]; isLoading: boolean }) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">💵</div>
          Cumulative Savings (YTD)
        </div>
      </div>
      {isLoading ? <ChartSkeleton /> : (
        <div className="cc-chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="month" tick={AXIS_STYLE} axisLine={false} />
              <YAxis tick={AXIS_STYLE} axisLine={false} tickFormatter={(v: number) => `$${v}K`} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v) => v != null ? [`$${v}K`, ''] : ['—', '']}
              />
              <Legend iconType="circle" wrapperStyle={{ paddingTop: 12, fontSize: 12 }} />
              <Area type="monotone" dataKey="actual" name="Actual" stroke="#10b981" fill="rgba(16, 185, 129, 0.1)" strokeWidth={2} connectNulls={false} />
              <Area type="monotone" dataKey="projected" name="Projected" stroke="#10b981" fill="none" strokeWidth={2} strokeDasharray="5 5" connectNulls={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function AgentUtilizationChart({ data, isLoading }: { data: AgentUtilization[]; isLoading: boolean }) {
  return (
    <div className="cc-card">
      <div className="cc-card-header">
        <div className="cc-card-title">
          <div className="cc-card-title-icon">⚡</div>
          Agent Utilization
        </div>
      </div>
      {isLoading ? <ChartSkeleton /> : (
        <div className="cc-chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="utilizationPercent"
                nameKey="displayName"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={2}
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={UTIL_COLORS[i % UTIL_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v) => [`${v}%`, 'Utilization']}
              />
              <Legend iconType="circle" layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function ChartsRow({ transactionVolume, processingTime, isLoading }: Pick<ChartsRowProps, 'transactionVolume' | 'processingTime' | 'isLoading'>) {
  return (
    <section className="cc-charts-row">
      <TransactionVolumeChart data={transactionVolume} isLoading={isLoading} />
      <ProcessingTimeChart data={processingTime} isLoading={isLoading} />
    </section>
  );
}
