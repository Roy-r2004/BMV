import { useEffect, useState } from 'react';
import { getAiStatus, type AiStatus } from '../api/ai';

export function useAiStatus(pollMs = 15000) {
  const [status, setStatus] = useState<AiStatus | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const next = await getAiStatus();
        if (active) setStatus(next);
      } catch {
        if (active) {
          setStatus({
            ready: true,
            provider: 'unknown',
            ollama_reachable: false,
            message: 'AI status unavailable — generation may still proceed.',
            required_models: [],
            installed_models: [],
            missing_models: [],
            models_ready_count: 0,
            models_required_count: 0,
          });
        }
      }
    };

    load();
    const timer = setInterval(load, pollMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [pollMs]);

  return status;
}
