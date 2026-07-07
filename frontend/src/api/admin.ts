import { apiClient, getAdminHeaders } from './client';
import type { RequestDetail, RequestListItem } from '../types/request';

export async function adminLogin(password: string): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post('/api/admin/login', { password });
  return data;
}

export async function listRequests(status?: string): Promise<RequestListItem[]> {
  const params = status && status !== 'all' ? { status } : {};
  const { data } = await apiClient.get('/api/admin/requests', {
    headers: getAdminHeaders(),
    params,
  });
  return data;
}

export async function getRequest(id: number): Promise<RequestDetail> {
  const { data } = await apiClient.get(`/api/admin/requests/${id}`, {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function updateRequest(id: number, body: Record<string, unknown>): Promise<RequestDetail> {
  const { data } = await apiClient.patch(`/api/admin/requests/${id}`, body, {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function generateAction(id: number, action: string): Promise<{ success: boolean; message: string; data?: unknown }> {
  const { data } = await apiClient.post(`/api/admin/requests/${id}/${action}`, null, {
    headers: getAdminHeaders(),
    timeout: 600000,
  });
  return data;
}

export async function getWhatsAppMessage(id: number): Promise<{ message: string }> {
  const { data } = await apiClient.get(`/api/admin/requests/${id}/whatsapp-message`, {
    headers: getAdminHeaders(),
  });
  return data;
}

export function getFileUrl(id: number): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000');
  const password = sessionStorage.getItem('admin_password') || '';
  return `${base}/api/admin/requests/${id}/file?admin_password=${encodeURIComponent(password)}`;
}
