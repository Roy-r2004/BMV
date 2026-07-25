import { apiClient, getAdminHeaders } from './client';

const ACCESS_KEY = (requestId: number) => `bmv_request_access_${requestId}`;

export function storeRequestAccessToken(requestId: number, token: string | null | undefined) {
  if (!token) return;
  try {
    sessionStorage.setItem(ACCESS_KEY(requestId), token);
  } catch {
    /* ignore */
  }
}

export function getRequestAccessToken(requestId: number): string | null {
  try {
    return sessionStorage.getItem(ACCESS_KEY(requestId));
  } catch {
    return null;
  }
}

function customerHeaders(requestId: number) {
  const token = getRequestAccessToken(requestId);
  return token ? { 'X-Request-Access-Token': token } : {};
}

export type CustomerExpandedStatus =
  | 'requested'
  | 'under_review'
  | 'approved'
  | 'generating'
  | 'ready'
  | 'rejected'
  | 'failed';

export interface ExpandedPreviewCustomerView {
  expanded_preview_id: number;
  request_id: number;
  status: CustomerExpandedStatus;
  lifecycle_status: string;
  reason?: string | null;
  requested_changes?: string | null;
  contact_preference?: string | null;
  created_at: string;
  updated_at: string;
  published_preview_url?: string | null;
  can_open_published: boolean;
}

export interface ExpandedPreviewListItem {
  id: number;
  request_id: number;
  current_status: string;
  business_name?: string | null;
  customer_email?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExpandedPreviewAdminView {
  id: number;
  expanded_preview_uuid: string;
  request_id: number;
  current_status: string;
  customer_reason?: string | null;
  requested_changes?: string | null;
  contact_preference?: string | null;
  actor_id: string;
  accepted_tier_1_revision_id?: number | null;
  tier_2_candidate_revision_id?: number | null;
  published_candidate_revision_id?: number | null;
  generation_error?: string | null;
  generation_started_at?: string | null;
  generation_finished_at?: string | null;
  created_at: string;
  updated_at: string;
  business_name?: string | null;
  customer_email?: string | null;
  tier_1_preview_url?: string | null;
  tier_2_preview_url?: string | null;
  published_preview_url?: string | null;
  phase4_status?: string | null;
  phase5_status?: string | null;
  routes: string[];
  screenshot_count: number;
  warning_count: number;
  blocking_finding_count: number;
  timeline: Array<{
    id: number;
    from_status: string | null;
    to_status: string;
    actor_id: string;
    actor_role: string;
    reason?: string | null;
    internal_notes?: string | null;
    created_at: string;
    event_sha256: string;
  }>;
}

export async function getExpandedPreview(
  requestId: number,
): Promise<ExpandedPreviewCustomerView | null> {
  const { data } = await apiClient.get(`/api/requests/${requestId}/expanded-preview`, {
    headers: customerHeaders(requestId),
  });
  return data;
}

export async function requestExpandedPreview(
  requestId: number,
  body: {
    reason?: string;
    requested_changes?: string;
    contact_preference?: string;
    idempotency_key?: string;
  },
): Promise<ExpandedPreviewCustomerView> {
  const { data } = await apiClient.post(
    `/api/requests/${requestId}/expanded-preview`,
    body,
    { headers: customerHeaders(requestId) },
  );
  return data;
}

export async function listExpandedPreviews(params?: {
  status?: string;
  limit?: number;
}): Promise<ExpandedPreviewListItem[]> {
  const { data } = await apiClient.get('/api/admin/expanded-previews', {
    headers: getAdminHeaders(),
    params,
  });
  return data;
}

export async function getExpandedPreviewAdmin(
  id: number,
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.get(`/api/admin/expanded-previews/${id}`, {
    headers: getAdminHeaders(),
  });
  return data;
}

export async function approveExpandedPreview(
  id: number,
  body: { reason?: string; internal_notes?: string },
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.post(
    `/api/admin/expanded-previews/${id}/approve`,
    body,
    { headers: getAdminHeaders() },
  );
  return data;
}

export async function rejectExpandedPreview(
  id: number,
  body: { reason: string; internal_notes?: string },
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.post(
    `/api/admin/expanded-previews/${id}/reject`,
    body,
    { headers: getAdminHeaders() },
  );
  return data;
}

export async function startExpandedPreviewGeneration(
  id: number,
  body: { reason?: string; confirm: boolean },
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.post(
    `/api/admin/expanded-previews/${id}/start-generation`,
    body,
    { headers: getAdminHeaders() },
  );
  return data;
}

export async function reviewExpandedPreview(
  id: number,
  body: {
    outcome: 'review_accepted' | 'review_rejected';
    reason?: string;
    internal_notes?: string;
    confirm: boolean;
  },
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.post(
    `/api/admin/expanded-previews/${id}/review`,
    body,
    { headers: getAdminHeaders() },
  );
  return data;
}

export async function publishExpandedPreview(
  id: number,
  body: { reason?: string; confirm: boolean },
): Promise<ExpandedPreviewAdminView> {
  const { data } = await apiClient.post(
    `/api/admin/expanded-previews/${id}/publish`,
    body,
    { headers: getAdminHeaders() },
  );
  return data;
}
