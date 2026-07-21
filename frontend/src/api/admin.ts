import { apiClient, getAdminHeaders } from './client';
import type { RequestDetail, RequestListItem } from '../types/request';

export type AdminActionItem = {
  request_id: number;
  business_name: string;
  status: string;
  stage?: string | null;
  pct?: number | null;
  label?: string | null;
  cost_usd?: number;
  email?: string;
  updated_at?: string | null;
  kind: string;
  priority: number;
  reason: string;
};

export type AdminAlert = {
  id: number;
  created_at: string | null;
  kind: string;
  severity: string;
  title: string;
  body: string | null;
  request_id: number | null;
  acknowledged: boolean;
};

export type AdminOverview = {
  provider: string;
  ai_enabled: boolean;
  site_chat_enabled: boolean;
  daily_budget_usd: number | null;
  request_budget_usd?: number | null;
  budget_remaining_usd: number | null;
  requests_total: number;
  requests_today: number;
  by_status: Record<string, number>;
  cost_today_usd: number;
  cost_7d_usd: number;
  tokens_today: number;
  calls_today: number;
  failed_today: number;
  unread_alerts?: number;
  action_queue?: AdminActionItem[];
  alerts?: AdminAlert[];
  top_models_today: Array<{
    model: string;
    calls: number;
    cost_usd: number;
    tokens: number;
  }>;
  recent_failures: AiUsageEvent[];
  recent_usage: AiUsageEvent[];
};

export type AiUsageEvent = {
  id: number;
  created_at: string | null;
  provider: string;
  model: string;
  purpose: string;
  request_id: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  success: boolean;
  error: string | null;
  latency_ms: number | null;
};

export type AdminSettings = {
  ai_enabled: boolean;
  site_chat_enabled: boolean;
  daily_budget_usd: number | null;
  request_budget_usd?: number | null;
  updated_at?: string | null;
};

export type AdminLoginResult = {
  success: boolean;
  message: string;
  token?: string | null;
  user?: { id: number; name: string; email: string; is_admin?: boolean } | null;
};

export async function adminLogin(
  password: string,
  email?: string,
): Promise<AdminLoginResult> {
  const { data } = await apiClient.post<AdminLoginResult>('/api/admin/login', {
    password,
    email: email?.trim() || undefined,
  });
  return data;
}

export function clearAdminSession() {
  sessionStorage.removeItem('admin_password');
  sessionStorage.removeItem('admin_token');
  sessionStorage.removeItem('admin_email');
}

export function hasAdminSession(): boolean {
  return Boolean(sessionStorage.getItem('admin_token') || sessionStorage.getItem('admin_password'));
}

export function persistAdminSession(result: AdminLoginResult, passwordFallback?: string) {
  if (result.token) {
    sessionStorage.setItem('admin_token', result.token);
    sessionStorage.removeItem('admin_password');
    if (result.user?.email) sessionStorage.setItem('admin_email', result.user.email);
  } else if (passwordFallback) {
    sessionStorage.setItem('admin_password', passwordFallback);
    sessionStorage.removeItem('admin_token');
  }
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const { data } = await apiClient.get('/api/admin/overview', {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function getAdminSettings(): Promise<AdminSettings> {
  const { data } = await apiClient.get('/api/admin/settings', {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function updateAdminSettings(body: {
  ai_enabled?: boolean;
  site_chat_enabled?: boolean;
  daily_budget_usd?: number | null;
  clear_daily_budget?: boolean;
  request_budget_usd?: number | null;
  clear_request_budget?: boolean;
}): Promise<AdminSettings> {
  const { data } = await apiClient.patch('/api/admin/settings', body, {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function ackAdminAlert(id: number): Promise<void> {
  await apiClient.post(`/api/admin/alerts/${id}/ack`, null, { headers: getAdminHeaders() });
}

export async function ackAllAdminAlerts(): Promise<void> {
  await apiClient.post('/api/admin/alerts/ack-all', null, { headers: getAdminHeaders() });
}

export async function cancelRequestGeneration(id: number): Promise<void> {
  await apiClient.post(`/api/admin/requests/${id}/cancel-generation`, null, {
    headers: getAdminHeaders(),
  });
}

export async function listAdminUsage(days = 7, limit = 200): Promise<{ days: number; events: AiUsageEvent[] }> {
  const { data } = await apiClient.get('/api/admin/usage', {
    headers: getAdminHeaders(),
    params: { days, limit },
  });
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

export type RequestRunLog = {
  request_id: number;
  business_name: string;
  status: string;
  cost_usd: number;
  tokens: number;
  calls: number;
  failed_calls: number;
  is_generating?: boolean;
  cancel_requested?: boolean;
  by_purpose: Array<{ key: string; calls: number; cost_usd: number; tokens: number; failed: number }>;
  by_model: Array<{ key: string; calls: number; cost_usd: number; tokens: number; failed: number }>;
  usage_events: AiUsageEvent[];
  progress: {
    stage?: string;
    label?: string;
    pct?: number;
    detail?: string;
    files_done?: number;
    files_total?: number;
    updated_at?: string;
    log?: Array<{ t?: number; msg?: string; detail?: string; stage?: string; pct?: number }>;
  };
  timeline: Array<{
    kind: 'progress' | 'ai';
    at: number | null;
    message: string;
    detail?: string;
    cost_usd?: number | null;
    tokens?: number | null;
    latency_ms?: number | null;
    success?: boolean;
    event_id?: number;
  }>;
};

export async function getRequestRunLog(id: number): Promise<RequestRunLog> {
  const { data } = await apiClient.get(`/api/admin/requests/${id}/run-log`, {
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

export async function deleteRequest(id: number): Promise<{ success: boolean; deleted_id: number; label: string }> {
  const { data } = await apiClient.delete(`/api/admin/requests/${id}`, {
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
  const base = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8001');
  const password = sessionStorage.getItem('admin_password') || '';
  return `${base}/api/admin/requests/${id}/file?admin_password=${encodeURIComponent(password)}`;
}
