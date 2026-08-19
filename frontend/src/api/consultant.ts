import axios from 'axios';
import { getUserToken } from './auth';

// The image-demo pipeline is its own service (consultant-service), separate
// from the main backend — its own port, its own ledger, its own uploads.
// Asset paths it returns ("/uploads/...") are relative to THIS base, never
// to VITE_API_BASE_URL.
export const CONSULTANT_API_BASE =
  import.meta.env.VITE_CONSULTANT_API_BASE_URL ??
  (import.meta.env.PROD ? '' : 'http://localhost:8002');

const consultantClient = axios.create({ baseURL: CONSULTANT_API_BASE });

// Engagements belong to accounts: every call carries the session token,
// and the service resolves it against the main app.
consultantClient.interceptors.request.use((config) => {
  const token = getUserToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

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
  target_customers?: string;
  desired_outcome?: string;
  reference_url?: string;
  what_you_like?: string;
  needs_ai?: string;
  budget_range?: string;
  timeline?: string;
  whatsapp?: string;
  /** The owner's own site/profile — distinct from reference_url, which is a
   *  tool they admire, not their own business. The research stage fetches
   *  it before analysis when present. */
  site_url?: string;
  /** How the business earns today, in the owner's words — grounds the
   *  revenue-model half of the decomposition stage. */
  revenue_today?: string;
  /** Which register the discovery numbers are in: current reality, or a
   *  plan for a business that hasn't launched yet. */
  operating_stage?: OperatingStage;
  /** "full" (blueprint the whole business) or "capability" (one solution
   *  scoped into an existing operation). */
  engagement_type?: EngagementType;
  /** The discovery Q&A — the ONLY numbers the business case is allowed to
   *  compute with. Only answered questions are sent. */
  ops_numbers?: OpsNumber[];
}

export type OperatingStage = 'operating' | 'opening';
export type EngagementType = 'full' | 'capability';

/** How a run is addressed: the unguessable public slug for its owner, or
 *  the plain numeric id kept for the showcase and legacy links. */
export type StudioRef = string | number;

export interface OpsNumber {
  question: string;
  answer: string;
}

/** One tailored discovery question, written by the fast model from the
 *  brief (or a stage-generic fallback when that call fails). */
export interface DiscoveryQuestion {
  id: string;
  label: string;
  placeholder: string;
  why: string;
}

/** The questions a consultant would open with, tailored to this brief.
 *  The service never fails closed (it serves a fallback set), so a reject
 *  here means the network itself — callers keep their own local fallback. */
export async function fetchDiscoveryQuestions(input: {
  business_name: string;
  business_description: string;
  industry?: string;
  operating_stage: OperatingStage;
  engagement_type?: EngagementType;
}): Promise<DiscoveryQuestion[]> {
  const form = new FormData();
  form.set('business_name', input.business_name);
  form.set('business_description', input.business_description);
  if (input.industry) form.set('industry', input.industry);
  form.set('operating_stage', input.operating_stage);
  if (input.engagement_type) form.set('engagement_type', input.engagement_type);
  const { data } = await consultantClient.post('/api/discovery/questions', form, { timeout: 15000 });
  return Array.isArray(data?.questions) ? data.questions : [];
}

export interface BriefMessage {
  role: 'assistant' | 'user';
  content: string;
}

export interface BriefTurn {
  ok: boolean;
  reply?: string;
  /** Cumulative '- fact' lines of everything the client corrected in the
   *  chat — appended to the description at launch. */
  brief_addendum?: string | null;
}

/** One turn of the pre-launch briefing chat. Fails open (ok=false) — the
 *  caller then launches directly; this chat may never block a run. */
export async function fetchBriefTurn(input: {
  intake: StudioIntake;
  messages: BriefMessage[];
}): Promise<BriefTurn> {
  try {
    const form = new FormData();
    form.set('business_name', input.intake.business_name);
    form.set('business_description', input.intake.business_description);
    if (input.intake.industry) form.set('industry', input.intake.industry);
    if (input.intake.target_customers) form.set('target_customers', input.intake.target_customers);
    if (input.intake.main_problem) form.set('main_problem', input.intake.main_problem);
    if (input.intake.desired_outcome) form.set('desired_outcome', input.intake.desired_outcome);
    if (input.intake.operating_stage) form.set('operating_stage', input.intake.operating_stage);
    if (input.intake.engagement_type) form.set('engagement_type', input.intake.engagement_type);
    if (input.intake.needs_ai) form.set('needs_ai', input.intake.needs_ai);
    if (input.intake.ops_numbers?.length) form.set('ops_numbers', JSON.stringify(input.intake.ops_numbers));
    if (input.messages.length) form.set('messages', JSON.stringify(input.messages));
    const { data } = await consultantClient.post('/api/discovery/brief', form, { timeout: 25000 });
    return data?.ok ? data : { ok: false };
  } catch {
    return { ok: false };
  }
}

export interface StudioProgress {
  /** "pending" while the human review gate holds a finished run. */
  review_status?: string | null;
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
  technical_plan: string | null;
  generated_pages: { attraction_images: StudioScreen[] };
  deck_available: boolean;
  status: string;
  is_generating: boolean;
  industry: string | null;
  /** Echoed back from the intake — feeds the Plans tab's add-on suggestions,
   *  the same signal the analysis prompt already used. */
  main_problem: string | null;
  desired_outcome: string | null;
  reference_url: string | null;
  what_you_like: string | null;
  timeline: string | null;
  budget_range: string | null;
  /** The analyze stage's own diagnosis, read back out rather than
   *  re-derived — the same finding that shaped everything downstream.
   *  Null when the fallback ("Unknown") fired instead of a real analysis. */
  business_model: string | null;
  target_customer_profile: string | null;
  pain_points: string[];
  growth_opportunity: string | null;
  /** Real facts pulled from the owner's own site, when they gave one and
   *  the fetch/extraction succeeded. Null otherwise — never a guess. */
  site_research: StudioSiteResearch | null;
  /** The decomposition the blueprint/technical docs were written FROM —
   *  empty array / null for runs made before the decompose stage existed. */
  modules: StudioModule[];
  business_case: StudioBusinessCase | null;
  /** The execution playbook — ordered real-world steps for the owner, plus
   *  the AI-covers-it / humans-needed people plan. Null for older runs. */
  playbook: StudioPlaybook | null;
  /** The consultancy layers (extras stage). Each is null/empty for older
   *  runs or when its one call failed — every layer fails open alone. */
  journey: { stages: StudioJourneyStage[] } | null;
  organization: StudioOrganization | null;
  scoreboard: StudioScoreboardRow[];
  risks: StudioRisk[];
  procedures: StudioProcedure[];
  checklists: StudioChecklists | null;
  engagement_type: EngagementType | null;
  review_status?: string | null;
  /** The quality bench's full report — present for the reviewer. */
  qa_report?: {
    checks: { label: string; passed: boolean; note?: string }[];
    findings: { severity: string; where?: string; issue: string; fix?: string }[];
    polish_applied?: boolean;
  } | null;
}

/** What a pending run shows the waiting client: real counts and names,
 *  their own numbers echoed, and the quality bench's pass marks — never
 *  the deliverable content itself. */
export interface StudioTeaser {
  pending_review: true;
  id: number;
  business_name: string;
  concept_name: string | null;
  engagement_type: EngagementType | null;
  stats: {
    modules: number;
    ai_agents: number;
    journey_stages: number;
    org_roles: number;
    procedures: number;
    checklists: number;
    quick_wins: number;
  };
  module_teasers: { name: string | null; purpose: string | null }[];
  journey_stage_names: string[];
  numbers_echo: string[];
  qa_checks: { label: string; passed: boolean }[];
}

export type StudioPreviewResult = StudioPreview | StudioTeaser;

export function isPendingTeaser(r: StudioPreviewResult): r is StudioTeaser {
  return (r as StudioTeaser).pending_review === true;
}

/** Approve a pending engagement — reviewer only. */
export async function approveReview(ref: StudioRef, reviewToken: string): Promise<void> {
  await consultantClient.post(`/api/requests/${ref}/review/approve?review_token=${encodeURIComponent(reviewToken)}`);
}

/** The reviewer's red pen: edited documents replace the generated ones. */
export async function saveReviewDocs(
  ref: StudioRef,
  reviewToken: string,
  docs: { mvp_blueprint?: string; technical_plan?: string },
): Promise<void> {
  const form = new FormData();
  if (docs.mvp_blueprint) form.set('mvp_blueprint', docs.mvp_blueprint);
  if (docs.technical_plan) form.set('technical_plan', docs.technical_plan);
  await consultantClient.post(`/api/requests/${ref}/review/docs?review_token=${encodeURIComponent(reviewToken)}`, form);
}

/** Humans and AI agents on one chart, with decision rights — plus what
 *  actually changes for each human (the adoption plan's raw material). */
export interface StudioOrgRole {
  role: string;
  type: 'human' | 'ai';
  responsibilities: string[];
  decides_alone: string | null;
  hands_off: string | null;
}

export interface StudioOrganization {
  roles: StudioOrgRole[];
  change_impact: { role: string; what_changes: string | null; must_learn: string | null }[];
}

/** One stage of the service-blueprint journey: what the customer does,
 *  what they see (frontstage), which modules run unseen (backstage). */
export interface StudioJourneyStage {
  stage: string;
  customer_action: string | null;
  frontstage: string | null;
  backstage_modules: string[];
  fail_point_removed?: string | null;
}

/** One scoreboard row. Baselines are only ever the owner's own numbers or
 *  the literal "measure in week 1" — the pipeline never invents one. */
export interface StudioScoreboardRow {
  metric: string;
  baseline: string | null;
  target: string | null;
  owner: string | null;
  review: string | null;
}

export interface StudioRisk {
  risk: string;
  mitigation: string | null;
  who_feels_it: string | null;
}

export interface StudioProcedure {
  name: string;
  trigger: string | null;
  steps: { actor: string | null; step: string }[];
  exceptions: { when: string; then: string | null }[];
  /** Which module this routine belongs to — per-module SOP library. */
  module?: string | null;
}

/** The operations-manual appendix: the artifacts staff hold in their
 *  hands, generated for THIS business. */
export interface StudioChecklists {
  checklists: { name: string; when: string | null; items: string[] }[];
  forms: { name: string; purpose: string | null; fields: string[] }[];
}

export interface StudioQuickWin {
  title: string;
  detail: string | null;
  who?: string | null;
  no_software?: boolean;
}

/** The blueprint or technical plan as a branded PDF. Only offer once the
 *  run is done — the route 400s before the document exists. */
export function studioPdfUrl(ref: StudioRef, kind: 'blueprint' | 'technical' | 'operations'): string {
  return `${CONSULTANT_API_BASE}/api/requests/${ref}/export/pdf/${kind}`;
}

/** The whole engagement as one download: the three PDF volumes, zipped. */
export function studioZipUrl(ref: StudioRef): string {
  return `${CONSULTANT_API_BASE}/api/requests/${ref}/export/zip`;
}

export interface StudioPlaybookStep {
  phase: 'before' | 'during' | 'after';
  who: 'you' | 'bmv' | 'partner';
  title: string;
  detail: string;
  /** When, as a horizon ("week 1", "first 30 days") — never a date. */
  horizon?: string | null;
  needs?: string[];
}

export interface StudioPlaybook {
  /** 3-5 first-30-days actions, at least one needing no software. */
  quick_wins?: StudioQuickWin[];
  steps: StudioPlaybookStep[];
  people_plan: {
    ai_covers?: string[];
    humans_needed?: { role: string; when: string; why: string }[];
  };
}

export interface StudioModuleSpec {
  features: { name: string; description: string }[];
  data: string[];
  screens: string[];
  ai: { role: string | null; decides_alone?: string | null; hands_off?: string | null } | null;
  integrations: string[];
  kpis: string[];
}

export interface StudioModule {
  id: string;
  name: string;
  purpose: string;
  users: string[];
  pain_point_addressed: string;
  /** Null when this one module's deep-spec call failed — the module still
   *  renders from its decomposition fields. */
  spec: StudioModuleSpec | null;
}

export interface StudioBusinessCase {
  /** Who is served, how they arrive, and the retention mechanism. */
  customers?: { segments?: string[]; channels?: string[]; how_kept?: string | null } | null;
  revenue_streams: { name: string; description: string; enabled_by?: string }[];
  costs_removed: { cost: string; how: string; enabled_by?: string }[];
  pricing_levers: string[];
  payback_logic: string | null;
  /** What staying manual costs — computed from owner numbers when they
   *  exist, mechanism-only otherwise. */
  cost_of_inaction?: string | null;
}

export interface StudioSiteResearch {
  source_url: string;
  services: string[];
  hours: string | null;
  tone: string | null;
  highlights: string[];
}

export async function createStudioRequest(intake: StudioIntake): Promise<{ id: number; public_id: string | null; status: string }> {
  const form = new FormData();
  form.set('business_name', intake.business_name);
  form.set('business_description', intake.business_description);
  form.set('email', intake.email);
  if (intake.industry) form.set('industry', intake.industry);
  if (intake.main_problem) form.set('main_problem', intake.main_problem);
  if (intake.target_customers) form.set('target_customers', intake.target_customers);
  if (intake.desired_outcome) form.set('desired_outcome', intake.desired_outcome);
  if (intake.reference_url) form.set('reference_url', intake.reference_url);
  if (intake.what_you_like) form.set('what_you_like', intake.what_you_like);
  if (intake.needs_ai) form.set('needs_ai', intake.needs_ai);
  if (intake.budget_range) form.set('budget_range', intake.budget_range);
  if (intake.timeline) form.set('timeline', intake.timeline);
  if (intake.whatsapp) form.set('whatsapp', intake.whatsapp);
  if (intake.site_url) form.set('site_url', intake.site_url);
  if (intake.revenue_today) form.set('revenue_today', intake.revenue_today);
  if (intake.operating_stage) form.set('operating_stage', intake.operating_stage);
  if (intake.engagement_type) form.set('engagement_type', intake.engagement_type);
  if (intake.ops_numbers?.length) form.set('ops_numbers', JSON.stringify(intake.ops_numbers));
  const { data } = await consultantClient.post('/api/requests', form, { timeout: 30000 });
  return data;
}

export async function getStudioProgress(ref: StudioRef): Promise<StudioProgress> {
  const { data } = await consultantClient.get(`/api/requests/${ref}/progress`);
  return data;
}

export async function getStudioPreview(ref: StudioRef, reviewToken?: string | null): Promise<StudioPreviewResult> {
  const suffix = reviewToken ? `?review_token=${encodeURIComponent(reviewToken)}` : '';
  const { data } = await consultantClient.get(`/api/requests/${ref}/preview${suffix}`);
  return data;
}

/** The deck the pipeline already builds. Only offer it when the preview says
 *  `deck_available` — the route 400s before the plan stage has run. */
export function studioDeckUrl(ref: StudioRef): string {
  return `${CONSULTANT_API_BASE}/api/requests/${ref}/export/pptx`;
}

/** The permanent address of a finished run. The customer's way back in — it
 *  is the same string we put on screen, so build it in one place. */
export function studioResultPath(ref: StudioRef): string {
  // Numeric ids are the public spellings (showcase cards, legacy links); a
  // slug is a private address only its owner's session can open.
  return /^\d+$/.test(String(ref)) ? `/demo/${ref}` : `/engagements/${ref}`;
}

/** One public example engagement — the marketing gallery card. */
export interface StudioShowcaseCard {
  id: number;
  business_name: string;
  concept_name: string | null;
  industry: string | null;
  engagement_type: EngagementType | null;
  operating_stage: OperatingStage | null;
  stats: { modules: number; ai_agents: number; journey_stages: number; procedures: number };
  image_url: string | null;
}

export async function fetchShowcase(): Promise<StudioShowcaseCard[]> {
  const { data } = await consultantClient.get('/api/requests/showcase-gallery');
  return Array.isArray(data?.showcase) ? data.showcase : [];
}

/** The caller's own engagements — the only listing a client ever sees. */
export interface StudioMineEntry {
  id: number;
  /** The run's private slug address. Null only for pre-slug legacy rows. */
  public_id: string | null;
  business_name: string;
  concept_name: string | null;
  status: string;
  is_generating: boolean;
  review_status: string | null;
  created_at: string | null;
}

export async function fetchMyEngagements(): Promise<StudioMineEntry[]> {
  const { data } = await consultantClient.get('/api/requests/mine');
  return Array.isArray(data?.engagements) ? data.engagements : [];
}

/** Engagements are private: 401 = sign in, 403 = someone else's run. */
export function isUnauthorized(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401;
}

export function isForbidden(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 403;
}

/** The service returns 429 when the studio is at generation capacity. */
export function isAtCapacity(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 429;
}

/** An id that was never issued — a mistyped or stale URL, not an outage. */
export function isNotFound(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}
