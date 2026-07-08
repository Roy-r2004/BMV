import { useCallback, useEffect, useState } from 'react';
import { getSolutionWorkspace, resetSolutionWorkspace } from '../api/solutionWorkspace';
import type { SolutionOverlay } from '../types/auth';
import { hasOverlayCustomizations } from '../utils/mergeShowcaseOverlay';

export function useSolutionWorkspace(solutionId: string, enabled: boolean) {
  const [overlay, setOverlay] = useState<SolutionOverlay>({});
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setOverlay({});
      return;
    }
    setLoading(true);
    try {
      const data = await getSolutionWorkspace(solutionId);
      setOverlay(data ?? {});
    } catch {
      setOverlay({});
    } finally {
      setLoading(false);
    }
  }, [solutionId, enabled]);

  const reset = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      const data = await resetSolutionWorkspace(solutionId);
      setOverlay(data ?? {});
    } finally {
      setLoading(false);
    }
  }, [solutionId, enabled]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    overlay,
    setOverlay,
    loading,
    refresh,
    reset,
    hasCustomizations: hasOverlayCustomizations(overlay),
  };
}
