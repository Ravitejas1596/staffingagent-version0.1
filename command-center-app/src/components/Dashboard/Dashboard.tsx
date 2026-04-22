import EntityPanel from '../EntityPanel/EntityPanel';
import RiskPanel from '../RiskPanel/RiskPanel';
import AgentKpiCard from '../AgentKpiCard/AgentKpiCard';
import type { EntityPanelData, RiskCategory } from '../../types';
import { useUI } from '../../context/UIContext';

interface DashboardProps {
  panels: EntityPanelData[];
  riskCategories: RiskCategory[];
  isLoading: boolean;
  onNavigateToTimeOps: (filter: string) => void;
  onNavigateToRiskOps: (category: string) => void;
  onOpenAlertQueue?: () => void;
}

export default function Dashboard({ panels, riskCategories, isLoading, onNavigateToTimeOps, onNavigateToRiskOps, onOpenAlertQueue }: DashboardProps) {
  const { newUI } = useUI();
  return (
    <div className="metrics-wrapper" style={{ position: 'relative' }}>
      {isLoading && (
        <div style={{
          position: 'absolute', inset: 0,
          background: newUI ? 'rgba(15,23,42,0.7)' : 'rgba(255,255,255,0.7)',
          zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: 16, backdropFilter: 'blur(2px)',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: 40, height: 40, border: `4px solid ${newUI ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`, borderTopColor: newUI ? '#2dd4bf' : '#2563eb', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
            <div style={{ fontWeight: 700, color: newUI ? '#94a3b8' : '#475569', fontSize: 14 }}>Refreshing data...</div>
          </div>
        </div>
      )}

      <AgentKpiCard onOpenQueue={onOpenAlertQueue} />

      <div className="panel-group entity-group">
        <div className="group-badge">Entity Panels</div>
        <div className="entity-panels">
          {panels.map((panel) => (
            <EntityPanel
              key={panel.id}
              panel={panel}
              onNavigate={(filter) => {
                if (panel.type === 'time-expense') onNavigateToTimeOps(filter);
              }}
            />
          ))}
        </div>
      </div>

      <div className="panel-group risk-group">
        <RiskPanel
          riskCategories={riskCategories}
          onNavigateToTimeOps={onNavigateToTimeOps}
          onNavigateToRiskOps={onNavigateToRiskOps}
        />
      </div>
    </div>
  );
}
