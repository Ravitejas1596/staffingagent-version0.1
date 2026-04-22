import { useState, useCallback, useEffect, useRef } from 'react';
import './commandCenter.css';
import useCommandCenterData from './useCommandCenterData';
import SummaryRow from './SummaryRow';
import ActionQueue from './ActionQueue';
import AgentFleetPanel from './AgentFleetPanel';
import type { AgentCardState } from './AgentFleetPanel';
import ROIPanel from './ROIPanel';
import QualityMetrics from './QualityMetrics';
import ChartsRow, { CumulativeSavingsChart, AgentUtilizationChart } from './ChartsRow';
import ActivityFeed from './ActivityFeed';
import type { AgentId } from './types';
import { AGENT_API_TYPE } from './types';
import { createAgentPlan } from '../../api/client';
import type { ViewId } from '../../types';

interface CommandCenterProps {
  onNavigate?: (view: ViewId) => void;
}

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

let toastCounter = 0;

export default function CommandCenter({ onNavigate }: CommandCenterProps) {
  const { data, isLoading, error, refetch } = useCommandCenterData();
  const [agentStates, setAgentStates] = useState<Record<string, AgentCardState>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const addToast = useCallback((type: 'success' | 'error', message: string) => {
    const id = ++toastCounter;
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => {
      if (mountedRef.current) {
        setToasts(prev => prev.filter(t => t.id !== id));
      }
    }, 5000);
  }, []);

  const setCardState = useCallback((agentId: string, state: AgentCardState) => {
    setAgentStates(prev => ({ ...prev, [agentId]: state }));
  }, []);

  const handleRunAgent = useCallback(async (agentId: AgentId) => {
    const apiType = AGENT_API_TYPE[agentId];
    if (!apiType) return;

    setCardState(agentId, 'running');
    try {
      await createAgentPlan(apiType);
      if (!mountedRef.current) return;
      setCardState(agentId, 'success');
      addToast('success', `Plan ready for review — check Action Queue`);
      refetch();
      setTimeout(() => {
        if (mountedRef.current) setCardState(agentId, 'idle');
      }, 3000);
    } catch (e) {
      if (!mountedRef.current) return;
      setCardState(agentId, 'error');
      addToast('error', `Failed to create plan: ${e instanceof Error ? e.message : 'Unknown error'}`);
      setTimeout(() => {
        if (mountedRef.current) setCardState(agentId, 'idle');
      }, 3000);
    }
  }, [setCardState, addToast, refetch]);

  const handleNavigate = (view: ViewId) => {
    onNavigate?.(view);
  };

  return (
    <div className="command-center">
      <div className="cc-bg-grid" />
      <div className="cc-bg-gradient" />

      {toasts.length > 0 && (
        <div className="cc-toast-container">
          {toasts.map(t => (
            <div key={t.id} className={`cc-toast cc-toast--${t.type}`}>
              <span className="cc-toast-icon">{t.type === 'success' ? '✓' : '✕'}</span>
              {t.message}
            </div>
          ))}
        </div>
      )}

      <div className="cc-main">
        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 12,
            padding: '12px 20px',
            marginBottom: 24,
            color: '#fca5a5',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{ fontSize: 16 }}>⚠</span>
            {error}
          </div>
        )}

        <SummaryRow data={data?.summary ?? null} isLoading={isLoading} />

        <ActionQueue
          data={data?.actionQueue ?? null}
          isLoading={isLoading}
          onNavigate={handleNavigate}
        />

        <section className="cc-dashboard-grid">
          <AgentFleetPanel
            agents={data?.agents ?? []}
            isLoading={isLoading}
            agentStates={agentStates}
            onRunAgent={handleRunAgent}
            onNavigate={handleNavigate}
          />
          <ROIPanel data={data?.roi ?? null} isLoading={isLoading} />
        </section>

        <QualityMetrics data={data?.quality ?? null} isLoading={isLoading} />

        <ChartsRow
          transactionVolume={data?.charts?.transactionVolume ?? []}
          processingTime={data?.charts?.processingTime ?? []}
          isLoading={isLoading}
        />

        <section className="cc-bottom-row">
          <ActivityFeed items={data?.recentActivity ?? []} isLoading={isLoading} />
          <CumulativeSavingsChart data={data?.charts?.cumulativeSavings ?? []} isLoading={isLoading} />
          <AgentUtilizationChart data={data?.charts?.utilization ?? []} isLoading={isLoading} />
        </section>
      </div>
    </div>
  );
}
