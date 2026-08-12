import axios from 'axios';

// The image-demo pipeline is its own service (consultant-service), separate
// from the main backend — its own port, its own ledger, its own uploads.
// Asset paths it returns ("/uploads/...") are relative to THIS base, never
// to VITE_API_BASE_URL.
export const CONSULTANT_API_BASE =
  import.meta.env.VITE_CONSULTANT_API_BASE_URL ??
  (import.meta.env.PROD ? '' : 'http://localhost:8002');

const consultantClient = axios.create({ baseURL: CONSULTANT_API_BASE });

export function consultantAssetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${CONSULTANT_API_BASE}${path}`;
}

export interface StudioIntake {
  business_name: string;
  business_description: string;
  email: string;
  industry?: string;
  main_problem?: string;
}

export interface StudioProgress {
  stage: string | null;
  label: string | null;
  pct: number | null;
  detail: string | null;
  is_generating: boolean;
  is_failed: boolean;
  updated_at: string | null;
}

export interface StudioScreen {
  role_id: string;
  role_label: string;
  image_url: string;
  variant: number;
  hero_url: string | null;
  detail_urls: string[];
}

export interface StudioAiFeature {
  id: string;
  name: string;
  description: string;
}

export interface StudioPreview {
  id: number;
  business_name: string;
  concept_name: string | null;
  preview_summary: string | null;
  ai_features: StudioAiFeature[];
  generated_pages: { attraction_images: StudioScreen[] };
  status: string;
  is_generating: boolean;
}

export async function createStudioRequest(intake: StudioIntake): Promise<{ id: number; status: string }> {
  const form = new FormData();
  form.set('business_name', intake.business_name);
  form.set('business_description', intake.business_description);
  form.set('email', intake.email);
  if (intake.industry) form.set('industry', intake.industry);
  if (intake.main_problem) form.set('main_problem', intake.main_problem);
  const { data } = await consultantClient.post('/api/requests', form, { timeout: 30000 });
  return data;
}

export async function getStudioProgress(id: number): Promise<StudioProgress> {
  const { data } = await consultantClient.get(`/api/requests/${id}/progress`);
  return data;
}

export async function getStudioPreview(id: number): Promise<StudioPreview> {
  const { data } = await consultantClient.get(`/api/requests/${id}/preview`);
  return data;
}

/** The service returns 429 when the studio is at generation capacity. */
export function isAtCapacity(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 429;
}
