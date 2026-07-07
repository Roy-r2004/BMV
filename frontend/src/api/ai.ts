import { apiClient } from './client';

export interface AiModelStatus {
  id: string;
  name: string;
  label: string;
  purpose: string;
  present: boolean;
}

export interface AiStatus {
  ready: boolean;
  provider?: 'ollama' | 'openrouter' | string;
  ollama_reachable: boolean;
  message: string;
  required_models: AiModelStatus[];
  installed_models: string[];
  missing_models: string[];
  models_ready_count: number;
  models_required_count: number;
  error?: string;
}

export async function getAiStatus(): Promise<AiStatus> {
  const { data } = await apiClient.get('/api/ai/status', { timeout: 10000 });
  return data;
}
