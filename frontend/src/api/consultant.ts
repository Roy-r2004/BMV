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
  business_name: string | null;
  stage: string | null;
  label: string | null;
  pct: number | null;
  detail: string | null;
  is_generating: boolean;
  is_failed: boolean;
  updated_at: string | null;
  /** Seconds since the run started, measured server-side — see the route's
   *  comment. Never derive this from a timestamp in the browser. */
  elapsed_s: number;
}

/** The AI module actually drawn on a screen. Null on the screen's story when
 *  no module was rendered — never an empty shell. */
export interface StudioScreenAi {
  title: string | null;
  headline: string;
  rationale: string | null;
  confidence: string | null;
  chips: string[];
}

/** What a screen is, read from the spec it was drawn from. Every string here
 *  is one the image was asked to render, so the explanation under a screen
 *  can be checked against the screen. Null for screens generated before the
 *  spec was persisted — which means "we cannot say", not "there is no AI". */
export interface StudioStory {
  subheading: string | null;
  tracks: string[];
  sections: string[];
  /** One composed sentence saying what the screen does. Built from the
   *  screen's own strings, never summarised — and identical to the sentence
   *  under the same screenshot in the deck. */
  description: string;
  ai: StudioScreenAi | null;
}

export interface StudioScreen {
  role_id: string;
  role_label: string;
  image_url: string;
  variant: number;
  hero_url: string | null;
  /** Still produced for the deck; the result page shows full screens only. */
  detail_urls: string[];
  story: StudioStory | null;
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
  /** What class of software this is, composed server-side from strings
   *  already on the request. Null when the plan stage has not named a
   *  concept yet — render nothing rather than something vague. */
  what_this_is: string | null;
  preview_summary: string | null;
  /** Plain strings from the consult stage, not objects. */
  preview_features: string[];
  ai_features: StudioAiFeature[];
  mvp_blueprint: string | null;
  generated_pages: { attraction_images: StudioScreen[] };
  deck_available: boolean;
  status: string;
  is_generating: boolean;
  industry: string | null;
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

/** The deck the pipeline already builds. Only offer it when the preview says
 *  `deck_available` — the route 400s before the plan stage has run. */
export function studioDeckUrl(id: number): string {
  return `${CONSULTANT_API_BASE}/api/requests/${id}/export/pptx`;
}

/** The permanent address of a finished run. The customer's way back in — it
 *  is the same string we put on screen, so build it in one place. */
export function studioResultPath(id: number): string {
  return `/studio/${id}`;
}

/** The service returns 429 when the studio is at generation capacity. */
export function isAtCapacity(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 429;
}

/** An id that was never issued — a mistyped or stale URL, not an outage. */
export function isNotFound(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}
