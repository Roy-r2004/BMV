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
  /** The intake field this answer fills, when it fills one — the conversation
   *  collects what the form used to ask for. Empty for a number question.
   *  Only names the server recognises ever arrive here. */
  field?: string;
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

/** One round of the adaptive interview. `done` is authoritative — it goes
 *  true when the consultant has enough, when the round cap is hit, and when a
 *  round fails, so the client never waits on a step that will not advance. */
export interface InterviewRound {
  questions: DiscoveryQuestion[];
  done: boolean;
  /** What they still need, or why they have enough. Shown to the client. */
  because: string;
  source: 'ai' | 'fallback';
  /** Read off what they wrote rather than asked as pills: whether this is one
   *  problem or the whole operation, and whether the business is trading yet.
   *  Either may be null when their words do not say. */
  inferred: { engagement_type: string | null; operating_stage: string | null };
  /** Fields without which the engagement cannot be launched at all. The
   *  interview will not call itself done while this is non-empty. */
  still_needed: string[];
}

export async function fetchInterviewRound(input: {
  business_name: string;
  business_description: string;
  industry?: string;
  operating_stage: OperatingStage;
  engagement_type?: EngagementType;
  needs_ai?: string;
  main_problem?: string;
  desired_outcome?: string;
  /** Everything answered so far, as the same {question, answer} pairs the
   *  run is launched with — so the interviewer sees exactly what the pipeline
   *  will see, and cannot ask for something it already has. */
  ops_numbers?: string;
  /** Every question label put to them so far, answered or not. Without the
   *  unanswered ones the interviewer cannot see what it already asked, and
   *  re-asks them each round in fresh wording. */
  asked?: string;
  /** The intake fields the conversation has filled so far, as JSON. One
   *  builder decides what is still missing, rather than the prompt guessing
   *  from whichever arguments happened to be passed. */
  known?: string;
  round: number;
}): Promise<InterviewRound> {
  const form = new FormData();
  form.set('business_name', input.business_name);
  form.set('business_description', input.business_description);
  if (input.industry) form.set('industry', input.industry);
  form.set('operating_stage', input.operating_stage);
  if (input.engagement_type) form.set('engagement_type', input.engagement_type);
  if (input.needs_ai) form.set('needs_ai', input.needs_ai);
  if (input.main_problem) form.set('main_problem', input.main_problem);
  if (input.desired_outcome) form.set('desired_outcome', input.desired_outcome);
  if (input.ops_numbers) form.set('ops_numbers', input.ops_numbers);
  if (input.asked) form.set('asked', input.asked);
  if (input.known) form.set('known', input.known);
  form.set('round', String(input.round));
  const { data } = await consultantClient.post('/api/discovery/interview', form, { timeout: 30000 });
  return {
    questions: Array.isArray(data?.questions) ? data.questions : [],
    done: Boolean(data?.done),
    because: typeof data?.because === 'string' ? data.because : '',
    source: data?.source === 'ai' ? 'ai' : 'fallback',
    inferred: {
      engagement_type: data?.inferred?.engagement_type ?? null,
      operating_stage: data?.inferred?.operating_stage ?? null,
    },
    still_needed: Array.isArray(data?.still_needed) ? data.still_needed : [],
  };
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

/** One line of the consultant thinking out loud. `kind` drives how it reads;
 *  the extra keys are present only on the kinds that carry them. */
export interface ThinkingStep {
  kind: 'considering' | 'testing' | 'verdict' | 'challenge' | 'settled';
  text: string;
  /** considering */
  count?: number;
  /** On the header of a pass that follows one whose lead was refuted. */
  retry?: boolean;
  area?: string;
  software?: boolean;
  /** true when this explanation is the client's own — shown, so they can see
   *  when we agreed with them and when we did not. */
  theirs?: boolean;
  /** verdict */
  verdict?: 'supported' | 'refuted' | 'untestable';
  because?: string;
  cites?: string[];
  /** testing — marks the one that leads */
  leading?: boolean;
  /** challenge */
  angle?: 'alternative' | 'confirmation';
  kills?: boolean;
  /** settled */
  status?: 'survived' | 'killed' | 'unchallenged';
}

export interface StudioProgress {
  /** "pending" while the human review gate holds a finished run. */
  review_status?: string | null;
  /** The run's own state. `awaiting_approval` is neither generating nor
   *  finished — a poller reading only `is_generating` shows a completed run
   *  with nothing behind it. */
  status?: string | null;
  /** The consultant's reasoning as it happens — explanations formed, tested
   *  against the client's own figures, and attacked. Append-only and
   *  purely presentational; nothing in the pipeline reads it back. */
  thinking?: ThinkingStep[];
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

export type StudioExportKind = 'zip' | 'pptx' | 'blueprint' | 'technical' | 'operations';

/** Fetch an export with the caller's session attached and hand it to the
 *  browser as a saved file. The export routes are auth-gated, and a plain
 *  <a href> navigation carries no Authorization header — the owner of a
 *  private run would be refused their own download. */
export async function downloadStudioExport(
  ref: StudioRef,
  kind: StudioExportKind,
  reviewToken?: string | null,
): Promise<void> {
  const path =
    kind === 'zip'
      ? `/api/requests/${ref}/export/zip`
      : kind === 'pptx'
        ? `/api/requests/${ref}/export/pptx`
        : `/api/requests/${ref}/export/pdf/${kind}`;
  const suffix = reviewToken ? `?review_token=${encodeURIComponent(reviewToken)}` : '';
  const { data, headers } = await consultantClient.get<Blob>(path + suffix, {
    responseType: 'blob',
    timeout: 180000,
  });
  const match = /filename="?([^";]+)"?/.exec(String(headers['content-disposition'] ?? ''));
  const fallback = kind === 'zip' ? 'engagement.zip' : kind === 'pptx' ? 'deck.pptx' : `${kind}.pdf`;
  const url = URL.createObjectURL(data);
  const a = document.createElement('a');
  a.href = url;
  a.download = match?.[1] ?? fallback;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
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

/** One of the client's own figures, as cited by a diagnosis. */
export interface StudioCitedClaim {
  id: string;
  text: string | null;
  source: string | null;
}

/** The reasoning behind the decision. Null when no diagnosis could be made —
 *  the client then sees the decision alone, as they did before this stage. */
export interface StudioDiagnosis {
  leading: {
    statement: string;
    area: string | null;
    software_can_fix: boolean | null;
    verdict: string | null;
    because: string | null;
    cites: StudioCitedClaim[];
    would_need: string | null;
    from_owner: boolean | null;
  };
  considered: { statement: string; area: string | null; verdict: string | null; because: string | null }[];
  /** 'survived' | 'killed' | 'unchallenged'. The third is not the first: a
   *  review that could not run has approved nothing. */
  status: string | null;
  weaknesses: string[];
  challenges: { angle: string; kills: boolean; because: string }[];
}

/** What we concluded, read before anything is built on it. */
export interface StudioDecision {
  diagnosis: StudioDiagnosis | null;
  id: number;
  public_id: string | null;
  status: string | null;
  business_name: string | null;
  understanding: {
    business_model: string | null;
    target_customer_profile: string | null;
    pain_points: string[];
    growth_opportunity: string | null;
  };
  decision: {
    summary: string | null;
    recommended_ai_employees: { title: string; why: string }[];
    recommended_features: string[];
    /** 'software' | 'process' | 'pricing' | 'staffing' | 'none'. Null on an
     *  engagement decided before this existed — read `builds`, not this. */
    intervention_kind: string | null;
    central_problem: string | null;
    why_not_the_others: string | null;
    confidence: string | null;
    unverified: string[];
  };
  /** Whether a build would actually move the diagnosed cause. False means we
   *  are telling them not to spend. They can still overrule it. */
  builds: boolean;
  /** Everything the client has already sent back, as one line. Empty on a
   *  first pass — shown so a second brief proves the objection was read. */
  revisions: string;
}

export async function getStudioDecision(ref: StudioRef): Promise<StudioDecision> {
  const { data } = await consultantClient.get(`/api/requests/${ref}/decision`);
  return data;
}

/** Press Build. `started` is false when someone already pressed it — the
 *  server claims the run with a conditional update, so a double press is
 *  answered honestly rather than starting a second build over the first. */
export async function approveStudioDecision(
  ref: StudioRef,
  scope?: { budget_range?: string; timeline?: string },
): Promise<{ status: string; started: boolean }> {
  // Budget and timeline ride along with the approval rather than the intake:
  // they reach one prompt, `playbook.j2` at stage ten, so asking on the way
  // in bought nothing and cost a screen of commercial questions.
  const form = new FormData();
  if (scope?.budget_range) form.append('budget_range', scope.budget_range);
  if (scope?.timeline) form.append('timeline', scope.timeline);
  const { data } = await consultantClient.post(`/api/requests/${ref}/decision/approve`, form);
  return data;
}

/** A figure read out of a file the client sent, verified against its cell. */
export interface StudioFigure {
  id: string;
  value: number;
  unit: string;
  time_basis: string;
  /** What it means in the business's own terms. */
  text: string;
  /** "march.xlsx · March · B5" — the file, the sheet, the cell. */
  source: string;
  cell: string;
  file: string;
}

export async function getStudioEvidence(ref: StudioRef): Promise<{ figures: StudioFigure[] }> {
  const { data } = await consultantClient.get(`/api/requests/${ref}/evidence`);
  return data;
}

/** `rejected` counts figures whose cited cell did not hold them. They are
 *  dropped, not kept with a caveat — a figure a hypothesis may rest on
 *  cannot be "probably in the file somewhere". */
export async function uploadStudioEvidence(
  ref: StudioRef,
  file: File,
): Promise<{ added: number; rejected: number; figures: StudioFigure[]; rediagnosing: boolean }> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await consultantClient.post(`/api/requests/${ref}/evidence`, form, {
    timeout: 120000,
  });
  return data;
}

export async function deleteStudioEvidence(
  ref: StudioRef,
  claimId: string,
): Promise<{ figures: StudioFigure[] }> {
  const { data } = await consultantClient.delete(`/api/requests/${ref}/evidence/${claimId}`);
  return data;
}

/** Take the answer and stop. Only offered when we said a build won't help;
 *  the brief is then the deliverable, and this is not a failed engagement. */
export async function acceptStudioAdvice(ref: StudioRef): Promise<{ status: string }> {
  const { data } = await consultantClient.post(`/api/requests/${ref}/decision/accept`);
  return data;
}

/** Send it back. The note reaches the next diagnosis as a correction. */
export async function reviseStudioDecision(ref: StudioRef, note: string): Promise<{ status: string; started: boolean }> {
  const form = new FormData();
  form.append('note', note);
  const { data } = await consultantClient.post(`/api/requests/${ref}/decision/revise`, form);
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
