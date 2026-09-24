import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  fetchCaseFile,
  getStudioPlan,
  logPilotWeek,
  retryStudioPlan,
  shareStudio,
  unshareStudio,
  type CaseFigure,
  type CaseFile,
  type ActionPlan,
  type PilotEntry,
} from '../api/consultant';
import Chrome from '../components/consult/Chrome';
import FrontDoor from '../components/consult/FrontDoor';
import Interview from '../components/consult/Interview';
import Playback from '../components/consult/Playback';
import Thinking from '../components/consult/Thinking';
import Answer from '../components/consult/Answer';
import Building from '../components/consult/Building';
import Package, { type PackageScreen } from '../components/consult/Package';
import '../styles/consult.css';
import SiteFooter from '../components/SiteFooter';
import {
  approveReview,
  createStudioRequest,
  fetchInterviewRound,
  isForbidden,
  isPendingTeaser,
  isUnauthorized,
  saveReviewDocs,
  getStudioPreview,
  getStudioProgress,
  getStudioDecision,
  approveStudioDecision,
  acceptStudioAdvice,
  reviseStudioDecision,
  getStudioEvidence,
  uploadStudioEvidence,
  deleteStudioEvidence,
  consultantAssetUrl,
  isAtCapacity,
  isNotFound,
  downloadStudioExport,
  studioResultPath,
  type DiscoveryQuestion,
  type StudioExportKind,
  type StudioRef,
  type StudioTeaser,
  type EngagementType,
  type OperatingStage,
  type StudioPreview,
  type StudioProgress,
  type StudioDecision,
  type StudioFigure,
  type StudioScreen,
} from '../api/consultant';
/** One round of the interview as the server returned it. */
interface Round {
  questions: DiscoveryQuestion[];
  /** What the consultant said it still needed before asking these. */
  because: string;
}

/** Which half of the run is on screen: the diagnosis, or the build. */
type RunPhase = 'diagnosing' | 'building';
import {
  splitH2Sections,
  findSection,
  splitH3Subsections,
  parseListItems,
  parseNestedPhases,
  firstParagraph,
  stripInlineMarkdown,
} from '../utils/consultantMarkdown';
import { consultingEmailUrl } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  BUILD_PLANS,
  suggestBusinessAddons,
  addonAvailable,
  addonIncluded,
  summarizeSelection,
  type BuildPlan,
} from '../data/buildPlans';
import '../styles/studio.css';

// The stage lists and rotating captions for the running step live in
// components/studio/RunStage.tsx now. They used to be one list of the BUILD
// stages, shown for the whole run — so a client who was only being diagnosed
// watched "Planning the product" and "Rendering your screens" scroll past for
// work that would not happen unless they pressed Build.

// 'loading' is the beat between opening a result URL and knowing what is at
// the other end; 'missing' is an id that was never issued.
// 'briefing' sits between the form and the launch: the consultant plays
// back the brief in a short chat so wrong inputs get corrected before a
// dollar of pipeline runs. It can never block — if the consultant is
// unreachable, the run starts directly.
// 'pending' is the review gate's client-facing state: the engagement is
// finished and with the consultant; the page shows a cinematic teaser of
// real facts and flips to the reveal the moment it is approved.
// 'private' is the ownership wall: the run exists but belongs to a
// different account (or the caller isn't signed in).
// 'decision' is the approval gate: the diagnosis half has finished and is
// waiting on the client. Nothing is running and nothing is built — the two
// states 'building' and 'reveal' used to cover between them, which is why
// the run needs its own act rather than a flag on one of theirs.
type Act = 'intake' | 'loading' | 'briefing' | 'pending' | 'decision' | 'building' | 'reveal' | 'failed' | 'missing' | 'private';

type ResultTab = 'screens' | 'blueprint' | 'technical' | 'playbook' | 'team' | 'plans';

// Each tab knows its own availability rule, so a run that skipped a stage
// (no technical plan yet, no AI employees named) never shows an empty tab —
// the tab bar itself is evidence of what this run actually produced.
const RESULT_TABS: { id: ResultTab; label: string; available: (p: StudioPreview) => boolean }[] = [
  { id: 'screens', label: 'Screens', available: () => true },
  { id: 'blueprint', label: 'Blueprint', available: (p) => Boolean(p.mvp_blueprint) || (p.modules?.length ?? 0) > 0 },
  { id: 'technical', label: 'Technical plan', available: (p) => Boolean(p.technical_plan) },
  { id: 'playbook', label: 'Playbook', available: (p) => (p.playbook?.steps?.length ?? 0) > 0 },
  { id: 'team', label: 'AI team', available: (p) => p.ai_features.length > 0 },
  // Static plan/add-on content (data/buildPlans.ts) plus the deck export —
  // always something to show, so always available.
  { id: 'plans', label: 'Plans', available: () => true },
];

interface FieldErrors {
  business_name?: string;
  business_description?: string;
  main_problem?: string;
  email?: string;
  what_you_like?: string;
}

// Heroicons-24-outline paths, same convention as ConsultantExperience.tsx.
const INTAKE_ICONS = {
  shield:
    'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  building:
    'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
  briefcase:
    'M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 0 0 .75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 0 0-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0 1 12 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 0 1-.673-.38m0 0A2.18 2.18 0 0 1 3 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 0 1 3.413-.387m7.5 0V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v.894m7.5 0a48.667 48.667 0 0 0-7.5 0',
  globe:
    'M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m-18.432-.001A8.959 8.959 0 0 1 3 12c0-.778.099-1.533.284-2.253',
  sparkle:
    'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z',
  database:
    'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 3.75v3.75m-16.5-3.75v3.75',
  wrench:
    'M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75',
  user: 'M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z',
  bolt: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  workflow:
    'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99',
  cpu: 'M8.25 3v1.5M15.75 3v1.5M8.25 19.5V21M15.75 19.5V21M3 8.25H1.5M3 12H1.5M3 15.75H1.5M22.5 8.25H21M22.5 12H21M22.5 15.75H21M6.75 19.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v10.5a2.25 2.25 0 0 0 2.25 2.25Zm3-9h4.5v4.5h-4.5V9.75Z',
  chart:
    'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
};

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

// The intake mirrors the old build-request wizard's five steps and fields —
// that data meaningfully shapes the analysis (see analyze.j2), so trimming
// it down to "just enough for a demo" was throwing away signal the pipeline
// already knows how to use.
// Two screens, because a consultation should not open with paperwork.
//
// It was six, then four: name, industry, sector, customers, the tool you
// admire, your AI appetite, your budget — every one of them asked before we
// had shown the visitor a single thing worth their trust. Now they say what
// is wrong, and the consultant asks for the rest the way a person would.
// Budget and timeline moved to the approval gate, where they are a question
// someone who wants the build is happy to answer; nothing before `plan`
// reads them anyway.
const INTAKE_STEPS = [
  { id: 'problem', label: 'Your situation', subtitle: 'Tell us in your own words' },
  { id: 'conversation', label: 'The conversation', subtitle: 'A few questions before we answer' },
] as const;

/** Shown only when the tailoring call itself is unreachable — the server
 *  already serves its own fallback on model failure. Mirrors that set. */
const LOCAL_DISCOVERY_FALLBACK: Record<OperatingStage, DiscoveryQuestion[]> = {
  operating: [
    { id: 'admin-hours', label: 'How many hours a week go to repetitive admin?', placeholder: 'e.g. 12 hours on bookings, follow-ups, paperwork', why: 'Time is the first cost your system removes - this sizes it.' },
    { id: 'avg-value', label: 'What is one sale, visit or job worth on average?', placeholder: 'e.g. $85', why: 'Lets every recovered hour and missed sale be valued at your own prices.' },
    { id: 'monthly-volume', label: 'How many customers, orders or jobs in a typical month?', placeholder: 'e.g. 340', why: 'Sets the scale every other number multiplies against.' },
    { id: 'loss-rate', label: 'What share of bookings or leads never turn into money?', placeholder: 'e.g. about 20% no-show or go quiet', why: 'Recovered losses are usually the fastest payback - this sizes them.' },
  ],
  opening: [
    { id: 'planned-price', label: 'What do you plan to charge for one sale, visit or job?', placeholder: 'e.g. $30', why: 'Anchors every capacity and payback calculation in your own pricing.' },
    { id: 'planned-capacity', label: 'How many customers or orders are you built to handle per week at launch?', placeholder: 'e.g. 200', why: 'Your target capacity is what the system has to keep full.' },
    { id: 'planned-hires', label: 'How many people do you plan to hire for phones, bookings or admin?', placeholder: 'e.g. 1 part-time', why: 'Every role the system covers is a hire you can delay.' },
    { id: 'launch-budget', label: 'What is your launch budget for tools and software?', placeholder: 'e.g. $5,000', why: 'Keeps every recommendation inside what you actually planned to spend.' },
  ],
};

const BUDGET_OPTIONS = ['Starter scope', 'Standard scope', 'Full build', 'Not sure yet'];

// Kept only as a bridge for someone who lands on bare /studio with a run
// still going — the URL is the source of truth, this is the safety net.
const RESUME_KEY = 'bmv_studio_request_id';

/** Asked only when the interview ended without the business's name. */
const NAME_QUESTION: DiscoveryQuestion = {
  id: 'bmv-business-name',
  label: "Last thing: what's the business called?",
  placeholder: 'Halo Reformer Studio',
  why: 'So everything we write is addressed to you, not to "the business". If it has no name yet, a working name is fine.',
  field: 'business_name',
};

/** Replace the numbers in `value` with the ones in `next`, when both say the
 *  same shape of thing ("10 of 12" edited to "about 11 of 12" shows "11 of
 *  12"); otherwise show what they typed. */
function reshapeValue(value: string, token: string, next: string): string {
  const oldN: string[] = token.match(/\d[\d,.]*/g) ?? [];
  const newN: string[] = next.match(/\d[\d,.]*/g) ?? [];
  if (!oldN.length || oldN.length !== newN.length) return next;
  let i = 0;
  return value.replace(/\d[\d,.]*/g, (m) => (oldN.includes(m) && i < newN.length ? newN[i++] : m));
}

// Every export download carries the caller's session. The export routes are
// auth-gated, and a plain <a href> navigation sends no Authorization header —
// the owner would be refused their own file (a signed-in owner hitting the
// raw URL sees exactly that). The reviewer's ?review= token rides along when
// the page has one.
function DownloadButton({ refId, kind, className, children }: {
  refId: StudioRef;
  kind: StudioExportKind;
  className?: string;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      className={className}
      disabled={busy}
      onClick={() => {
        if (busy) return;
        setBusy(true);
        downloadStudioExport(refId, kind, new URLSearchParams(window.location.search).get('review'))
          .catch(() => {
            window.alert('The download could not start — check your connection and try again.');
          })
          .finally(() => setBusy(false));
      }}
    >
      {busy ? 'Preparing…' : children}
    </button>
  );
}

function useElapsed(running: boolean, startedAt: number | null) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    // Read the clock the moment the run starts. Without this the first
    // render uses whatever `now` was when the component mounted, which can
    // be a second or more stale — and a stale `now` against a freshly
    // re-based `startedAt` is a negative elapsed, floored to 0:00.
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  if (!startedAt) return '0:00';
  const s = Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** The blueprint arrives as light markdown. Rendered as blocks rather than
 *  through a markdown dependency: it is headings, bullets and paragraphs,
 *  and dangerouslySetInnerHTML on model-authored prose is not a trade worth
 *  making for three formatting rules. */
function BlueprintProse({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const out: Array<{ kind: 'h' | 'p'; text: string } | { kind: 'ul'; items: string[] }> = [];
    for (const raw of text.split('\n')) {
      const line = raw.trim();
      if (!line) continue;
      const strip = (s: string) => s.replace(/\*\*/g, '').replace(/^#+\s*/, '').trim();
      if (/^#{1,6}\s/.test(line)) out.push({ kind: 'h', text: strip(line) });
      else if (/^[-*•]\s/.test(line)) {
        const item = strip(line.replace(/^[-*•]\s+/, ''));
        const last = out[out.length - 1];
        if (last && last.kind === 'ul') last.items.push(item);
        else out.push({ kind: 'ul', items: [item] });
      } else out.push({ kind: 'p', text: strip(line) });
    }
    return out;
  }, [text]);

  return (
    <div className="studio-prose">
      {blocks.map((b, i) =>
        b.kind === 'h' ? (
          <h3 key={i}>{b.text}</h3>
        ) : b.kind === 'ul' ? (
          <ul key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={i}>{b.text}</p>
        ),
      )}
    </div>
  );
}

/** First two initial letters of a name's words — "AI Scheduler" → "AS". */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((w) => /^[a-zA-Z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  );
}

function PlanHero({ kicker, title, lead }: { kicker: string; title: string; lead: string }) {
  return (
    <div className="studio-plan-hero">
      <p className="studio-kicker mb-3">{kicker}</p>
      <h2 className="studio-display text-2xl sm:text-3xl font-bold text-navy mb-4">{title}</h2>
      <p className="studio-plan-hero-lead">{lead}</p>
    </div>
  );
}

function PlanPanel({
  eyebrow,
  children,
  className = '',
}: {
  eyebrow: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`studio-panel studio-plan-panel ${className}`}>
      <p className="studio-kicker mb-4">{eyebrow}</p>
      {children}
    </div>
  );
}

/** The decompose-era blueprint, in the reference's consulting-app layout —
 *  every number and node populated from the run's own structured data:
 *  the agent flow from the modules' real agents, the data sources from
 *  their brains, the value cards from the business case. Deliberately
 *  ABSENT from the reference: invented impact dollars/percentages, fake
 *  prospect cards, stock avatars — this page only states facts the
 *  pipeline produced. Older runs keep BlueprintCinematic below. */
function DecomposedBlueprint({ preview }: { preview: StudioPreview }) {
  const md = preview.mvp_blueprint ?? '';
  const sections = useMemo(() => splitH2Sections(md), [md]);
  const exec = findSection(sections, /executive|summary/);
  const buildFirst = findSection(sections, /build first/);
  const bc = preview.business_case;
  const mods = preview.modules ?? [];

  const execText = exec
    ? stripInlineMarkdown(exec.body.replace(/\n+/g, ' '))
    : preview.preview_summary ?? '';

  type TechRail = { ai_agent?: { purpose?: string; brain?: string[]; escalation?: string } };
  const agentMods = mods.filter((m) => m.spec?.ai?.role || (m as { tech?: TechRail }).tech?.ai_agent);
  const integrations = [...new Set(mods.flatMap((m) => m.spec?.integrations ?? []))];
  // Brain entries are written for the technical plan and carry parenthetical
  // entity asides ("(from InvestmentCriteriaConfiguration entity)") — strip
  // them for this at-a-glance panel, where they read as jargon and, on a
  // phone, each turned into a tall card of its own.
  const cleanSource = (s: string) =>
    s
      .replace(/\s*\([^)]*\)?/g, '')
      // CamelCase entity names read as code AND, being unbreakable words,
      // blow up the phone grid's column widths — space them into words.
      .replace(/\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b/g, (w) => w.replace(/([a-z0-9])([A-Z])/g, '$1 $2'))
      .replace(/\s+/g, ' ')
      .trim();
  const dataSources = [
    ...new Set(
      agentMods
        .flatMap((m) => (m as { tech?: TechRail }).tech?.ai_agent?.brain ?? [])
        .map(cleanSource)
        .filter(Boolean),
    ),
  ].slice(0, 5);

  const moduleNameById: Record<string, string> = Object.fromEntries(
    mods.filter((m) => m.id).map((m) => [m.id, m.name]),
  );

  const valueCards = [
    ...(bc?.revenue_streams ?? []).map((s) => ({
      icon: INTAKE_ICONS.chart, tone: 'up' as const, title: s.name, body: s.description,
    })),
    ...(bc?.costs_removed ?? []).map((c) => ({
      icon: INTAKE_ICONS.bolt, tone: 'down' as const, title: c.cost, body: c.how,
    })),
  ].slice(0, 4);

  return (
    <div className="bp">
      {/* hero: identity left, agent flow right */}
      <div className="bp-hero">
        <div>
          <p className="studio-kicker mb-3">Blueprint</p>
          <h2 className="studio-display bp-title">{preview.concept_name || preview.business_name}</h2>
          {preview.business_model && (
            <p className="bp-subtitle">AI {preview.business_model} system</p>
          )}
          <p className="bp-lead">{execText}</p>
          <div className="bp-stats">
            <div className="bp-stat">
              <Icon path={INTAKE_ICONS.workflow} className="w-4 h-4" />
              <strong>{mods.length}</strong> Core modules
            </div>
            <div className="bp-stat">
              <Icon path={INTAKE_ICONS.cpu} className="w-4 h-4" />
              <strong>{agentMods.length}</strong> AI agents
            </div>
            <div className="bp-stat">
              <Icon path={INTAKE_ICONS.globe} className="w-4 h-4" />
              <strong>{integrations.length}</strong> Integrations
            </div>
            <div className="bp-stat">
              <Icon path={INTAKE_ICONS.shield} className="w-4 h-4" />
              <strong>100%</strong> Human oversight
            </div>
          </div>
        </div>

        <div className="bp-flowpanel">
          {dataSources.length > 0 && (
            <div className="bp-sources">
              <p className="bp-mini-kicker">Data sources</p>
              {dataSources.map((s) => (
                <div className="bp-source" key={s}>
                  <Icon path={INTAKE_ICONS.database} className="w-3.5 h-3.5" />
                  <p>{s}</p>
                </div>
              ))}
            </div>
          )}
          <div className="bp-agents">
            {agentMods.map((m, i) => (
              <div className="bp-agentnode" key={m.id || i}>
                <span className="bp-agentnode-no">{String(i + 1).padStart(2, '0')}</span>
                <p className="bp-agentnode-name">{m.name}</p>
                <p className="bp-agentnode-tag">AI Agent</p>
              </div>
            ))}
            <div className="bp-agentnode bp-agentnode--human">
              <span className="bp-agentnode-no">{String(agentMods.length + 1).padStart(2, '0')}</span>
              <p className="bp-agentnode-name">Human review</p>
              <p className="bp-agentnode-tag">Your team</p>
            </div>
          </div>
          <div className="bp-legend">
            <span><i className="bp-dot bp-dot--ai" /> AI processing</span>
            <span><i className="bp-dot bp-dot--human" /> Human in the loop</span>
          </div>
        </div>
      </div>

      {/* how this creates value — from the business case, nothing invented */}
      {valueCards.length > 0 && (
        <div>
          <p className="studio-kicker mb-4">How this creates value</p>
          <div className="bp-valuegrid">
            {valueCards.map((v) => (
              <div className="bp-valuecard" key={v.title}>
                <span className={`bp-valueicon bp-valueicon--${v.tone}`}>
                  <Icon path={v.icon} className="w-4 h-4" />
                </span>
                <h3>{v.title}</h3>
                <p>{v.body}</p>
              </div>
            ))}
          </div>
          {bc?.customers && ((bc.customers.segments?.length ?? 0) > 0 || (bc.customers.channels?.length ?? 0) > 0) && (
            <div className="bp-customers">
              {(bc.customers.segments?.length ?? 0) > 0 && (
                <p><span>Who you serve</span>{bc.customers.segments!.join(' · ')}</p>
              )}
              {(bc.customers.channels?.length ?? 0) > 0 && (
                <p><span>How they arrive</span>{bc.customers.channels!.join(' · ')}</p>
              )}
              {bc.customers.how_kept && <p><span>How they're kept</span>{bc.customers.how_kept}</p>}
            </div>
          )}
          {bc?.payback_logic && <p className="bp-payback">{bc.payback_logic}</p>}
          {bc?.cost_of_inaction && (
            <p className="bp-inaction">
              <strong>What staying as you are costs: </strong>
              {bc.cost_of_inaction}
            </p>
          )}
        </div>
      )}

      {/* the customer journey — where each module lives in their experience */}
      {(preview.journey?.stages?.length ?? 0) > 0 && (
        <div>
          <p className="studio-kicker mb-2">The customer journey</p>
          <p className="studio-plan-rostertext mb-4">
            What your customer does at every stage — and which parts of the system work for
            them behind the scenes.
          </p>
          <div className="bp-journey">
            {preview.journey!.stages.map((st, i) => (
              <div className="bp-jstage" key={st.stage + i}>
                <div className="bp-jstage-head">
                  <span className="bp-jstage-no">{String(i + 1).padStart(2, '0')}</span>
                  <p className="bp-jstage-name">{st.stage}</p>
                </div>
                {st.customer_action && (
                  <p className="bp-jline"><span>Your customer</span>{st.customer_action}</p>
                )}
                {st.frontstage && (
                  <p className="bp-jline"><span>What they see</span>{st.frontstage}</p>
                )}
                {st.backstage_modules.length > 0 && (
                  <div className="bp-jmods">
                    <span className="bp-jline-label">Working backstage</span>
                    {st.backstage_modules.map((id) => (
                      <span className="bp-jmod" key={id}>{moduleNameById[id] ?? id}</span>
                    ))}
                  </div>
                )}
                {st.fail_point_removed && (
                  <p className="bp-jfixed">No longer goes wrong: {st.fail_point_removed}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* the scoreboard — baselines only ever the owner's numbers */}
      {preview.scoreboard.length > 0 && (
        <div>
          <p className="studio-kicker mb-2">The scoreboard</p>
          <p className="studio-plan-rostertext mb-4">
            How you'll know it's working. Baselines are your own numbers — where we don't have
            one, it says so.
          </p>
          <div className="bp-scorewrap">
            <table className="bp-score">
              <thead>
                <tr><th>Metric</th><th>Baseline</th><th>Target</th><th>Owner</th><th>Review</th></tr>
              </thead>
              <tbody>
                {preview.scoreboard.map((r) => (
                  <tr key={r.metric}>
                    <td className="bp-score-metric">{r.metric}</td>
                    <td>{r.baseline ?? '—'}</td>
                    <td>{r.target ?? '—'}</td>
                    <td>{r.owner ?? '—'}</td>
                    <td>{r.review ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DownloadButton refId={preview.id} kind="blueprint" className="studio-ghost-btn bp-pdfbtn">
            Download the blueprint (PDF)
          </DownloadButton>
        </div>
      )}

      {/* the system at a glance: module rows + honest sidebar */}
      <div className="bp-glance">
        <div>
          <p className="studio-kicker mb-2">The system at a glance</p>
          <h3 className="studio-display bp-glance-title">
            {mods.length} modules. {agentMods.length} AI agents. One seamless workflow.
          </h3>
          <div className="bp-modrows">
            {mods.map((m, i) => (
              <a className="bp-modrow" href={`#bp-mod-${i}`} key={m.id || i}>
                <span className="bp-modrow-no">{String(i + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <div className="bp-modrow-head">
                    <h4>{m.name}</h4>
                    <span className={`bp-modrow-badge${m.spec?.ai?.role ? '' : ' bp-modrow-badge--none'}`}>
                      {m.spec?.ai?.role ? 'AI agent' : 'No AI — deliberate'}
                    </span>
                  </div>
                  <p>{m.purpose}</p>
                  <span className="bp-modrow-more">Learn more ↓</span>
                </div>
              </a>
            ))}
          </div>
          <div className="bp-oversight">
            <Icon path={INTAKE_ICONS.shield} className="w-5 h-5" />
            <p>
              <strong>Human oversight at every critical step.</strong> Every agent has a hand-off
              trigger and things it may never do — written into its spec.
            </p>
          </div>
        </div>

        <aside className="bp-side">
          {bc && (bc.pricing_levers?.length ?? 0) > 0 && (
            <div className="bp-sidecard">
              <p className="bp-mini-kicker">Pricing levers</p>
              {bc.pricing_levers.map((l) => (
                <div className="bp-siderow" key={l}>
                  <CheckIcon className="studio-plan-checkicon" />
                  <p>{l}</p>
                </div>
              ))}
            </div>
          )}
          <div className="bp-sidecard">
            <p className="bp-mini-kicker">Build details</p>
            <div className="bp-sidefact"><span>Core modules</span><strong>{mods.length}</strong></div>
            <div className="bp-sidefact"><span>AI agents</span><strong>{agentMods.length}</strong></div>
            <div className="bp-sidefact"><span>Integrations</span><strong>{integrations.length}</strong></div>
            {preview.timeline && (
              <div className="bp-sidefact"><span>Your timeline</span><strong>{preview.timeline}</strong></div>
            )}
            {preview.budget_range && (
              <div className="bp-sidefact"><span>Scope appetite</span><strong>{preview.budget_range}</strong></div>
            )}
          </div>
          {buildFirst && (
            <div className="bp-sidecard">
              <p className="bp-mini-kicker">What we'd build first</p>
              <BlueprintProse text={buildFirst.body} />
            </div>
          )}
        </aside>
      </div>

      {/* one deep section per module */}
      {mods.map((m, i) => {
        const spec = m.spec;
        const tech = (m as { tech?: TechRail }).tech;
        return (
          <div className="bp-module" id={`bp-mod-${i}`} key={m.id || i}>
            <div>
              <div className="bp-module-head">
                <span className="bp-modrow-no">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="studio-display">{m.name}</h3>
              </div>
              <p className="bp-mini-kicker mt-4">How it works</p>
              <p className="bp-module-purpose">{m.purpose}</p>
              {(spec?.features?.length ?? 0) > 0 && (
                <div className="studio-plan-checklist mt-3">
                  {spec!.features.map((f, j) => (
                    <div className="studio-plan-checkrow" key={f.name || j}>
                      <CheckIcon className="studio-plan-checkicon" />
                      <p><strong className="text-slate-900">{f.name}.</strong> {f.description}</p>
                    </div>
                  ))}
                </div>
              )}
              {(spec?.data?.length ?? 0) > 0 && (
                <>
                  <p className="bp-mini-kicker mt-5">What it keeps track of</p>
                  <div className="bp-datachips">
                    {spec!.data.slice(0, 6).map((d) => (
                      <span key={d}>{d}</span>
                    ))}
                  </div>
                </>
              )}
            </div>
            <aside className="bp-module-rail">
              {spec?.ai?.role && (
                <div className="bp-sidecard">
                  <p className="bp-mini-kicker">The AI in this module</p>
                  <p className="bp-module-airole">{spec.ai.role}</p>
                  {((tech?.ai_agent?.brain?.length ?? 0) > 0) && (
                    <p className="bp-module-aibrain">
                      <span>Grounded in: </span>
                      {tech!.ai_agent!.brain!.slice(0, 3).join(' · ')}
                    </p>
                  )}
                </div>
              )}
              {(spec?.ai?.hands_off || tech?.ai_agent?.escalation) && (
                <div className="bp-sidecard bp-sidecard--human">
                  <p className="bp-mini-kicker">Human review</p>
                  <p>{spec?.ai?.hands_off || tech?.ai_agent?.escalation}</p>
                </div>
              )}
            </aside>
          </div>
        );
      })}
    </div>
  );
}

/** The blueprint's and technical plan's prompts each mandate a fixed
 *  `## Heading` skeleton (see blueprint.j2 / technical_plan.j2), so this
 *  parses out named sections and gives each a bespoke cinematic treatment
 *  instead of one long scroll of prose. An unrecognized or older document
 *  (missing the sections this looks for) falls back to BlueprintProse. */
function BlueprintCinematic({ preview }: { preview: StudioPreview }) {
  const md = preview.mvp_blueprint ?? '';
  const sections = useMemo(() => splitH2Sections(md), [md]);
  const vision = findSection(sections, /vision/);
  const employeesSec = findSection(sections, /employee/);
  const featuresSec = findSection(sections, /feature/);
  const journeySec = findSection(sections, /experience|customer/);
  const winsSec = findSection(sections, /win/);

  if (!vision && !employeesSec) return <BlueprintProse text={md} />;

  const visionText = vision ? stripInlineMarkdown(vision.body.replace(/\n+/g, ' ')) : preview.preview_summary ?? '';
  const employees = employeesSec ? splitH3Subsections(employeesSec.body) : [];
  const employeeCards = employees.length
    ? employees
    : preview.ai_features.map((f) => ({ title: f.name, text: f.description }));
  const journeySteps = journeySec ? parseListItems(journeySec.body) : [];
  const winsIntro = winsSec ? firstParagraph(winsSec.body) : '';
  const winsChecks = winsSec ? parseListItems(winsSec.body) : [];
  const featureItems = featuresSec ? parseListItems(featuresSec.body) : [];

  return (
    <div className="studio-plan">
      <PlanHero kicker="The vision" title={preview.concept_name || preview.business_name} lead={visionText} />

      {employeeCards.length > 0 && (
        <div className="studio-plan-roster">
          {employeeCards.map((emp, i) => (
            <div className="studio-plan-rostercard" key={emp.title || i}>
              <span className="studio-plan-avatar">{initials(emp.title) || 'AI'}</span>
              <div className="min-w-0">
                <p className="studio-plan-eyebrow">Employee {String(i + 1).padStart(2, '0')}</p>
                <p className="studio-plan-rostername">{emp.title}</p>
                <p className="studio-plan-rostertext">{emp.text}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {(journeySteps.length > 0 || winsIntro) && (
        <div className="studio-plan-columns">
          {journeySteps.length > 0 && (
            <PlanPanel eyebrow="How your customers will experience it">
              <div className="studio-plan-timeline">
                {journeySteps.map((step, i) => (
                  <div className="studio-plan-timeline-item" key={i}>
                    <span className="studio-plan-timeline-no">{i + 1}</span>
                    <p>{step.text || step.title}</p>
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
          {winsIntro && (
            <PlanPanel eyebrow="Why this wins">
              <p className="studio-plan-checklist-lead">{winsIntro}</p>
              {winsChecks.length > 0 && (
                <div className="studio-plan-checklist">
                  {winsChecks.map((c, i) => (
                    <div className="studio-plan-checkrow" key={i}>
                      <CheckIcon className="studio-plan-checkicon" />
                      <p>{c.text || c.title}</p>
                    </div>
                  ))}
                </div>
              )}
            </PlanPanel>
          )}
        </div>
      )}

      {featureItems.length > 0 && (
        <div>
          <p className="studio-kicker mb-4">Core features</p>
          <div className="studio-plan-features">
            {featureItems.map((f, i) => (
              <div className="studio-plan-featurecard" key={f.title || i}>
                <span className="studio-plan-featureno">{String(i + 1).padStart(2, '0')}</span>
                <p className="studio-plan-featuretitle">{f.title}</p>
                {f.text && <p className="studio-plan-featuretext">{f.text}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** One module of the technical plan, rendered as a full-width card with
 *  the facts organized into zones instead of a flat label:text pile — an
 *  intro line, a breathing facts grid, a highlighted "where the AI works"
 *  panel, numbered build steps, checkmarked finish criteria, and the dev
 *  handles as a muted footer. Facet labels are matched loosely so both
 *  document generations (developer-voice and owner-voice) land in the
 *  right zone; unknown labels fall into the facts grid rather than
 *  disappearing. */
function ModuleSpecCard({ index, title, raw }: { index: number; title: string; raw: string }) {
  const zones = useMemo(() => {
    const facets = parseListItems(raw);
    let intro = '';
    const ai: { label: string; text: string }[] = [];
    const facts: { label: string; text: string }[] = [];
    let steps: string[] = [];
    const done: string[] = [];
    let team = '';
    let collectingSteps = false;

    for (const f of facets) {
      const label = (f.title || '').toLowerCase();
      if (!f.title) {
        // Titleless items are the nested bullets of the facet before them —
        // in practice the numbered build steps.
        if (collectingSteps) steps.push(f.text);
        else if (facts.length > 0) facts[facts.length - 1].text += ` ${f.text}`;
        continue;
      }
      collectingSteps = false;
      if (label.includes('what this part does')) intro = f.text;
      else if (label.includes('gets built') || label.includes('build sequence')) {
        collectingSteps = true;
        // Inline form: "1. First... 2. Then..." on one line.
        const inline = f.text.split(/\s*\d+[.)]\s+/).filter(Boolean);
        if (inline.length > 1) steps = inline;
      } else if (label.includes('finished when') || label.includes('done when')) {
        done.push(...f.text.split(/\s*;\s+/).filter(Boolean));
      } else if (label.includes('build team')) team = f.text;
      else if (
        label.startsWith('what the ai') || label.includes('the ai agent') || label.startsWith('agent') ||
        label.includes('what it knows') || label.includes('hands to you') || label.includes('never do') ||
        label.includes('escalation') || label.includes('guardrail') || label.includes('evaluate')
      ) {
        ai.push({ label: f.title, text: f.text });
      } else {
        facts.push({ label: f.title, text: f.text });
      }
    }
    return { intro, ai, facts, steps, done, team };
  }, [raw]);

  return (
    <article className="studio-modspec">
      <header className="studio-modspec-head">
        <span className="studio-plan-featureno">{String(index + 1).padStart(2, '0')}</span>
        <h3>{title}</h3>
      </header>
      {zones.intro && <p className="studio-modspec-intro">{zones.intro}</p>}

      {zones.facts.length > 0 && (
        <div className="studio-modspec-grid">
          {zones.facts.map((f) => (
            <div className="studio-modspec-cell" key={f.label}>
              <p className="studio-modspec-label">{f.label}</p>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      )}

      {zones.ai.length > 0 && (
        <div className="studio-modspec-ai">
          <p className="studio-modspec-label studio-modspec-label--ai">
            <span className="studio-ai-dot" aria-hidden="true" />
            Where the AI works in this part
          </p>
          <div className="studio-modspec-grid studio-modspec-grid--ai">
            {zones.ai.map((f) => (
              <div className="studio-modspec-cell" key={f.label}>
                <p className="studio-modspec-label">{f.label}</p>
                <p>{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {(zones.steps.length > 0 || zones.done.length > 0) && (
        <div className="studio-modspec-buildrow">
          {zones.steps.length > 0 && (
            <div className="studio-modspec-cell">
              <p className="studio-modspec-label">How this part gets built, in order</p>
              <ol className="studio-modspec-steps">
                {zones.steps.map((s, i) => (
                  <li key={i}>
                    <span className="studio-plan-timeline-no">{i + 1}</span>
                    <p>{s}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {zones.done.length > 0 && (
            <div className="studio-modspec-cell">
              <p className="studio-modspec-label">It's finished when</p>
              <div className="studio-plan-checklist">
                {zones.done.map((c, i) => (
                  <div className="studio-plan-checkrow" key={i}>
                    <CheckIcon className="studio-plan-checkicon" />
                    <p>{c}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {zones.team && (
        <p className="studio-modspec-team">
          <span>For your build team:</span> {zones.team}
        </p>
      )}
    </article>
  );
}

function TechnicalCinematic({ preview }: { preview: StudioPreview }) {
  const md = preview.technical_plan ?? '';
  const sections = useMemo(() => splitH2Sections(md), [md]);
  // Each matcher accepts every generation of the document's headings —
  // "Architecture overview" (old), "How your system works" (owner-voice era),
  // and so on — since stored documents never regenerate.
  const arch = findSection(sections, /architecture|how your system/);
  const blocks = findSection(sections, /building blocks|components/);
  const moduleSpecs = findSection(sections, /module spec|parts, one by one/);
  const selfBuild = findSection(sections, /yourself|own team|bringing it to life/);
  const aiWork = findSection(sections, /employees work|how the ai/);
  const implPhases = findSection(sections, /implementation|applying it/);
  const security = findSection(sections, /security|information safe|data/);

  if (!arch && !blocks && !aiWork && !moduleSpecs) return <BlueprintProse text={md} />;

  const archText = arch ? stripInlineMarkdown(arch.body.replace(/\n+/g, ' ')) : '';
  const moduleCards = moduleSpecs ? splitH3Subsections(moduleSpecs.body) : [];
  const buildBlocks = blocks ? parseListItems(blocks.body) : [];
  const aiRows = aiWork ? parseListItems(aiWork.body) : [];
  const securityRows = security ? parseListItems(security.body) : [];
  const phases = implPhases ? parseNestedPhases(implPhases.body) : [];

  return (
    <div className="studio-plan">
      <PlanHero
        kicker="System architecture"
        title={`${preview.concept_name || preview.business_name} — how it gets built`}
        lead={archText}
      />

      {(aiRows.length > 0 || securityRows.length > 0) && (
        <div className="studio-plan-columns">
          {aiRows.length > 0 && (
            <PlanPanel eyebrow="How the AI employees work">
              <div className="studio-plan-roster studio-plan-roster--stacked">
                {aiRows.map((row, i) => (
                  <div className="studio-plan-rostercard" key={row.title || i}>
                    <span className="studio-plan-avatar">{initials(row.title) || 'AI'}</span>
                    <div className="min-w-0">
                      <p className="studio-plan-rostername">{row.title}</p>
                      <p className="studio-plan-rostertext">{row.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
          {securityRows.length > 0 && (
            <PlanPanel eyebrow="Data, security &amp; reliability">
              <div className="studio-plan-checklist">
                {securityRows.map((row, i) => (
                  <div className="studio-plan-checkrow" key={i}>
                    <CheckIcon className="studio-plan-checkicon" />
                    <p>{row.text || row.title}</p>
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
        </div>
      )}

      {moduleCards.length > 0 && (
        <div>
          <p className="studio-kicker mb-5">The parts, one by one</p>
          <div className="studio-modspecs">
            {moduleCards.map((m, i) => (
              <ModuleSpecCard key={m.title || i} index={i} title={m.title} raw={m.raw || m.text} />
            ))}
          </div>
        </div>
      )}

      {selfBuild && (
        <PlanPanel eyebrow="Bringing it to life yourself">
          <p className="studio-plan-rostertext mb-3">
            This plan is complete enough to execute without us. If you take it to your own team,
            this is the honest guide.
          </p>
          <BlueprintProse text={selfBuild.body} />
        </PlanPanel>
      )}

      {buildBlocks.length > 0 && (
        <div>
          <p className="studio-kicker mb-4">The building blocks</p>
          <div className="studio-plan-features">
            {buildBlocks.map((b, i) => (
              <div className="studio-plan-featurecard" key={b.title || i}>
                <span className="studio-plan-featureno">{String(i + 1).padStart(2, '0')}</span>
                <p className="studio-plan-featuretitle">{b.title}</p>
                {b.text && <p className="studio-plan-featuretext">{b.text}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {phases.length > 0 && (
        <div>
          <p className="studio-kicker mb-4">Implementation phases</p>
          <div className="studio-plan-roadmap">
            {phases.map((phase, i) => (
              <div className="studio-plan-roadmap-item" key={phase.title || i}>
                <span className="studio-plan-roadmap-no">{i + 1}</span>
                <div className="studio-plan-roadmap-card">
                  <p className="studio-plan-roadmap-title">{phase.title}</p>
                  {phase.fields.map((field, j) => (
                    <p className="studio-plan-roadmap-field" key={j}>
                      {field.label && <span>{field.label}: </span>}
                      {field.text}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const PLAYBOOK_PHASES: { id: 'before' | 'during' | 'after'; label: string; sub: string }[] = [
  { id: 'before', label: 'Before the build', sub: 'What you prepare so the build lands on solid ground' },
  { id: 'during', label: 'During the build', sub: 'What happens while the system takes shape' },
  { id: 'after', label: 'After launch', sub: 'The numbers you watch, and what each one triggers' },
];

const PLAYBOOK_WHO: Record<string, string> = { you: 'You', bmv: 'BMV', partner: 'Partner' };

/** The execution playbook — rendered from the structured steps directly,
 *  grouped into before/during/after, each step badged with who owns it.
 *  Closes with the people plan: what the AI employees cover (so no hire is
 *  needed) and the honest conditions under which humans ARE needed. */
function PlaybookCinematic({ preview }: { preview: StudioPreview }) {
  const pb = preview.playbook;
  if (!pb) return null;
  const people = pb.people_plan ?? {};

  return (
    <div className="studio-plan">
      <PlanHero
        kicker="Execution playbook"
        title="Every step, in order — and who does it"
        lead="The software is one actor in this plan. This is everything else: what you prepare, who does what, which partners you bring in, and what you watch once it's live."
      />

      {(pb.quick_wins?.length ?? 0) > 0 && (
        <div>
          <p className="studio-kicker mb-1">Your first 30 days</p>
          <p className="studio-plan-rostertext mb-4">
            Real value before any software exists — each of these stands on its own.
          </p>
          <div className="studio-qwins">
            {pb.quick_wins!.map((w, i) => (
              <div className="studio-qwin" key={w.title + i}>
                <div className="studio-qwin-head">
                  <p className="studio-qwin-title">{w.title}</p>
                  {w.no_software && <span className="studio-qwin-tag">No software needed</span>}
                </div>
                {w.detail && <p className="studio-plan-rostertext mt-1">{w.detail}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {PLAYBOOK_PHASES.map((phase) => {
        const steps = pb.steps.filter((s) => s.phase === phase.id);
        if (steps.length === 0) return null;
        return (
          <div key={phase.id}>
            <p className="studio-kicker mb-1">{phase.label}</p>
            <p className="studio-plan-rostertext mb-4">{phase.sub}</p>
            <div className="studio-plan-roadmap">
              {steps.map((s, i) => (
                <div className="studio-plan-roadmap-item" key={`${phase.id}-${i}`}>
                  <span className="studio-plan-roadmap-no">{i + 1}</span>
                  <div className="studio-plan-roadmap-card">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <p className="studio-plan-roadmap-title">{s.title}</p>
                      <span className="studio-pb-badges">
                        {s.horizon && <span className="studio-pb-horizon">{s.horizon}</span>}
                        <span className={`studio-pb-who studio-pb-who--${s.who}`}>
                          {PLAYBOOK_WHO[s.who] ?? s.who}
                        </span>
                      </span>
                    </div>
                    <p className="studio-plan-rostertext mt-1">{s.detail}</p>
                    {(s.needs?.length ?? 0) > 0 && (
                      <p className="studio-plan-roadmap-field">
                        <span>Needs: </span>
                        {s.needs!.join(' · ')}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {preview.risks.length > 0 && (
        <div>
          <p className="studio-kicker mb-1">What could make this fail — honestly</p>
          <p className="studio-plan-rostertext mb-4">
            The real risks are usually habits, not technology. Each one has a counter-move.
          </p>
          <div className="studio-risks">
            {preview.risks.map((r, i) => (
              <div className="studio-risk" key={r.risk + i}>
                <p className="studio-risk-name">{r.risk}</p>
                {r.mitigation && (
                  <p className="studio-plan-rostertext mt-1">
                    <strong>Counter-move:</strong> {r.mitigation}
                  </p>
                )}
                {r.who_feels_it && <p className="studio-risk-who">Felt by: {r.who_feels_it}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {preview.checklists && (preview.checklists.checklists.length > 0 || preview.checklists.forms.length > 0) && (
        <div>
          <p className="studio-kicker mb-1">Forms & checklists</p>
          <p className="studio-plan-rostertext mb-4">
            The artifacts your team holds in their hands from day one — the full printable set
            is in the operations manual.
          </p>
          <div className="studio-checkgrid">
            {preview.checklists.checklists.map((c) => (
              <div className="studio-checkcard" key={c.name}>
                <p className="studio-checkcard-name">{c.name}</p>
                {c.when && <p className="studio-checkcard-when">{c.when}</p>}
                <ul>
                  {c.items.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
            {preview.checklists.forms.map((f) => (
              <div className="studio-checkcard studio-checkcard--form" key={f.name}>
                <p className="studio-checkcard-name">{f.name} <span>form</span></p>
                {f.purpose && <p className="studio-checkcard-when">{f.purpose}</p>}
                <p className="studio-checkcard-fields">{f.fields.join(' · ')}</p>
              </div>
            ))}
          </div>
          <DownloadButton refId={preview.id} kind="operations" className="studio-ghost-btn bp-pdfbtn">
            Download the operations manual (PDF)
          </DownloadButton>
        </div>
      )}

      {((people.ai_covers?.length ?? 0) > 0 || (people.humans_needed?.length ?? 0) > 0) && (
        <div className="studio-plan-columns">
          {(people.ai_covers?.length ?? 0) > 0 && (
            <PlanPanel eyebrow="Your AI employees cover this — no hire needed">
              <div className="studio-plan-checklist">
                {people.ai_covers!.map((line, i) => (
                  <div className="studio-plan-checkrow" key={i}>
                    <CheckIcon className="studio-plan-checkicon" />
                    <p>{line}</p>
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
          {(people.humans_needed?.length ?? 0) > 0 && (
            <PlanPanel eyebrow="When to bring in humans">
              <div className="studio-plan-roster studio-plan-roster--stacked">
                {people.humans_needed!.map((h, i) => (
                  <div className="studio-plan-rostercard" key={h.role || i}>
                    <span className="studio-plan-avatar">{initials(h.role) || 'HR'}</span>
                    <div className="min-w-0">
                      <p className="studio-plan-rostername">{h.role}</p>
                      <p className="studio-plan-roadmap-field">
                        <span>When: </span>
                        {h.when}
                      </p>
                      <p className="studio-plan-rostertext">{h.why}</p>
                    </div>
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
        </div>
      )}
    </div>
  );
}

/** Packages, tailored add-ons and the deck export — the same canonical,
 *  no-public-prices catalog the landing page's Packages section and the old
 *  pipeline's BuildRequestCTA already use (data/buildPlans.ts), read from
 *  this run's own preview instead of invented for the occasion. There is no
 *  build-request endpoint on consultant-service, so the call to action is
 *  WhatsApp — already wired, no backend dependency. */
function PlansPanel({ preview }: { preview: StudioPreview }) {
  const [planId, setPlanId] = useState<BuildPlan['id']>('growth');
  const [addonIds, setAddonIds] = useState<string[]>([]);

  const roleLabels = useMemo(
    () => [...new Set(preview.generated_pages.attraction_images.map((s) => s.role_label))],
    [preview.generated_pages.attraction_images],
  );

  const addons = useMemo(
    () =>
      suggestBusinessAddons({
        businessName: preview.business_name,
        conceptName: preview.concept_name,
        industry: preview.industry,
        mainProblem: preview.main_problem,
        desiredOutcome: preview.desired_outcome,
        previewFeatures: preview.preview_features,
        aiFeatures: preview.ai_features,
        roleLabels,
      }),
    [preview, roleLabels],
  );

  const plan = BUILD_PLANS.find((p) => p.id === planId) ?? BUILD_PLANS[1];
  const includedAddons = addons.filter((a) => addonIncluded(a, planId));
  const optionalAddons = addons.filter((a) => addonAvailable(a, planId));

  const selectPlan = (id: BuildPlan['id']) => {
    setPlanId(id);
    setAddonIds((prev) =>
      prev.filter((aid) => {
        const addon = addons.find((a) => a.id === aid);
        return addon ? addonAvailable(addon, id) : false;
      }),
    );
  };

  const toggleAddon = (id: string) => {
    setAddonIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectionSummary = summarizeSelection(planId, addonIds, addons, BUILD_PLANS);
  const demoUrl = `${window.location.origin}${studioResultPath(preview.id)}`;
  const buildEmailHref = consultingEmailUrl(
    `Build request — ${preview.business_name} (demo #${preview.id})`,
    `Hi,\n\nI reviewed my demo (${demoUrl}) and I'd like to move forward.\n\n${selectionSummary}\n\nPlease send the exact quote.\n`,
  );
  const deepDiveEmailHref = consultingEmailUrl(
    `Deep-dive request — ${preview.business_name} (demo #${preview.id})`,
    `Hi,\n\nI'd like to book the executive working session for my engagement (${demoUrl}).\n\nPreferred days and times: \n`,
  );

  return (
    <div className="studio-plan">
      <div className="studio-plan-hero">
        <p className="studio-kicker mb-3">Next step</p>
        <h2 className="studio-display text-2xl sm:text-3xl font-bold text-navy mb-4">
          Choose how we build it
        </h2>
        <p className="studio-plan-hero-lead">
          Packages and add-ons below are written from this preview. No public prices — we quote
          after you choose and confirm scope.
        </p>
        <div className="studio-plans-downloads mt-6">
          {preview.mvp_blueprint && (
            <DownloadButton refId={preview.id} kind="zip" className="studio-cta studio-plans-deckbtn">
              Download your full plan (ZIP — all three volumes)
            </DownloadButton>
          )}
          {preview.deck_available && (
            <DownloadButton refId={preview.id} kind="pptx" className="studio-ghost-btn">
              Download the deck (PowerPoint)
            </DownloadButton>
          )}
        </div>
      </div>

      <div className="studio-plancards">
        {BUILD_PLANS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`studio-plancard${planId === p.id ? ' studio-plancard--active' : ''}`}
            onClick={() => selectPlan(p.id)}
          >
            {p.badge && <span className="studio-plancard-badge">{p.badge}</span>}
            <p className="studio-plancard-name">{p.name}</p>
            <p className="studio-plancard-tagline">{p.tagline}</p>
            <p className="studio-plancard-timeline">{p.timeline}</p>
            <ul className="studio-plancard-includes">
              {p.includes.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </button>
        ))}
      </div>

      {(includedAddons.length > 0 || optionalAddons.length > 0) && (
        <div className="studio-plan-columns">
          {includedAddons.length > 0 && (
            <PlanPanel eyebrow={`Included in ${plan.name}`}>
              <div className="studio-addons">
                {includedAddons.map((addon) => (
                  <div className="studio-addon studio-addon--included" key={addon.id}>
                    <p className="studio-addon-name">{addon.name}</p>
                    {addon.description && <p className="studio-addon-desc">{addon.description}</p>}
                    {addon.whyForYou && <p className="studio-addon-why">Why for you: {addon.whyForYou}</p>}
                  </div>
                ))}
              </div>
            </PlanPanel>
          )}
          {optionalAddons.length > 0 && (
            <PlanPanel eyebrow="Optional upgrades">
              <div className="studio-addons">
                {optionalAddons.map((addon) => {
                  const on = addonIds.includes(addon.id);
                  return (
                    <button
                      key={addon.id}
                      type="button"
                      className={`studio-addon studio-addon--optional${on ? ' studio-addon--on' : ''}`}
                      onClick={() => toggleAddon(addon.id)}
                    >
                      <p className="studio-addon-name">{addon.name}</p>
                      {addon.description && <p className="studio-addon-desc">{addon.description}</p>}
                      <span className="studio-addon-toggle">{on ? 'Added' : 'Add'}</span>
                    </button>
                  );
                })}
              </div>
            </PlanPanel>
          )}
        </div>
      )}

      <div className="studio-plans-actions">
        <a className="studio-cta studio-stepnav-cta" href={buildEmailHref}>
          Email us this plan
        </a>
        <p className="studio-hint">
          Goes straight to consulting@buildmyversion.com — we reply with the exact quote. Or just
          reply to the email you gave us; we already have the blueprint.
        </p>
      </div>

      {/* The middle rung of the ladder — for readers convinced by the plan
          but not ready to commit to a build. */}
      <div className="studio-deepdive">
        <div className="studio-deepdive-info">
          <p className="studio-kicker mb-2">Not ready to choose?</p>
          <p className="studio-deepdive-title">Book the executive working session</p>
          <p className="studio-deepdive-text">
            Ninety minutes with your engagement lead inside your real operation. We pressure-test
            this plan against your constraints — modules re-scoped, the business case recomputed
            from your actual numbers — and you leave with the corrected plan and an exact quote.
          </p>
        </div>
        <div className="studio-deepdive-side">
          <p className="studio-deepdive-price">Terms on request</p>
          <p className="studio-deepdive-credit">The session fee is credited in full against your build</p>
          <a className="studio-cta studio-deepdive-btn" href={deepDiveEmailHref}>
            Request the session
            <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  );
}

export default function StudioPage() {
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const { id: idParam } = useParams<{ id: string }>();
  // A run's address: its unguessable slug (/engagements/<public_id>) for
  // the owner, or a plain numeric id for showcase and legacy links.
  const routeId = idParam && /^[A-Za-z0-9_-]{1,40}$/.test(idParam) ? idParam : null;

  const [act, setAct] = useState<Act>(routeId == null ? 'intake' : 'loading');
  const [progress, setProgress] = useState<StudioProgress | null>(null);
  const [preview, setPreview] = useState<StudioPreview | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [failureDetail, setFailureDetail] = useState<string | null>(null);
  const [decision, setDecision] = useState<StudioDecision | null>(null);
  const [gateBusy, setGateBusy] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);
  const [figures, setFigures] = useState<StudioFigure[]>([]);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [evidenceNote, setEvidenceNote] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  // Which half of the run this is. The diagnosis stops at the gate and the
  // build only starts when the client presses it, so the running screen has
  // to say which one it is showing — the server's `status` says so too, but
  // it lags a poll behind the click, and a stale value flashed the wrong
  // half's stages for a couple of seconds after every button.
  const [phase, setPhase] = useState<RunPhase>('diagnosing');
  const [activeTab, setActiveTab] = useState<ResultTab>('screens');
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  const [copied, setCopied] = useState(false);
  // Screens whose file did not load. A missing byte gets an honest tile
  // instead of a browser's broken-image glyph.
  const [brokenSrc, setBrokenSrc] = useState<Record<string, true>>({});

  const [form, setForm] = useState({
    business_name: '',
    business_description: '',
    email: '',
    industry: '',
    main_problem: '',
    target_customers: '',
    desired_outcome: '',
    reference_url: '',
    what_you_like: '',
    // 'maybe', not 'yes'. The question this used to answer is gone, so this is
    // no longer something the client chose — it is what we tell every stage
    // about them. 'yes' says "the client wants AI", a preference nobody
    // expressed, sent to `decide` in the very engagement that exists to find
    // out whether software is the answer. 'maybe' is the honest default:
    // recommend it only where it clearly earns its place.
    needs_ai: 'maybe',
    budget_range: BUDGET_OPTIONS[0],
    timeline: 'Flexible',
    whatsapp: '',
    site_url: '',
    revenue_today: '',
    operating_stage: 'operating' as OperatingStage,
    engagement_type: 'full' as EngagementType,
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(0);
  // The tailored discovery questions. Prefetched in the background the
  // moment the brief is complete enough (leaving the Challenge step), so
  // by the time the visitor reaches the Numbers step they are waiting -
  // the step feels like the consultant already read the brief.
  // The interview accumulates: each round is kept on screen so the client can
  // see and change what they already told us.
  const [rounds, setRounds] = useState<Round[]>([]);
  const [interviewDone, setInterviewDone] = useState(false);
  const [interviewClosing, setInterviewClosing] = useState('');
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [numbersAnswers, setNumbersAnswers] = useState<Record<string, string>>({});
  const discoveryKey = useRef<string | null>(null);
  // One question at a time: the ids they have answered or said they don't
  // know. The current question is the first one not in here.
  const [committed, setCommitted] = useState<string[]>([]);
  const roundAsked = useRef(0);
  // The case file beside the conversation, refreshed as they answer, and the
  // one played back before the diagnosis. Latest call wins.
  const [caseFile, setCaseFile] = useState<CaseFile | null>(null);
  const [caseLoading, setCaseLoading] = useState(false);
  const caseCall = useRef<{ key: string; promise: Promise<CaseFile> } | null>(null);
  const [playbackFile, setPlaybackFile] = useState<CaseFile | null>(null);
  const [playbackLoading, setPlaybackLoading] = useState(false);
  const [correction, setCorrection] = useState('');
  const [finishError, setFinishError] = useState<string | null>(null);
  // Files they dropped into the conversation, sent with the engagement.
  const [files, setFiles] = useState<File[]>([]);
  const [pilotLog, setPilotLog] = useState<PilotEntry[]>([]);
  // The plan on a finished package, when it is written after the fact.
  const [revealPlan, setRevealPlan] = useState<ActionPlan | null>(null);
  // The review gate. The token arrives as ?review=... on the reviewer's
  // link; its presence turns the page into the review view of the run.
  const reviewToken = useMemo(
    () => new URLSearchParams(window.location.search).get('review'),
    [],
  );
  const [teaser, setTeaser] = useState<StudioTeaser | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editBp, setEditBp] = useState('');
  const [editTech, setEditTech] = useState('');
  const [qaOpen, setQaOpen] = useState(false);
  const { user, isAuthenticated, loading: authLoading } = useAuth();
  const [privateReason, setPrivateReason] = useState<'signin' | 'foreign'>('signin');

  const dialogRef = useRef<HTMLDialogElement>(null);
  const elapsed = useElapsed(act === 'building', startedAt);
  // The server starts a fresh trail for every diagnosis, so whatever the poll
  // returns IS the current run's reasoning — no client-side merging needed.
  const thinking = progress?.thinking ?? [];

  const resultUrl = routeId != null ? `${window.location.origin}${studioResultPath(routeId)}` : null;

  const showResult = useCallback(async (id: StudioRef) => {
    try {
      const data = await getStudioPreview(id, reviewToken);
      if (isPendingTeaser(data)) {
        setTeaser(data);
        setAct('pending');
        return;
      }
      setPreview(data);
      setActiveTab('screens');
      setAct('reveal');
    } catch (err) {
      if (isNotFound(err)) setAct('missing');
      else if (isUnauthorized(err)) {
        setPrivateReason('signin');
        setAct('private');
      } else if (isForbidden(err)) {
        setPrivateReason('foreign');
        setAct('private');
      } else {
        setFailureDetail('Your screens were generated, but the studio could not load them just now. Refreshing this page usually brings them back.');
        setAct('failed');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewToken]);

  // The brief behind the gate. Loaded rather than derived from the poll,
  // because the poll carries a stage label and a percentage — not the
  // reasoning the client is being asked to approve.
  const loadDecision = useCallback(async (id: StudioRef) => {
    try {
      setDecision(await getStudioDecision(id));
      setGateError(null);
      setAct('decision');
      // Figures are a separate read and a failure to load them must not cost
      // the client their brief — the panel simply starts empty.
      getStudioEvidence(id)
        .then((e) => setFigures(e.figures ?? []))
        .catch(() => undefined);
    } catch (err) {
      if (isUnauthorized(err)) {
        setPrivateReason('signin');
        setAct('private');
      } else if (isForbidden(err)) {
        setPrivateReason('foreign');
        setAct('private');
      } else {
        // The run is intact and still waiting — only the read failed. Say so
        // rather than reporting a failure that did not happen.
        setFailureDetail('Your diagnosis is ready, but the studio could not load it just now. Refreshing this page usually brings it back.');
        setAct('failed');
      }
    }
  }, []);

  const approveDecision = useCallback(async (scope?: { budget_range: string; timeline: string }) => {
    if (routeId == null) return;
    setGateBusy(true);
    setGateError(null);
    try {
      await approveStudioDecision(routeId, scope);
      // Whether this caller or an earlier double-press claimed the run, the
      // build is now going — either way the honest next screen is the same.
      // The clock restarts with it: it counts the build, not the consultation.
      setStartedAt(Date.now());
      setPhase('building');
      setAct('building');
    } catch {
      setGateError('We could not start the build just now. Try again in a moment.');
    } finally {
      setGateBusy(false);
    }
  }, [routeId]);

  const uploadEvidence = useCallback(async (file: File) => {
    if (routeId == null) return;
    setEvidenceBusy(true);
    setEvidenceError(null);
    setEvidenceNote(null);
    try {
      const r = await uploadStudioEvidence(routeId, file);
      setFigures((prev) => [...prev, ...r.figures]);
      // The dropped count is stated, never hidden. A client who sent a file
      // is owed the news that we threw part of it away, and why.
      setEvidenceNote(
        `Read ${r.added} figure${r.added === 1 ? '' : 's'} from ${file.name}.` +
          (r.rejected > 0
            ? ` ${r.rejected} more we could not match to a cell, so we left them out.`
            : '') +
          (r.rediagnosing ? ' Diagnosing again with them now…' : ''),
      );
      if (r.rediagnosing) {
        setPhase('diagnosing');
        setAct('building');
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setEvidenceError(detail || 'We could not read that file just now. Try again in a moment.');
    } finally {
      setEvidenceBusy(false);
    }
  }, [routeId]);

  const deleteFigure = useCallback(async (id: string) => {
    if (routeId == null) return;
    setEvidenceBusy(true);
    try {
      const r = await deleteStudioEvidence(routeId, id);
      setFigures(r.figures);
      setEvidenceNote(null);
    } catch {
      setEvidenceError('We could not remove that just now.');
    } finally {
      setEvidenceBusy(false);
    }
  }, [routeId]);

  const acceptAdvice = useCallback(async () => {
    if (routeId == null) return;
    setGateBusy(true);
    setGateError(null);
    try {
      await acceptStudioAdvice(routeId);
      // Re-read rather than patching the local copy: the server owns whether
      // this engagement is now terminal, and a refresh must show the same.
      await loadDecision(routeId);
    } catch {
      setGateError('We could not save that just now. Try again in a moment.');
    } finally {
      setGateBusy(false);
    }
  }, [routeId, loadDecision]);

  const reviseDecision = useCallback(async (note: string) => {
    if (routeId == null) return;
    setGateBusy(true);
    setGateError(null);
    try {
      await reviseStudioDecision(routeId, note);
      setDecision(null);
      setStartedAt(Date.now());
      setPhase('diagnosing');
      setAct('building');
    } catch {
      setGateError('We could not send that back just now. Try again in a moment.');
    } finally {
      setGateBusy(false);
    }
  }, [routeId]);

  // Decide what a run's state means — used both on first load of a result URL
  // and on every poll, so there is exactly one set of rules.
  const applyProgress = useCallback(
    (id: StudioRef, p: StudioProgress) => {
      setProgress(p);
      // The clock is the server's, but it is SET rather than re-based on
      // every poll. Re-basing each time read `Date.now() - elapsed_s*1000`
      // while the displayed `now` only ticks once a second, so the fresh
      // origin was routinely newer than the cached now — a negative
      // elapsed, floored to 0:00 by Math.max, every 2.5s. The clock sat at
      // zero for the whole run.
      //
      // Adopt the server's number when there is no clock yet, or when the
      // local one has genuinely drifted from it. That keeps the property
      // this was written for — a correct time on a run this tab did not
      // start — without resetting a clock that is already right.
      setStartedAt((prev) => {
        if (p.elapsed_s == null) return prev ?? Date.now();
        const fromServer = Date.now() - p.elapsed_s * 1000;
        if (prev == null || Math.abs(prev - fromServer) > 2000) return fromServer;
        return prev;
      });
      if (p.is_failed || p.stage === 'failed') {
        sessionStorage.removeItem(RESUME_KEY);
        setFailureDetail(p.detail ?? null);
        setAct('failed');
        return;
      }
      // The gate is checked BEFORE is_generating, because at the gate nothing
      // is generating: read in the other order this falls through to
      // showResult and offers them an engagement with no deliverables in it.
      // 'advised' is terminal and is NOT a finished build: we told them a
      // build would not fix the cause and they took the answer. It shares
      // this branch because the brief is what they come back to read.
      if (p.status === 'awaiting_approval' || p.status === 'advised') {
        sessionStorage.setItem(RESUME_KEY, String(id));
        void loadDecision(id);
        return;
      }
      if (p.is_generating) {
        sessionStorage.setItem(RESUME_KEY, String(id));
        // The server says which half is running. Read here rather than only
        // set by clicks, so a page reloaded mid-run shows the right one.
        setPhase(p.status === 'building' ? 'building' : 'diagnosing');
        setAct('building');
        return;
      }
      // Not generating and not failed: either finished, or a run that was
      // abandoned before it ever started. showResult tells them apart by
      // whether there is anything to show.
      sessionStorage.removeItem(RESUME_KEY);
      void showResult(id);
    },
    [showResult, loadDecision],
  );

  // A result URL is self-sufficient: it loads its own run, whatever state it
  // is in. Bare /studio only redirects to a run this browser already started.
  useEffect(() => {
    if (routeId == null) {
      // Dev-only design hook: /studio?preview=building renders the theater
      // without a live run, so the act can be looked at without spending a
      // generation. Compiled out of production builds.
      if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === 'building') {
        setStartedAt(Date.now() - 74_000);
        setProgress({
          business_name: 'Beacon Physiotherapy', stage: 'images',
          label: 'Rendering your product screenshots...', pct: 70,
          detail: 'screen 2 of 3', is_generating: true, is_failed: false,
          updated_at: null, elapsed_s: 74,
        });
        setPhase('building');
        setAct('building');
        return;
      }
      const stored = sessionStorage.getItem(RESUME_KEY);
      if (stored && /^[A-Za-z0-9_-]{1,40}$/.test(stored)) navigate(studioResultPath(stored), { replace: true });
      else setAct('intake');
      return;
    }

    let cancelled = false;
    setAct('loading');
    getStudioProgress(routeId)
      .then((p) => {
        if (!cancelled) applyProgress(routeId, p);
      })
      .catch((err) => {
        if (cancelled) return;
        if (isNotFound(err)) {
          // A stale bookmark should not keep redirecting us back to itself.
          sessionStorage.removeItem(RESUME_KEY);
          setAct('missing');
        } else if (isUnauthorized(err) || isForbidden(err)) {
          setPrivateReason(isUnauthorized(err) ? 'signin' : 'foreign');
          setAct('private');
        } else {
          setFailureDetail('The studio is not reachable right now. Your run is safe — this page will show it as soon as the connection is back.');
          setAct('failed');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeId, navigate, applyProgress]);


  // While the engagement is with the consultant, quietly check for its
  // release — the waiting client's page flips to the reveal on its own.
  useEffect(() => {
    if (act !== 'pending' || routeId == null) return;
    const t = setInterval(() => void showResult(routeId), 20000);
    return () => clearInterval(t);
  }, [act, routeId, showResult]);

  // The plan is written in the background after they take the answer. Poll
  // for it until it is written — or until it fails, which the page offers to
  // retry.
  const planStatus = decision?.action_plan?.status;
  useEffect(() => {
    if (act !== 'decision' || routeId == null || decision?.status !== 'advised') return;
    if (planStatus && planStatus !== 'writing') return;
    const t = setInterval(() => {
      getStudioDecision(routeId)
        .then(setDecision)
        .catch(() => undefined);
    }, 3000);
    return () => clearInterval(t);
  }, [act, routeId, decision?.status, planStatus]);

  // A plan asked for on a finished package: poll until it is written.
  const revealPlanStatus = revealPlan?.status;
  useEffect(() => {
    if (act !== 'reveal' || routeId == null || revealPlanStatus !== 'writing') return;
    const t = setInterval(() => {
      getStudioPlan(routeId)
        .then((r) => {
          if (r.plan && r.plan.status !== 'writing') setRevealPlan(r.plan);
        })
        .catch(() => undefined);
    }, 3000);
    return () => clearInterval(t);
  }, [act, routeId, revealPlanStatus]);

  // The tracker's entries, whenever a package is on screen.
  useEffect(() => {
    if (routeId == null) return;
    if (act !== 'reveal' && !(act === 'decision' && decision?.status === 'advised')) return;
    getStudioPlan(routeId)
      .then((r) => setPilotLog(r.log ?? []))
      .catch(() => undefined);
  }, [act, routeId, decision?.status]);

  // A build resumed from its URL has no decision in memory, and the building
  // screen pins the answer it is built around. Read it once.
  useEffect(() => {
    if (act !== 'building' || phase !== 'building' || decision || routeId == null) return;
    getStudioDecision(routeId)
      .then(setDecision)
      .catch(() => undefined);
  }, [act, phase, decision, routeId]);

  // Poll progress while building.
  useEffect(() => {
    if (act !== 'building' || routeId == null) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const p = await getStudioProgress(routeId);
        if (!cancelled) applyProgress(routeId, p);
      } catch {
        // transient poll failure: keep polling, the run continues server-side
      }
    };
    const t = setInterval(tick, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [act, routeId, applyProgress]);

  // Each step validates and returns on only its own field(s) — a stale
  // error left on a step the visitor has already backed away from must
  // never block Continue on the step they're actually standing on.
  /** Which fields each step owns, and what makes each one valid.
   *
   *  A step validates and reports on ONLY its own fields — a stale error left
   *  on a step the visitor has backed away from must never block Continue on
   *  the step they are actually standing on. Each step can now fail on more
   *  than one field at once, which the old one-error-at-a-time version could
   *  not do: the first screen carries both the name and the description, and
   *  surfacing one error, then the next on the following click, is a worse
   *  experience than showing both.
   */
  /** What we treat as the description of the business: what the conversation
   *  collected, or failing that what they wrote on the first screen. Used by
   *  both the validation and the launch, so the two cannot disagree about
   *  whether an engagement has one. */
  const effectiveDescription = () =>
    form.business_description.trim() || form.main_problem.trim();

  const STEP_RULES: { field: keyof FieldErrors; invalid: () => boolean; message: string }[][] = [
    [
      {
        field: 'main_problem',
        // The only thing we require before the conversation starts. It used
        // to be optional, buried on step two of six; it is now the entire
        // front door, because the pipeline treats it as the owner's own
        // hypothesis and tests it against the others. Blank, there is
        // nothing to test and nothing to disagree with — and disagreeing is
        // the product.
        invalid: () => form.main_problem.trim().length < 15,
        message: "Tell us what you're trying to work out — it's the thing we'll test.",
      },
    ],
    [
      // The conversation fills these, so they are checked when it ends rather
      // than typed on a form. `POST /api/requests` refuses the engagement
      // without them, and the interview will not call itself finished while
      // either is blank — this is the last line of that defence.
      {
        field: 'business_name',
        invalid: () => form.business_name.trim().length < 2,
        message: "We still don't have the business's name — the question above asks for it.",
      },
      {
        field: 'business_description',
        // The complaint stands in when the conversation never asked for a
        // description. Someone who wrote a paragraph about their studio on
        // screen one has already described it — making them type it again,
        // or blocking them because a model skipped the question, is worse
        // than using what they wrote.
        invalid: () => effectiveDescription().length < 30,
        message: 'We still need a couple of sentences on what you do and how big you are.',
      },
    ],
  ];

  const validateStep = (i: number): boolean => {
    const rules = STEP_RULES[i] ?? [];
    const failed = rules.filter((r) => r.invalid());
    setErrors((prev) => {
      const next = { ...prev };
      rules.forEach((r) => delete next[r.field]);
      failed.forEach((r) => {
        next[r.field] = r.message;
      });
      return next;
    });
    return failed.length === 0;
  };

  /** Intake fields the conversation is allowed to fill, mirroring the
   *  server's FILLABLE. A `field` the server does not recognise never
   *  arrives, and one this list does not recognise is ignored — nothing the
   *  model returns may write an arbitrary key into the form. */
  const CONVERSATION_FIELDS = [
    'business_name', 'business_description', 'target_customers',
    'industry', 'desired_outcome', 'revenue_today',
  ] as const;

  /** An answer goes to the form when the question said which field it fills,
   *  and to the numbers otherwise. Both, when it fills a field: the interview
   *  reads back what it already asked from the same list, so an answer that
   *  vanished from it would be asked for again. */
  const answerQuestion = useCallback((id: string, value: string) => {
    setNumbersAnswers((prev) => ({ ...prev, [id]: value }));
    const question = [...rounds.flatMap((r) => r.questions), NAME_QUESTION].find((q) => q.id === id);
    const field = question?.field;
    if (field === 'business_name') {
      // "What's it called, and how big is it?" is one natural question, and
      // it gets one sentence back: "Halo Reformer Studio. One room, 12
      // reformers…". The name is what comes before the first stop; the rest
      // describes the business, and is kept as that rather than lost.
      const parts = value.split(/(?<=\S)[.;\n]\s+|\s+[—–-]\s+/);
      // "Dr. Aoun's Clinic" must not become "Dr": a first piece that short
      // is an abbreviation, not a name.
      const split = parts.length > 1 && parts[0].trim().length >= 4;
      const name = split ? parts[0] : value;
      const more = split ? parts.slice(1).join('. ').trim() : '';
      setForm((prev) => ({
        ...prev,
        business_name: name.trim().slice(0, 120),
        business_description: more && !prev.business_description.trim() ? more : prev.business_description,
      }));
    } else if (field && (CONVERSATION_FIELDS as readonly string[]).includes(field)) {
      setForm((prev) => ({ ...prev, [field]: value }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rounds]);

  /** Every question put to them, in order — plus the business's name, asked
   *  last and only if the interview never got it. The engagement cannot
   *  start without a name, and the interview can end without asking. */
  const allQuestions = useMemo(() => {
    const qs = rounds.flatMap((r) => r.questions);
    const pending = qs.some((q) => !committed.includes(q.id));
    if (interviewDone && !pending && !discoveryLoading && form.business_name.trim().length < 2) {
      return [...qs, NAME_QUESTION];
    }
    return qs;
  }, [rounds, committed, interviewDone, discoveryLoading, form.business_name]);

  /** Everything answered across every round, in the shape the run is
   *  launched with. One builder, so the interviewer is shown exactly what the
   *  pipeline will be given — an interviewer reading a different set from the
   *  diagnosis would ask for figures the diagnosis already has. */
  const opsNumbersPairs = useCallback(
    () =>
      rounds
        .flatMap((r) => r.questions)
        // Answers that fill an intake field live in that field, not here. A
        // paragraph describing the business sitting in the numbers would be
        // mined for figures by `client_fact_claims` and cited as one.
        .filter((q) => !q.field && (numbersAnswers[q.id] ?? '').trim())
        .map((q) => ({ id: q.id, question: q.label, answer: numbersAnswers[q.id].trim() })),
    [rounds, numbersAnswers],
  );

  /** What the conversation knows about them so far. The server decides what
   *  is still missing from this, so there is one answer to that question
   *  rather than one per caller. */
  const knownFields = useCallback(
    () =>
      Object.fromEntries(
        CONVERSATION_FIELDS.map((f) => [f, String(form[f] ?? '').trim()]).filter(([, v]) => v),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [form],
  );

  /** One round of the interview. Round 1 fires the moment they have said what
   *  is wrong; later rounds once they have answered something, so a follow-up
   *  always follows an actual answer. */
  const askRound = useCallback(async (n: number) => {
    // The only precondition now. The business has no name yet on round 1 —
    // asking for it is the conversation's job, not the form's.
    if (form.main_problem.trim().length < 15) return;
    setDiscoveryLoading(true);
    try {
      const r = await fetchInterviewRound({
        business_name: form.business_name.trim() || undefined,
        business_description: form.business_description.trim() || undefined,
        industry: form.industry.trim() || undefined,
        operating_stage: form.operating_stage,
        engagement_type: form.engagement_type,
        main_problem: form.main_problem.trim(),
        desired_outcome: form.desired_outcome.trim() || undefined,
        // Exactly what the pipeline will see, so it cannot re-ask for
        // something it already has.
        ops_numbers: JSON.stringify(opsNumbersPairs()),
        asked: JSON.stringify(rounds.flatMap((r) => r.questions.map((q) => q.label))),
        known: JSON.stringify(knownFields()),
        round: n,
      });
      if (r.questions.length > 0) {
        setRounds((prev) => [...prev, { questions: r.questions, because: r.because }]);
      }
      // Read off their own words instead of asked as pills. Only ever fills a
      // gap: a value the client has already changed is theirs, not ours.
      setForm((prev) => ({
        ...prev,
        engagement_type: (r.inferred.engagement_type as EngagementType) ?? prev.engagement_type,
        operating_stage: (r.inferred.operating_stage as OperatingStage) ?? prev.operating_stage,
      }));
      setInterviewDone(r.done);
      setInterviewClosing(r.because);
    } catch {
      // The interview must never trap the client on a step. A failed first
      // round serves the static set; a failed later round simply ends it.
      setRounds((prev) =>
        prev.length
          ? prev
          : [{ questions: LOCAL_DISCOVERY_FALLBACK[form.operating_stage], because: '' }],
      );
      setInterviewDone(true);
    } finally {
      setDiscoveryLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, opsNumbersPairs, knownFields, rounds]);

  const prefetchDiscovery = useCallback(() => {
    const problem = form.main_problem.trim();
    if (problem.length < 15) return;
    // Keyed on the complaint alone now. It is the only thing they have told
    // us when the first round fires, and everything else is downstream of it:
    // a different complaint is a different conversation, and following up on
    // answers to questions nobody would have asked about it is worse than
    // starting again.
    if (discoveryKey.current === problem) return;
    discoveryKey.current = problem;
    setRounds([]);
    setCommitted([]);
    setCaseFile(null);
    setInterviewDone(false);
    roundAsked.current = 1;
    void askRound(1);
  }, [form.main_problem, askRound]);

  /** The inputs the case file is read from: only what they have committed,
   *  so it refreshes when they answer and not on every keystroke. */
  const caseInputs = useCallback(() => {
    const ops = opsNumbersPairs().filter((p) => committed.includes(p.id));
    return {
      main_problem: form.main_problem.trim(),
      ops_numbers: ops,
      known: knownFields() as Record<string, string>,
      operating_stage: form.operating_stage,
      playback: true,
    };
  }, [opsNumbersPairs, committed, form.main_problem, form.operating_stage, knownFields]);

  const caseKey = useMemo(
    () => JSON.stringify({
      p: form.main_problem.trim(),
      a: committed.map((id) => [id, (numbersAnswers[id] ?? '').trim()]),
    }),
    [form.main_problem, committed, numbersAnswers],
  );

  // After every answer: re-read the case file. A newer call supersedes an
  // older one — the panel never shows an answer being taken back.
  useEffect(() => {
    if (act !== 'intake' || step !== 1 || committed.length === 0) return;
    if (caseCall.current?.key === caseKey) return;
    const promise = fetchCaseFile(caseInputs());
    caseCall.current = { key: caseKey, promise };
    setCaseLoading(true);
    void promise.then((file) => {
      if (caseCall.current?.key !== caseKey) return;
      setCaseFile((prev) => (file.figures.length || file.capacity || !prev ? file : prev));
      setCaseLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [act, step, caseKey]);

  // When the round's last question is answered, ask the next round — unless
  // they skipped every question in it, in which case follow-ups would be
  // follow-ups to nothing.
  useEffect(() => {
    if (act !== 'intake' || step !== 1) return;
    if (discoveryLoading || interviewDone || rounds.length === 0) return;
    const qs = rounds.flatMap((r) => r.questions);
    if (!qs.every((q) => committed.includes(q.id))) return;
    const next = rounds.length + 1;
    if (roundAsked.current >= next) return;
    const last = rounds[rounds.length - 1];
    if (!last.questions.some((q) => (numbersAnswers[q.id] ?? '').trim())) {
      setInterviewDone(true);
      return;
    }
    roundAsked.current = next;
    void askRound(next);
  }, [act, step, committed, rounds, discoveryLoading, interviewDone, numbersAnswers, askRound]);

  const commitQuestion = (id: string) => {
    setFinishError(null);
    setCommitted((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  const reopenQuestion = (id: string) => {
    setCommitted((prev) => prev.filter((x) => x !== id));
  };

  /** Their files, checked here only for what the server would refuse anyway:
   *  the type and the size. Three at most. */
  const addFiles = (incoming: File[]) => {
    const ok = incoming.filter((f) => /\.(csv|tsv|txt|xlsx|xlsm|pdf)$/i.test(f.name) && f.size <= 8 * 1024 * 1024);
    if (ok.length < incoming.length) {
      setFinishError('We can read spreadsheets, CSV files and PDFs up to 8 MB. Anything else was left out.');
    }
    setFiles((prev) => [...prev, ...ok].slice(0, 3));
  };

  /** From the conversation to the playback: every rule once more, then the
   *  case file played back — reusing the one already read if nothing has
   *  changed since. */
  const finishInterview = async () => {
    const allValid = STEP_RULES.map((_, i) => validateStep(i)).every(Boolean);
    if (!allValid) {
      setFinishError(
        form.business_name.trim().length < 2
          ? "We still need the business's name. Tap “change” on that question above, or answer the last one."
          : 'We still need a couple of sentences on what you do.',
      );
      return;
    }
    setFinishError(null);
    setSubmitError(null);
    setCorrection('');
    setAct('briefing');
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    const pending = caseCall.current;
    if (pending && pending.key === caseKey) {
      setPlaybackLoading(true);
      const file = await pending.promise;
      setPlaybackFile(file);
      setPlaybackLoading(false);
      if (file.summary || file.figures.length) return;
    }
    setPlaybackLoading(true);
    const file = await fetchCaseFile(caseInputs());
    setPlaybackFile(file);
    setPlaybackLoading(false);
  };

  /** A figure corrected on the playback rewrites the sentence it was read
   *  from, so the diagnosis reads the corrected answer, not the old one with
   *  a note beside it. */
  const editFigure = (f: CaseFigure, next: string) => {
    const swap = (text: string) => {
      if (text.includes(f.token)) return text.replace(f.token, next);
      const i = text.toLowerCase().indexOf(f.token.toLowerCase());
      return i < 0 ? `${text} (correction: ${next})` : text.slice(0, i) + next + text.slice(i + f.token.length);
    };
    if (f.source === 'main_problem') {
      setForm((p) => ({ ...p, main_problem: swap(p.main_problem) }));
    } else if (f.source.startsWith('field:')) {
      const key = f.source.slice(6) as keyof typeof form;
      setForm((p) => ({ ...p, [key]: swap(String(p[key] ?? '')) }));
      const q = rounds.flatMap((r) => r.questions).find((x) => x.field === key);
      if (q) setNumbersAnswers((p) => ({ ...p, [q.id]: swap(p[q.id] ?? '') }));
    } else {
      setNumbersAnswers((p) => ({ ...p, [f.source]: swap(p[f.source] ?? '') }));
    }
    setPlaybackFile((pf) =>
      pf && {
        ...pf,
        figures: pf.figures.map((x) =>
          x === f ? { ...x, token: next, value: reshapeValue(x.value, x.token, next) } : x,
        ),
      },
    );
  };

  const goNext = () => {
    if (!validateStep(step)) return;
    // Idempotent (keyed on the brief) — re-fires only when the name,
    // description or stage actually changed since the last fetch. Fired from
    // step 0 now rather than step 1, because the description moved onto the
    // first screen: by the time they reach the conversation the questions are
    // already written, and the step reads as a consultant who had read the
    // brief before walking in.
    prefetchDiscovery();
    setStep((s) => Math.min(s + 1, INTAKE_STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const buildIntake = () => ({
    business_name: form.business_name.trim(),
    business_description: effectiveDescription(),
    // No longer asked on a form. They signed in to get here, so we already
    // know where to reach them — asking again on screen one was a tax paid
    // before we had shown them anything worth paying it for.
    email: form.email.trim() || user?.email || '',
    industry: form.industry.trim() || undefined,
    main_problem: form.main_problem.trim() || undefined,
    target_customers: form.target_customers.trim() || undefined,
    desired_outcome: form.desired_outcome.trim() || undefined,
    reference_url: form.reference_url.trim() || undefined,
    what_you_like: form.what_you_like.trim() || undefined,
    needs_ai: form.needs_ai || undefined,
    budget_range: form.budget_range || undefined,
    timeline: form.timeline || undefined,
    whatsapp: form.whatsapp.trim() || undefined,
    site_url: form.site_url.trim() || undefined,
    revenue_today: form.revenue_today.trim() || undefined,
    operating_stage: form.operating_stage,
    engagement_type: form.engagement_type,
    ops_numbers: opsNumbersPairs(),
    files,
  });

  const launchEngagement = async (addendum: string | null) => {
    if (submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const intake = buildIntake();
      const created = await createStudioRequest({
        ...intake,
        // Corrections from the briefing chat become part of the brief the
        // whole pipeline reads — the client's facts, verbatim.
        business_description: addendum
          ? `${intake.business_description}\n\nCorrections and additions from the briefing chat:\n${addendum}`
          : intake.business_description,
      });
      // The private slug is the address we hand the client; the numeric id
      // only backstops legacy rows created before slugs existed.
      const ref = created.public_id ?? created.id;
      sessionStorage.setItem(RESUME_KEY, String(ref));
      // The run gets its address the moment it exists, not when it finishes —
      // so a refresh, a closed laptop or a shared link all land somewhere.
      navigate(studioResultPath(ref));
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    } catch (err) {
      setSubmitError(
        isAtCapacity(err)
          ? 'The studio is rendering at full capacity right now — give it a few minutes and try again.'
          : 'Something went wrong reaching the studio. Try again in a moment.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const doApprove = async () => {
    if (!reviewToken || routeId == null || reviewBusy) return;
    setReviewBusy(true);
    try {
      await approveReview(routeId, reviewToken);
      await showResult(routeId);
    } finally {
      setReviewBusy(false);
    }
  };

  const openEditor = () => {
    setEditBp(preview?.mvp_blueprint ?? '');
    setEditTech(preview?.technical_plan ?? '');
    setEditOpen(true);
  };

  const doSaveDocs = async () => {
    if (!reviewToken || routeId == null || reviewBusy) return;
    setReviewBusy(true);
    try {
      await saveReviewDocs(routeId, reviewToken, { mvp_blueprint: editBp, technical_plan: editTech });
      setEditOpen(false);
      await showResult(routeId);
    } finally {
      setReviewBusy(false);
    }
  };

  const startOver = () => {
    sessionStorage.removeItem(RESUME_KEY);
    setPreview(null);
    setProgress(null);
    setStartedAt(null);
    setFailureDetail(null);
    setErrors({});
    setStep(0);
    setAct('intake');
    navigate('/demo');
  };

  const copyLink = async () => {
    if (!resultUrl) return;
    try {
      await navigator.clipboard.writeText(resultUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2400);
    } catch {
      // Clipboard blocked (insecure origin, denied permission): the link is
      // on screen and selectable, so there is nothing to apologise for.
    }
  };

  const openLightbox = (src: string, alt: string) => {
    setLightbox({ src, alt });
    requestAnimationFrame(() => dialogRef.current?.showModal());
  };

  const closeLightbox = () => {
    dialogRef.current?.close();
    setLightbox(null);
  };

  // Switching tabs on a long page must land the reader at the top of the
  // new tab's content — the tab bar itself, not the page hero above it.
  // The ref skips the mount run so opening a result URL doesn't jump.
  const firstTabRender = useRef(true);
  const resultTabsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (firstTabRender.current) {
      firstTabRender.current = false;
      return;
    }
    if (act !== 'reveal') return;
    const bar = resultTabsRef.current;
    // 80px clears the fixed navbar so the bar isn't hidden under it.
    const top = bar ? bar.getBoundingClientRect().top + window.scrollY - 80 : 0;
    window.scrollTo({ top: Math.max(top, 0), behavior: reduceMotion ? 'auto' : 'smooth' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const pct = progress?.pct ?? 4;

  const allScreens: StudioScreen[] = preview?.generated_pages.attraction_images ?? [];
  const screens = allScreens.filter((s) => !brokenSrc[s.image_url]);
  const visibleTabs = preview ? RESULT_TABS.filter((t) => t.available(preview)) : [];
  const buildingName =
    progress?.business_name || decision?.business_name || preview?.business_name || form.business_name.trim() || 'Your business';
  const firstName = (user?.name ?? '').trim().split(/\s+/)[0] || null;
  const fade = reduceMotion
    ? {}
    : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -12 }, transition: { duration: 0.4 } };

  // Where they are in the five steps, and what the top bar calls it.
  const [chromeStep, chromeWhere] = ((): [number, string] => {
    switch (act) {
      case 'intake':
        return step === 0 ? [0, 'Your situation'] : [1, 'Questions'];
      case 'briefing':
        return [1, 'Before we start'];
      case 'building':
        return phase === 'building' ? [4, 'Building your package'] : [2, 'Diagnosis'];
      case 'decision':
        return decision?.status === 'advised' ? [5, 'Yours to keep'] : [3, 'Your answer'];
      case 'reveal':
        return [5, 'Yours to keep'];
      case 'pending':
        return [5, 'In final review'];
      default:
        return [0, ''];
    }
  })();

  const packageScreens: PackageScreen[] = screens
    .map((sc) => ({
      label: sc.role_label,
      src: consultantAssetUrl(sc.hero_url ?? sc.image_url) ?? '',
      full: consultantAssetUrl(sc.image_url) ?? '',
    }))
    .filter((sc) => sc.src && sc.full);

  const download = (kind: StudioExportKind) =>
    routeId == null ? Promise.resolve() : downloadStudioExport(routeId, kind, reviewToken);
  const share = async () => {
    const r = await shareStudio(routeId as StudioRef);
    return `${window.location.origin}${r.path}`;
  };
  const unshare = async () => {
    await unshareStudio(routeId as StudioRef);
  };
  const saveWeek = async (week: number, values: Record<string, number>, note: string) => {
    const r = await logPilotWeek(routeId as StudioRef, week, values, note);
    setPilotLog(r.log);
  };
  const retryPlan = async () => {
    if (routeId == null) return;
    try {
      await retryStudioPlan(routeId);
    } finally {
      if (act === 'decision') await loadDecision(routeId);
      else setRevealPlan({ status: 'writing' });
    }
  };
  const finding = decision?.answer
    ? [decision.answer.headline, decision.answer.turn].filter(Boolean).join(' ')
    : decision?.decision.central_problem ?? null;

  return (
    <div className="cx">
      <Chrome
        step={chromeStep}
        where={chromeWhere}
        right={isAuthenticated ? <RouterLink to="/engagements">Your engagements</RouterLink> : null}
      />

      <main className="cx-wrap">
          <AnimatePresence mode="wait">
            {act === 'loading' && (
              <motion.section key="loading" {...fade}>
                <p className="cx-lead pt-[12vh]">
                  Opening your consultation<span className="cx-typing"><i /><i /><i /></span>
                </p>
              </motion.section>
            )}

            {act === 'intake' && step === 0 && (
              <motion.div key="door" {...fade}>
                <FrontDoor
                  firstName={firstName}
                  value={form.main_problem}
                  onChange={(v) => setForm((f) => ({ ...f, main_problem: v }))}
                  siteUrl={form.site_url}
                  onSiteUrl={(v) => setForm((f) => ({ ...f, site_url: v }))}
                  error={errors.main_problem}
                  onStart={goNext}
                  signedIn={isAuthenticated}
                  checkingAuth={authLoading}
                />
              </motion.div>
            )}

            {act === 'intake' && step === 1 && (
              <motion.div key="interview" {...fade}>
                <button type="button" className="cx-link cx-small mt-2" onClick={goBack}>
                  Back to what you wrote
                </button>
                <Interview
                  questions={allQuestions}
                  answers={numbersAnswers}
                  committed={committed}
                  onAnswer={answerQuestion}
                  onCommit={commitQuestion}
                  onReopen={reopenQuestion}
                  loading={discoveryLoading}
                  done={interviewDone}
                  closing={interviewClosing}
                  estimatedTotal={allQuestions.length + (interviewDone ? 0 : 2)}
                  caseFile={caseFile}
                  caseLoading={caseLoading}
                  files={files}
                  onAddFiles={addFiles}
                  onRemoveFile={(i) => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  onFinish={() => void finishInterview()}
                  finishError={finishError}
                />
              </motion.div>
            )}

            {act === 'briefing' && (
              <motion.div key="playback" {...fade}>
                <Playback
                  file={playbackFile}
                  loading={playbackLoading}
                  businessName={form.business_name.trim()}
                  fallbackAnswers={opsNumbersPairs().map((p) => ({ question: p.question, answer: p.answer }))}
                  mainProblem={form.main_problem}
                  onEditFigure={editFigure}
                  correction={correction}
                  onCorrection={setCorrection}
                  onStart={() => void launchEngagement(correction.trim() ? `- ${correction.trim()}` : null)}
                  onBack={() => setAct('intake')}
                  submitting={submitting}
                  error={submitError}
                />
              </motion.div>
            )}

            {act === 'private' && (
              <motion.section key="private" {...fade} transition={{ duration: 0.45 }}>
                <div className="max-w-xl mx-auto text-center py-16">
                  <p className="studio-kicker mb-3">Private engagement</p>
                  <h1 className="studio-display text-3xl font-bold text-navy mb-4">
                    {privateReason === 'signin'
                      ? 'Sign in to open this engagement'
                      : 'This engagement belongs to another account'}
                  </h1>
                  <p className="studio-plan-rostertext mb-8">
                    {privateReason === 'signin'
                      ? 'Engagements are private to the account that created them. Sign in with the account you used.'
                      : "Every engagement is visible only to its owner. If this is yours, sign in with the right account - otherwise, start your own."}
                  </p>
                  <div className="flex flex-wrap gap-3 justify-center">
                    {privateReason === 'signin' && (
                      <RouterLink to="/login" state={{ from: window.location.pathname }} className="studio-cta">
                        Sign in
                      </RouterLink>
                    )}
                    <RouterLink to="/demo" className={privateReason === 'signin' ? 'studio-ghost-btn' : 'studio-cta'}>
                      Start your own engagement
                    </RouterLink>
                  </div>
                </div>
              </motion.section>
            )}

            {act === 'pending' && teaser && (
              <motion.section key="pending" {...fade} transition={{ duration: 0.5 }}>
                <div className="max-w-4xl mx-auto text-center">
                  <div className="studio-pend-badge" aria-hidden="true">
                    <span className="studio-pend-ring" />
                    <Icon path={INTAKE_ICONS.shield} className="w-5 h-5" />
                  </div>
                  <p className="studio-kicker mb-3 mt-6">Engagement complete — in final review</p>
                  <h1 className="studio-display text-3xl sm:text-5xl font-bold text-navy">
                    {teaser.concept_name || teaser.business_name} is ready.
                  </h1>
                  <p className="studio-plan-rostertext mt-4 max-w-xl mx-auto">
                    Your consultant is personally reviewing every page before release — the same
                    signature every engagement gets. You'll receive it shortly.
                  </p>

                  {teaser.numbers_echo.length > 0 && (
                    <div className="studio-pend-numbers">
                      <span>Built around your own numbers</span>
                      {teaser.numbers_echo.map((n, i) => (
                        <em key={i}>{n}</em>
                      ))}
                    </div>
                  )}

                  <div className="studio-pend-stats">
                    {[
                      [teaser.stats.modules, 'modules'],
                      [teaser.stats.ai_agents, 'AI agents'],
                      [teaser.stats.journey_stages, 'journey stages'],
                      [teaser.stats.procedures, 'procedures'],
                      [teaser.stats.checklists, 'checklists'],
                      [teaser.stats.quick_wins, 'quick wins'],
                    ]
                      .filter(([n]) => (n as number) > 0)
                      .map(([n, label], i) => (
                        <motion.div
                          className="studio-pend-stat"
                          key={label as string}
                          initial={reduceMotion ? undefined : { opacity: 0, y: 14 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.15 + i * 0.09, duration: 0.4 }}
                        >
                          <strong>{n}</strong>
                          <span>{label}</span>
                        </motion.div>
                      ))}
                  </div>

                  {teaser.journey_stage_names.length > 0 && (
                    <div className="studio-pend-journey">
                      {teaser.journey_stage_names.map((name, i) => (
                        <motion.span
                          className="studio-pend-jstage"
                          key={name}
                          initial={reduceMotion ? undefined : { opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.4 + i * 0.12, duration: 0.35 }}
                        >
                          <i>{i + 1}</i>
                          {name}
                        </motion.span>
                      ))}
                    </div>
                  )}

                  {teaser.module_teasers.length > 0 && (
                    <div className="studio-pend-modules">
                      {teaser.module_teasers.map((m, i) => (
                        <motion.div
                          className="studio-pend-module"
                          key={m.name ?? i}
                          initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.5 + i * 0.1, duration: 0.4 }}
                        >
                          <p className="studio-pend-module-name">{m.name}</p>
                          {m.purpose && <p className="studio-pend-module-purpose">{m.purpose}</p>}
                        </motion.div>
                      ))}
                    </div>
                  )}

                  {teaser.qa_checks.length > 0 && (
                    <div className="studio-pend-checks">
                      <p className="studio-kicker mb-3">What the expert auditors verified</p>
                      {teaser.qa_checks.map((c, i) => (
                        <motion.p
                          className={`studio-pend-check${c.passed ? '' : ' studio-pend-check--fixing'}`}
                          key={c.label}
                          initial={reduceMotion ? undefined : { opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: 0.7 + i * 0.15 }}
                        >
                          <span aria-hidden="true">{c.passed ? '✓' : '…'}</span>
                          {c.label}
                          {!c.passed && <em> — being corrected by your consultant</em>}
                        </motion.p>
                      ))}
                    </div>
                  )}

                  <p className="studio-hint studio-hint--trust justify-center mt-10">
                    <Icon path={INTAKE_ICONS.shield} className="w-3.5 h-3.5" />
                    This page updates itself the moment your engagement is released.
                  </p>
                </div>
              </motion.section>
            )}

            {act === 'decision' && decision && (
              <motion.div key={`decision-${decision.status}`} {...fade}>
                {decision.status === 'advised' ? (
                  <>
                    <Package
                      mode="plan"
                      businessName={decision.business_name ?? buildingName}
                      answer={decision.answer ?? null}
                      fallbackFinding={decision.decision.central_problem ?? decision.decision.summary}
                      capacity={decision.capacity ?? null}
                      plan={decision.action_plan ?? null}
                      log={pilotLog}
                      unverified={decision.decision.unverified ?? []}
                      screens={[]}
                      docs={{ blueprint: false, technical: false, operations: false }}
                      onDownload={download}
                      onShare={share}
                      onUnshare={unshare}
                      canEdit
                      onSaveWeek={saveWeek}
                      onRetryPlan={() => void retryPlan()}
                      onBuild={() => void approveDecision()}
                    />
                    {gateError ? <p className="cx-error mt-6" role="alert">{gateError}</p> : null}
                  </>
                ) : (
                  <Answer
                    decision={decision}
                    firstName={firstName}
                    onBuild={(scope) => void approveDecision(scope)}
                    onAccept={() => void acceptAdvice()}
                    onRevise={(note) => void reviseDecision(note)}
                    onUpload={(f) => void uploadEvidence(f)}
                    busy={gateBusy}
                    error={gateError}
                    evidenceBusy={evidenceBusy}
                    evidenceNote={evidenceNote}
                    evidenceError={evidenceError}
                    figures={figures}
                    onDeleteFigure={(id) => void deleteFigure(id)}
                  />
                )}
              </motion.div>
            )}

            {act === 'building' && (
              <motion.div key={`run-${phase}`} {...fade}>
                {phase === 'diagnosing' ? (
                  <Thinking steps={thinking} stage={progress?.stage ?? null} elapsed={elapsed} businessName={buildingName} />
                ) : (
                  <Building
                    businessName={buildingName}
                    finding={finding}
                    pct={pct}
                    elapsed={elapsed}
                    label={progress?.label ?? null}
                    detail={progress?.detail ?? null}
                    notifyEmail={progress?.notify?.enabled ? progress.notify.email ?? null : null}
                    resultUrl={resultUrl}
                    copied={copied}
                    onCopy={copyLink}
                  />
                )}
              </motion.div>
            )}

            {act === 'reveal' && preview && (
              <motion.section key="reveal" {...fade} transition={{ duration: 0.5 }}>
                <Package
                  mode="full"
                  businessName={preview.business_name}
                  answer={preview.answer ?? null}
                  fallbackFinding={preview.preview_summary}
                  capacity={preview.capacity ?? null}
                  plan={revealPlan ?? preview.action_plan ?? null}
                  log={pilotLog}
                  unverified={preview.unverified ?? []}
                  screens={packageScreens}
                  docs={{
                    blueprint: Boolean(preview.mvp_blueprint),
                    technical: Boolean(preview.technical_plan),
                    operations: preview.procedures.length > 0 || Boolean(preview.organization) || Boolean(preview.checklists),
                  }}
                  onDownload={download}
                  onShare={share}
                  onUnshare={unshare}
                  canEdit={!reviewToken}
                  onSaveWeek={saveWeek}
                  onRetryPlan={() => void retryPlan()}
                  onOpenScreen={(sc) => openLightbox(sc.full, sc.label)}
                  readOnly={Boolean(reviewToken)}
                />

                <div className="mx-auto mt-24 max-w-6xl">
                <div className="mb-10 border-t border-[var(--cx-line)] pt-12">
                  <h2 className="cx-h2">Everything, in detail</h2>
                  <p className="cx-lead mt-3">Read the documents here, or download them above.</p>
                  {preview.what_this_is ? <p className="cx-muted mt-4 max-w-[70ch]">{preview.what_this_is}</p> : null}
                </div>

                {/* One tab per thing this run actually produced — a run that
                    skipped the technical plan or named no AI employees never
                    shows an empty tab, since RESULT_TABS filters on that. */}
                {visibleTabs.length > 1 && (
                  <div className="studio-tabs" role="tablist" aria-label="Result sections" ref={resultTabsRef}>
                    {visibleTabs.map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        role="tab"
                        aria-selected={activeTab === tab.id}
                        className={`studio-tab${activeTab === tab.id ? ' studio-tab--active' : ''}`}
                        onClick={(e) => {
                          // On phones the bar scrolls horizontally — keep the
                          // tapped tab fully in view instead of half-clipped.
                          e.currentTarget.scrollIntoView({ inline: 'center', block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
                          setActiveTab(tab.id);
                        }}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                )}

                {activeTab === 'screens' && (screens.length === 0 ? (
                  <div className="studio-panel p-8 text-center max-w-xl mx-auto">
                    <p className="text-slate-600 font-semibold">This run's screens aren't on file.</p>
                    <p className="mt-3 text-slate-600 text-sm">
                      The design work finished, but the image files can't be served right now.
                      Start a fresh run and it will render again.
                    </p>
                    <button type="button" className="studio-cta mt-8 max-w-xs mx-auto" onClick={startOver}>
                      Design my software
                    </button>
                  </div>
                ) : (
                  <div className="studio-walkthrough">
                    {screens.map((screen, i) => {
                      const src = consultantAssetUrl(screen.hero_url ?? screen.image_url);
                      const full = consultantAssetUrl(screen.image_url);
                      if (!src || !full) return null;
                      const story = screen.story;
                      return (
                        <motion.section
                          className="studio-screen"
                          key={`${screen.role_id}-${screen.variant}`}
                          initial={reduceMotion ? undefined : { opacity: 0, y: 34 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.6, delay: reduceMotion ? 0 : 0.12 * i }}
                        >
                          <header className="studio-screen-head">
                            <span className="studio-screen-no">
                              {String(i + 1).padStart(2, '0')}
                            </span>
                            <div>
                              <h2>{screen.role_label}</h2>
                              {story?.subheading && <p>{story.subheading}</p>}
                            </div>
                            <a
                              className="studio-screen-open"
                              href={full}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open full resolution
                            </a>
                          </header>

                          <button
                            type="button"
                            className="studio-shot"
                            onClick={() => openLightbox(full, screen.role_label)}
                            aria-label={`Enlarge ${screen.role_label}`}
                          >
                            <img
                              src={src}
                              alt={`${screen.role_label} screen`}
                              loading={i > 0 ? 'lazy' : 'eager'}
                              onError={() => setBrokenSrc((b) => ({ ...b, [screen.image_url]: true }))}
                            />
                          </button>

                          {/* Everything below is read from the spec this
                              screen was drawn from, so a client can check
                              each line against the picture above it. A screen
                              with no stored spec simply gets no notes. */}
                          {story?.description && (
                            <p className="studio-screen-desc">{story.description}</p>
                          )}

                          {story && (story.tracks.length > 0 || story.ai) && (
                            <div className="studio-notes">
                              {story.tracks.length > 0 && (
                                <div className="studio-note">
                                  <h3>What it tracks</h3>
                                  <p>{story.tracks.join(' · ')}</p>
                                </div>
                              )}

                              {story.ai && (
                                <div className="studio-note studio-note--ai">
                                  <h3>
                                    <span className="studio-ai-dot" aria-hidden="true" />
                                    Where the AI works on this screen
                                  </h3>
                                  {story.ai.title && <p className="studio-ai-title">{story.ai.title}</p>}
                                  <p className="studio-ai-headline">{story.ai.headline}</p>
                                  {story.ai.rationale && (
                                    <p className="studio-ai-why">{story.ai.rationale}</p>
                                  )}
                                  {story.ai.confidence && (
                                    <p className="studio-ai-conf">{story.ai.confidence}</p>
                                  )}
                                  {story.ai.chips.length > 0 && (
                                    <div className="studio-ai-chips">
                                      {story.ai.chips.map((c) => (
                                        <span key={c}>{c}</span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </motion.section>
                      );
                    })}
                  </div>
                ))}

                {activeTab === 'team' && (
                  <div className="studio-tabpanel">
                    {preview.ai_features.length > 0 && (
                      <div className="studio-roster">
                        <p className="studio-kicker mb-6">Your new team</p>
                        {preview.ai_features.length > 1 && (
                          <span className="studio-roster-line" aria-hidden="true" />
                        )}
                        <div className="studio-roster-list">
                          {preview.ai_features.map((f, i) => (
                            <article className="studio-rostercard" key={f.id}>
                              <span className="studio-rostercard-avatar">{initials(f.name) || 'AI'}</span>
                              <div className="min-w-0">
                                <p className="studio-rostercard-eyebrow">
                                  Employee {String(i + 1).padStart(2, '0')}
                                </p>
                                <h3 className="studio-display">{f.name}</h3>
                                <p>{f.description}</p>
                                <span className="studio-rostercard-status">
                                  <span className="studio-ai-dot" aria-hidden="true" />
                                  Always on
                                </span>
                              </div>
                            </article>
                          ))}
                        </div>
                      </div>
                    )}

                    {preview.preview_features.length > 0 && (
                      <div className="mt-16">
                        <p className="studio-kicker mb-4">What it does for you</p>
                        <div className="studio-plan-checklist studio-plan-checklist--grid">
                          {preview.preview_features.map((f) => (
                            <div className="studio-plan-checkrow" key={f}>
                              <CheckIcon className="studio-plan-checkicon" />
                              <p>{f}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* modules is optional-chained: a result served by an older
                    API build has no such key at runtime, whatever the type
                    says. */}
                {activeTab === 'blueprint' && (preview.mvp_blueprint || (preview.modules?.length ?? 0) > 0) && (
                  <div className="studio-tabpanel">
                    {(preview.modules?.length ?? 0) > 0 ? (
                      <DecomposedBlueprint preview={preview} />
                    ) : (
                      <BlueprintCinematic preview={preview} />
                    )}
                  </div>
                )}

                {activeTab === 'technical' && preview.technical_plan && (
                  <div className="studio-tabpanel">
                    {/* The plan is deliberately complete enough to execute
                        without us — so the choice is stated, not implied. */}
                    <div className="studio-plan-columns mb-10">
                      <div className="studio-panel studio-plan-panel">
                        <p className="studio-kicker mb-2">Path one</p>
                        <p className="studio-plan-rostername mb-1">We execute this plan for you</p>
                        <p className="studio-plan-rostertext mb-4">
                          The same team that wrote it builds it — module by module, in the order
                          below, with you reviewing at every phase.
                        </p>
                        <button
                          type="button"
                          className="studio-ghost-btn"
                          onClick={() => setActiveTab('plans')}
                        >
                          See build packages
                        </button>
                      </div>
                      <div className="studio-panel studio-plan-panel">
                        <p className="studio-kicker mb-2">Path two</p>
                        <p className="studio-plan-rostername mb-1">Take the plan — it's yours</p>
                        <p className="studio-plan-rostertext mb-4">
                          Every module, data model, agent spec, build sequence and acceptance check
                          is written down below. A competent team can build from this document.
                        </p>
                        <div className="studio-doc-downloads">
                          {preview.deck_available && (
                            <DownloadButton refId={preview.id} kind="pptx" className="studio-ghost-btn">
                              Download the deck
                            </DownloadButton>
                          )}
                          <DownloadButton refId={preview.id} kind="technical" className="studio-ghost-btn">
                            Download as PDF
                          </DownloadButton>
                          {preview.procedures.length > 0 && (
                            <DownloadButton refId={preview.id} kind="operations" className="studio-ghost-btn">
                              Operations manual (PDF)
                            </DownloadButton>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="studio-deepdive studio-deepdive--slim mb-10">
                      <p className="studio-deepdive-text">
                        <strong>Between the two:</strong> a deep-dive working session — 90 minutes
                        with our consultant, this plan corrected together, an exact quote at the
                        end. $200, credited in full against your build.
                      </p>
                      <a
                        className="studio-cta studio-deepdive-btn"
                        href={consultingEmailUrl(
                          `Deep-dive request — ${preview.business_name} (demo #${preview.id})`,
                          `Hi,\n\nI'd like to book the deep-dive working session for my demo (${window.location.origin}${studioResultPath(preview.id)}).\n\nPreferred days and times: \n`,
                        )}
                      >
                        Request your deep-dive
                      </a>
                    </div>
                    {preview.procedures.length > 0 && (
                      <div className="mb-10">
                        <p className="studio-kicker mb-1">Core procedures</p>
                        <p className="studio-plan-rostertext mb-4">
                          The routines this business runs on once live — who, or which AI, does
                          each step. The layer a franchise manual is made of.
                        </p>
                        <div className="studio-sops">
                          {preview.procedures.map((p) => (
                            <div className="studio-sop" key={p.name}>
                              <p className="studio-sop-name">{p.name}</p>
                              {p.trigger && (
                                <p className="studio-sop-trigger">Starts when: {p.trigger}</p>
                              )}
                              <ol className="studio-sop-steps">
                                {p.steps.map((st, i) => (
                                  <li key={i}>
                                    {st.actor && (
                                      /* the model may write "ai (Module Name)" — treat any
                                         ai-prefixed actor as the AI, keep the module name */
                                      <span
                                        className={`studio-sop-actor${/^ai\b/i.test(st.actor) ? ' studio-sop-actor--ai' : ''}`}
                                      >
                                        {/^ai\b/i.test(st.actor) ? st.actor.replace(/^ai\s*/i, '').replace(/^\((.*)\)$/, 'AI · $1') || 'AI' : st.actor}
                                      </span>
                                    )}
                                    {st.step}
                                  </li>
                                ))}
                              </ol>
                              {p.exceptions.length > 0 && (
                                <div className="studio-sop-ex">
                                  {p.exceptions.map((e, i) => (
                                    <p key={i}>
                                      <strong>If {e.when}:</strong> {e.then}
                                    </p>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <TechnicalCinematic preview={preview} />
                  </div>
                )}

                {activeTab === 'team' && preview.organization && (
                  <div className="studio-tabpanel-extra">
                    <p className="studio-kicker mb-1">The organization - humans and AI on one chart</p>
                    <p className="studio-plan-rostertext mb-4">
                      Who runs this day to day, what each role decides alone, and where it hands off.
                    </p>
                    <div className="studio-orggrid">
                      {preview.organization.roles.map((r) => (
                        <div className={`studio-orgrole${r.type === 'ai' ? ' studio-orgrole--ai' : ''}`} key={r.role}>
                          <p className="studio-orgrole-name">
                            {r.role}
                            <span className="studio-orgrole-type">{r.type === 'ai' ? 'AI' : 'Human'}</span>
                          </p>
                          {r.responsibilities.length > 0 && (
                            <p className="studio-orgrole-resp">{r.responsibilities.join(' · ')}</p>
                          )}
                          {r.decides_alone && (
                            <p className="studio-orgrole-line"><span>Decides alone</span>{r.decides_alone}</p>
                          )}
                          {r.hands_off && (
                            <p className="studio-orgrole-line"><span>Hands off</span>{r.hands_off}</p>
                          )}
                        </div>
                      ))}
                    </div>
                    {preview.organization.change_impact.length > 0 && (
                      <div className="mt-6">
                        <p className="studio-kicker mb-2">What changes for your people</p>
                        <div className="studio-orgimpact">
                          {preview.organization.change_impact.map((c) => (
                            <p key={c.role}>
                              <strong>{c.role}:</strong> {c.what_changes}
                              {c.must_learn && <em> Must learn: {c.must_learn}</em>}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'playbook' && preview.playbook && (
                  <div className="studio-tabpanel">
                    <PlaybookCinematic preview={preview} />
                  </div>
                )}

                {activeTab === 'plans' && (
                  <div className="studio-tabpanel">
                    <PlansPanel preview={preview} />
                  </div>
                )}

                {/* The empty-state panel above already offers its own way
                    forward — a second CTA under it just reads as clutter. */}
                {screens.length > 0 && (
                  <div className="mt-16 flex flex-wrap items-center gap-4">
                    <button type="button" className="studio-cta max-w-xs" onClick={startOver}>
                      Design another
                    </button>
                    <p className="text-sm text-slate-600">
                      Want this built for real? Reply to us from the address you gave — we already
                      have the blueprint.
                    </p>
                  </div>
                )}
                </div>
              </motion.section>
            )}

            {act === 'failed' && (
              <motion.section key="failed" {...fade} transition={{ duration: 0.45 }}>
                <div className="max-w-xl mx-auto studio-panel p-8 text-center">
                  <p className="studio-kicker mb-4">The studio hit a wall</p>
                  <h1 className="studio-display text-3xl font-bold text-navy">
                    That run didn't make it
                  </h1>
                  <p className="mt-4 text-slate-600">
                    {failureDetail || 'Something in the pipeline failed and the run was stopped. Nothing was charged to you, and trying again usually just works.'}
                  </p>
                  <button type="button" className="studio-cta mt-8" onClick={startOver}>
                    Try again
                  </button>
                </div>
              </motion.section>
            )}

            {act === 'missing' && (
              <motion.section key="missing" {...fade} transition={{ duration: 0.45 }}>
                <div className="max-w-xl mx-auto studio-panel p-8 text-center">
                  <p className="studio-kicker mb-4">Nothing at this address</p>
                  <h1 className="studio-display text-3xl font-bold text-navy">
                    We couldn't find that run
                  </h1>
                  <p className="mt-4 text-slate-600">
                    The link may have a typo, or it may point at a studio run that no longer
                    exists. Designing a fresh set takes about three minutes.
                  </p>
                  <button type="button" className="studio-cta mt-8" onClick={startOver}>
                    Design my software
                  </button>
                </div>
              </motion.section>
            )}
          </AnimatePresence>
      </main>

      {reviewToken && act === 'reveal' && preview?.review_status === 'pending' && (
        <div className="studio-reviewbar" role="region" aria-label="Review controls">
          <div className="studio-reviewbar-info">
            <strong>Review mode</strong>
            <span>
              This engagement awaits your approval.
              {preview.qa_report && (
                <button type="button" className="studio-reviewbar-qa" onClick={() => setQaOpen((o) => !o)}>
                  {preview.qa_report.checks.filter((c) => c.passed).length}/{preview.qa_report.checks.length} checks
                  passed · {preview.qa_report.findings.length} findings
                </button>
              )}
            </span>
          </div>
          <div className="studio-reviewbar-actions">
            <button type="button" className="studio-ghost-btn" onClick={openEditor} disabled={reviewBusy}>
              Edit documents
            </button>
            <button type="button" className="studio-cta" onClick={() => void doApprove()} disabled={reviewBusy}>
              {reviewBusy ? 'Working…' : 'Approve & release'}
            </button>
          </div>
          {qaOpen && preview.qa_report && (
            <div className="studio-reviewbar-findings">
              {preview.qa_report.findings.length === 0 && <p>No findings — the auditors passed it clean.</p>}
              {preview.qa_report.findings.map((f, i) => (
                <p key={i}>
                  <strong>[{f.severity}]</strong> {f.where ? `${f.where}: ` : ''}
                  {f.issue}
                  {f.fix && <em> → {f.fix}</em>}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {editOpen && (
        <div className="studio-editor" role="dialog" aria-label="Edit documents">
          <div className="studio-editor-panel">
            <p className="studio-kicker mb-2">The red pen — your edits flow into every PDF</p>
            <label>The Blueprint</label>
            <textarea value={editBp} onChange={(e) => setEditBp(e.target.value)} rows={12} />
            <label>The Technical Plan</label>
            <textarea value={editTech} onChange={(e) => setEditTech(e.target.value)} rows={12} />
            <div className="studio-editor-actions">
              <button type="button" className="studio-ghost-btn" onClick={() => setEditOpen(false)} disabled={reviewBusy}>
                Cancel
              </button>
              <button type="button" className="studio-cta" onClick={() => void doSaveDocs()} disabled={reviewBusy}>
                {reviewBusy ? 'Saving…' : 'Save documents'}
              </button>
            </div>
          </div>
        </div>
      )}

      <dialog
        ref={dialogRef}
        className="studio-lightbox"
        onClick={(e) => {
          if (e.target === dialogRef.current) closeLightbox();
        }}
        onClose={() => setLightbox(null)}
      >
        {lightbox && (
          <>
            <img src={lightbox.src} alt={lightbox.alt} />
            <button type="button" className="studio-lightbox-close" onClick={closeLightbox}>
              Close
            </button>
          </>
        )}
      </dialog>

      {act === 'reveal' ? <SiteFooter /> : null}
    </div>
  );
}
