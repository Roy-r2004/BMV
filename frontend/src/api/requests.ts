import { apiClient } from './client';
import type { ChatMessage, ChatSendResponse, PreviewResponse } from '../types/request';
import type { BuildRequestContact } from '../types/buildRequest';

export async function createRequest(formData: FormData): Promise<{ id: number; status: string }> {
  // The backend now returns immediately and runs generation in the background —
  // the frontend polls /preview and /progress to track completion.
  const { data } = await apiClient.post('/api/requests', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  });
  return data;
}

export async function getPreview(id: number): Promise<PreviewResponse> {
  const { data } = await apiClient.get(`/api/requests/${id}/preview`);
  return data;
}

export async function requestBuild(id: number, contact: BuildRequestContact): Promise<{ id: number; build_requested: boolean; status: string }> {
  const { data } = await apiClient.post(`/api/requests/${id}/request-build`, contact);
  return data;
}

export async function getChatHistory(id: number): Promise<ChatMessage[]> {
  const { data } = await apiClient.get(`/api/requests/${id}/chat`);
  return data.messages;
}

export async function sendChatMessage(id: number, message: string): Promise<ChatSendResponse> {
  const { data } = await apiClient.post(
    `/api/requests/${id}/chat`,
    { message },
    { timeout: 600000 },
  );
  return data;
}
