import { useState, useEffect, useCallback, useRef } from 'react';
import { getDashboardSnapshot } from '../../api/client';
import type { DashboardSnapshot } from './types';

const POLL_INTERVAL = 30_000;

interface UseCommandCenterDataReturn {
  data: DashboardSnapshot | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export default function useCommandCenterData(): UseCommandCenterDataReturn {
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true);
    try {
      const raw = await getDashboardSnapshot();
      if (!mountedRef.current) return;
      setData(raw as unknown as DashboardSnapshot);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : 'Failed to fetch dashboard data');
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchData(true);

    const interval = setInterval(() => fetchData(false), POLL_INTERVAL);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchData]);

  const refetch = useCallback(() => fetchData(false), [fetchData]);

  return { data, isLoading, error, refetch };
}
