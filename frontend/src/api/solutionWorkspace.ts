import { apiClient } from './client';
import { getUserAuthHeaders } from './auth';
import type { SolutionChatSendResponse, SolutionEditMessage, SolutionOverlay } from '../types/auth';
import type { AIFeatureCatalogItem } from '../data/aiFeatureCatalog';

export async function getSolutionWorkspace(solutionId: string): Promise<SolutionOverlay> {
  const { data } = await apiClient.get<{ overlay: SolutionOverlay }>(
    `/api/solutions/${solutionId}/workspace`,
    { headers: getUserAuthHeaders() },
  );
  return data.overlay ?? {};
}

export async function getSolutionChat(solutionId: string): Promise<{
  messages: SolutionEditMessage[];
  overlay: SolutionOverlay;
}> {
  const { data } = await apiClient.get<{ messages: SolutionEditMessage[]; overlay: SolutionOverlay }>(
    `/api/solutions/${solutionId}/chat`,
    { headers: getUserAuthHeaders() },
  );
  return data;
}

export async function sendSolutionChat(
  solutionId: string,
  message: string,
  attachment?: File | null,
): Promise<SolutionChatSendResponse> {
  const form = new FormData();
  form.append('message', message);
  if (attachment) form.append('attachment', attachment);

  const { data } = await apiClient.post<SolutionChatSendResponse>(
    `/api/solutions/${solutionId}/chat`,
    form,
    { headers: getUserAuthHeaders() },
  );
  return data;
}

/** Clear only the signed-in user's personal copy for this solution */
export async function resetSolutionWorkspace(solutionId: string): Promise<SolutionOverlay> {
  const { data } = await apiClient.post<{ overlay: SolutionOverlay }>(
    `/api/solutions/${solutionId}/workspace/reset`,
    null,
    { headers: getUserAuthHeaders() },
  );
  return data.overlay ?? {};
}

export async function getAIFeatureCatalog(solutionId: string): Promise<AIFeatureCatalogItem[]> {
  const { data } = await apiClient.get<{ features: AIFeatureCatalogItem[] }>(
    `/api/solutions/${solutionId}/catalog`,
    { headers: getUserAuthHeaders() },
  );
  return data.features ?? [];
}

export interface IntegrateFeatureResponse {
  reply: string;
  changes_made: string[];
  overlay: SolutionOverlay;
  feature_id: string;
  integrated: boolean;
}

export async function integrateAIFeature(
  solutionId: string,
  featureId: string,
): Promise<IntegrateFeatureResponse> {
  const { data } = await apiClient.post<IntegrateFeatureResponse>(
    `/api/solutions/${solutionId}/catalog/${featureId}/integrate`,
    null,
    { headers: getUserAuthHeaders() },
  );
  return data;
}

export async function removeAIFeature(
  solutionId: string,
  featureId: string,
): Promise<IntegrateFeatureResponse> {
  const { data } = await apiClient.post<IntegrateFeatureResponse>(
    `/api/solutions/${solutionId}/catalog/${featureId}/remove`,
    null,
    { headers: getUserAuthHeaders() },
  );
  return data;
}
