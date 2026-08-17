import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import {
  createStudioRequest,
  getStudioPreview,
  getStudioProgress,
  consultantAssetUrl,
  isAtCapacity,
  isNotFound,
  studioDeckUrl,
  studioResultPath,
  type StudioPreview,
  type StudioProgress,
  type StudioScreen,
} from '../api/consultant';
import {
  splitH2Sections,
  findSection,
  splitH3Subsections,
  parseListItems,
  parseNestedPhases,
  firstParagraph,
  stripInlineMarkdown,
} from '../utils/consultantMarkdown';
import { whatsappUrl } from '../api/client';
import {
  BUILD_PLANS,
  suggestBusinessAddons,
  addonAvailable,
  addonIncluded,
  summarizeSelection,
  type BuildPlan,
} from '../data/buildPlans';
import '../styles/studio.css';

// The orchestrator's real stages, told as studio work. `at` mirrors the
// progress_pct each stage emits so the timeline advances from the poll's
// pct even if a stage name ever changes server-side.
const STAGES = [
  { at: 10, name: 'Reading your business', sub: 'What you do, who you serve, where it hurts' },
  { at: 25, name: 'Consulting', sub: 'Deciding what your AI employees should take over' },
  { at: 35, name: 'Planning the product', sub: 'Which screens your software actually needs' },
  { at: 42, name: 'Decomposing the business', sub: 'Module by module, each with its own spec' },
  { at: 50, name: 'Writing the blueprint', sub: 'The modules, the money, the build order' },
  { at: 60, name: 'Writing your playbook', sub: 'Every step you take, who does it, and when' },
  { at: 62, name: 'Art direction', sub: 'Layout, palette and hierarchy — set per screen' },
  { at: 70, name: 'Rendering your screens', sub: 'Drawn in parallel, inspected, re-rolled if flawed' },
] as const;

const RENDER_WHISPERS = [
  'Every screen is inspected by two independent checks before it ships…',
  'A screen that fails inspection gets one re-roll — quality over speed…',
  'Typesetting your real numbers, not placeholders…',
  'Your navigation, your services, your customers — nothing generic…',
];

// 'loading' is the beat between opening a result URL and knowing what is at
// the other end; 'missing' is an id that was never issued.
type Act = 'intake' | 'loading' | 'building' | 'reveal' | 'failed' | 'missing';

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

// What a serious buyer engages a consultancy for — not what the tool does.
// Numbered rather than titled "Features", on purpose.
const OUTCOMES = [
  {
    icon: INTAKE_ICONS.workflow,
    title: 'Your workflow, redesigned',
    body: 'See how the operation changes when AI is embedded directly into the work.',
  },
  {
    icon: INTAKE_ICONS.cpu,
    title: 'Your AI system, visualized',
    body: 'A concrete view of the agents, interfaces, data, integrations, and human handoffs we’d build.',
  },
  {
    icon: INTAKE_ICONS.chart,
    title: 'Your business case, modeled',
    body: 'Understand where the value comes from, what can be automated or augmented, and why the system is worth building.',
  },
] as const;

/** What the intake actually produces isn't three app screens — it's an
 *  understanding of the business that then gets architected into a system.
 *  This says that visually instead of showing UI mockups, which is exactly
 *  the read this page is trying not to give. Memoized: it takes no props
 *  and never changes, so it has no reason to re-reconcile on every
 *  keystroke the intake form's state changes trigger a re-render for. */
const SystemDiagram = memo(function SystemDiagram() {
  return (
    <svg
      className="studio-diagram"
      viewBox="0 0 640 258"
      role="img"
      aria-label="Your business connects through AI agents, data and tools, to human review"
    >
      <g className="studio-diagram-lines">
        <line x1="160" y1="130" x2="248" y2="40" />
        <line x1="160" y1="130" x2="248" y2="128" />
        <line x1="160" y1="130" x2="248" y2="216" />
        <line x1="392" y1="40" x2="480" y2="130" />
        <line x1="392" y1="128" x2="480" y2="130" />
        <line x1="392" y1="216" x2="480" y2="130" />
      </g>
      <circle cx="160" cy="130" r="3" className="studio-diagram-junction" />
      <circle cx="480" cy="130" r="3" className="studio-diagram-junction" />
      <g className="studio-diagram-node" transform="translate(20,106)">
        <rect width="140" height="48" rx="8" />
        <path d={INTAKE_ICONS.building} transform="translate(16,14) scale(0.83)" className="studio-diagram-nodeicon" />
        <text x="86" y="29" textAnchor="middle">
          Your business
        </text>
      </g>
      <g className="studio-diagram-node studio-diagram-node--core" transform="translate(248,18)">
        <rect width="144" height="44" rx="8" />
        <path d={INTAKE_ICONS.sparkle} transform="translate(20,12) scale(0.83)" className="studio-diagram-nodeicon studio-diagram-nodeicon--core" />
        <text x="90" y="27" textAnchor="middle">
          AI agents
        </text>
      </g>
      <g className="studio-diagram-node studio-diagram-node--core" transform="translate(248,106)">
        <rect width="144" height="44" rx="8" />
        <path d={INTAKE_ICONS.database} transform="translate(32,12) scale(0.83)" className="studio-diagram-nodeicon studio-diagram-nodeicon--core" />
        <text x="90" y="27" textAnchor="middle">
          Data
        </text>
      </g>
      <g className="studio-diagram-node studio-diagram-node--core" transform="translate(248,194)">
        <rect width="144" height="44" rx="8" />
        <path d={INTAKE_ICONS.wrench} transform="translate(30,12) scale(0.83)" className="studio-diagram-nodeicon studio-diagram-nodeicon--core" />
        <text x="90" y="27" textAnchor="middle">
          Tools
        </text>
      </g>
      <g className="studio-diagram-node" transform="translate(480,106)">
        <rect width="140" height="48" rx="8" />
        <path d={INTAKE_ICONS.user} transform="translate(14,14) scale(0.83)" className="studio-diagram-nodeicon" />
        <text x="84" y="29" textAnchor="middle">
          Human review
        </text>
      </g>
    </svg>
  );
});

/** The same idea, laid out for a narrow screen — a compact cross instead of
 *  a wide left-to-right flow, since the desktop diagram's 640px viewBox has
 *  nothing sensible to shrink to at phone width. Fewer nodes on purpose:
 *  "human review" and the AI/data/tools split collapse into one "AI systems
 *  concept" core, with the team added at the point that's most legible in
 *  a plus shape — this is a condensed read of the same idea, not a partial
 *  one. */
const MobileSystemDiagram = memo(function MobileSystemDiagram() {
  return (
    <svg
      className="studio-diagram-mobile"
      viewBox="0 0 300 300"
      role="img"
      aria-label="Your business and team feed an AI systems concept, built from your data and tools"
    >
      <g className="studio-diagram-lines">
        <line x1="150" y1="62" x2="150" y2="110" />
        <line x1="150" y1="190" x2="150" y2="240" />
        <line x1="68" y1="150" x2="75" y2="150" />
        <line x1="225" y1="150" x2="232" y2="150" />
      </g>
      <g className="studio-diagram-node" transform="translate(85,20)">
        <rect width="130" height="42" rx="8" />
        <text x="65" y="26" textAnchor="middle">
          Your business
        </text>
      </g>
      <g className="studio-diagram-node" transform="translate(10,130)">
        <rect width="58" height="40" rx="8" />
        <text x="29" y="25" textAnchor="middle">
          Your data
        </text>
      </g>
      <g className="studio-diagram-node" transform="translate(232,130)">
        <rect width="58" height="40" rx="8" />
        <text x="29" y="25" textAnchor="middle">
          Your tools
        </text>
      </g>
      <g className="studio-diagram-node studio-diagram-node--core" transform="translate(75,110)">
        <rect width="150" height="80" rx="10" />
        <text x="75" y="36" textAnchor="middle">
          AI systems
        </text>
        <text x="75" y="52" textAnchor="middle">
          concept
        </text>
      </g>
      <g className="studio-diagram-node" transform="translate(90,240)">
        <rect width="120" height="42" rx="8" />
        <text x="60" y="26" textAnchor="middle">
          Your team
        </text>
      </g>
    </svg>
  );
});

// The intake mirrors the old build-request wizard's five steps and fields —
// that data meaningfully shapes the analysis (see analyze.j2), so trimming
// it down to "just enough for a demo" was throwing away signal the pipeline
// already knows how to use.
const INTAKE_STEPS = [
  { id: 'business', label: 'Business', subtitle: 'Tell us who you are' },
  { id: 'challenge', label: 'Challenge', subtitle: 'What you need solved' },
  { id: 'inspiration', label: 'Inspiration', subtitle: 'A tool you admire' },
  { id: 'project', label: 'Project', subtitle: 'Scope & AI appetite' },
  { id: 'contact', label: 'Contact', subtitle: 'Where to send it' },
] as const;

const NEEDS_AI_OPTIONS = ['Yes, definitely', 'Maybe, if it adds value', 'No, keep it simple'];
const NEEDS_AI_MAP: Record<string, string> = {
  'Yes, definitely': 'yes',
  'Maybe, if it adds value': 'maybe',
  'No, keep it simple': 'no',
};
const NEEDS_AI_REVERSE: Record<string, string> = {
  yes: 'Yes, definitely',
  maybe: 'Maybe, if it adds value',
  no: 'No, keep it simple',
};
const BUDGET_OPTIONS = ['Starter scope', 'Standard scope', 'Full build', 'Not sure yet'];
const TIMELINE_OPTIONS = ['ASAP (2–4 weeks)', '1–2 months', '2–3 months', 'Flexible'];

/** Tiers built on the real validation rule (30 chars minimum, see
 *  validateStep) rather than an arbitrary "AI is impressed" fiction — this
 *  turns a threshold that already exists into live feedback instead of a
 *  surprise error on blur. */
function specificityTier(text: string): { pct: number; label: string; tone: 'low' | 'mid' | 'high' } {
  const len = text.trim().length;
  if (len === 0) return { pct: 0, label: 'What do you do, and for whom?', tone: 'low' };
  if (len < 30) {
    return { pct: Math.round((len / 30) * 40), label: 'A little more — what do you do, and for whom?', tone: 'low' };
  }
  if (len < 120) {
    return {
      pct: 40 + Math.round(((len - 30) / 90) * 40),
      label: 'Good — a bit more detail helps the screens feel real',
      tone: 'mid',
    };
  }
  return {
    pct: Math.min(100, 80 + Math.round(((len - 120) / 120) * 20)),
    label: 'Excellent detail — this will feel like yours',
    tone: 'high',
  };
}

function SpecificityMeter({ value }: { value: string }) {
  const { pct, label, tone } = specificityTier(value);
  return (
    <div className="studio-specificity" data-tone={tone}>
      <div className="studio-specificity-track">
        <div className="studio-specificity-fill" style={{ width: `${pct}%` }} />
      </div>
      <p className="studio-specificity-label">{label}</p>
    </div>
  );
}

function StudioPills({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="studio-pills">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          className={`studio-pill${value === opt ? ' studio-pill--active' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

// Kept only as a bridge for someone who lands on bare /studio with a run
// still going — the URL is the source of truth, this is the safety net.
const RESUME_KEY = 'bmv_studio_request_id';

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

/** The decompose-era blueprint: rendered from the structured decomposition
 *  itself (preview.modules + preview.business_case) rather than re-parsed
 *  out of the markdown it produced — the markdown is only consulted for
 *  the sections that exist nowhere else (executive summary, build order,
 *  success measures). Used when the run has modules; older runs keep
 *  BlueprintCinematic below. */
function DecomposedBlueprint({ preview }: { preview: StudioPreview }) {
  const md = preview.mvp_blueprint ?? '';
  const sections = useMemo(() => splitH2Sections(md), [md]);
  const exec = findSection(sections, /executive|summary/);
  const buildFirst = findSection(sections, /build first/);
  const success = findSection(sections, /success/);
  const bc = preview.business_case;

  const execText = exec
    ? stripInlineMarkdown(exec.body.replace(/\n+/g, ' '))
    : preview.preview_summary ?? '';
  const successRows = success ? parseListItems(success.body) : [];

  return (
    <div className="studio-plan">
      <PlanHero
        kicker="Executive summary"
        title={preview.concept_name || preview.business_name}
        lead={execText}
      />

      {bc && (
        <div>
          <p className="studio-kicker mb-2">How this makes money</p>
          {bc.payback_logic && (
            <p className="studio-plan-checklist-lead max-w-3xl">{bc.payback_logic}</p>
          )}
          <div className="studio-plan-columns mt-4">
            {(bc.revenue_streams?.length ?? 0) > 0 && (
              <PlanPanel eyebrow="Revenue">
                <div className="studio-plan-checklist">
                  {bc.revenue_streams.map((s, i) => (
                    <div className="studio-plan-checkrow" key={s.name || i}>
                      <CheckIcon className="studio-plan-checkicon" />
                      <p>
                        <strong className="text-slate-900">{s.name}.</strong> {s.description}
                      </p>
                    </div>
                  ))}
                </div>
              </PlanPanel>
            )}
            {(bc.costs_removed?.length ?? 0) > 0 && (
              <PlanPanel eyebrow="Costs removed">
                <div className="studio-plan-checklist">
                  {bc.costs_removed.map((c, i) => (
                    <div className="studio-plan-checkrow" key={c.cost || i}>
                      <CheckIcon className="studio-plan-checkicon" />
                      <p>
                        <strong className="text-slate-900">{c.cost}.</strong> {c.how}
                      </p>
                    </div>
                  ))}
                </div>
              </PlanPanel>
            )}
          </div>
          {(bc.pricing_levers?.length ?? 0) > 0 && (
            <div className="studio-plan-checklist studio-plan-checklist--grid mt-4">
              {bc.pricing_levers.map((l) => (
                <div className="studio-plan-checkrow" key={l}>
                  <CheckIcon className="studio-plan-checkicon" />
                  <p>{l}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div>
        <p className="studio-kicker mb-4">The product, module by module</p>
        <div className="studio-plan-roster studio-plan-roster--stacked">
          {preview.modules.map((m, i) => {
            const spec = m.spec;
            return (
              <div className="studio-panel studio-plan-panel" key={m.id || i}>
                <div className="flex items-start justify-between gap-3 flex-wrap mb-2">
                  <p className="studio-plan-rostername text-base">
                    <span className="studio-plan-featureno inline mr-2">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    {m.name}
                  </p>
                  {(m.users?.length ?? 0) > 0 && (
                    <span className="studio-diagnosis-badge">{m.users.join(' · ')}</span>
                  )}
                </div>
                <p className="studio-plan-rostertext mb-1">{m.purpose}</p>
                {m.pain_point_addressed && (
                  <p className="studio-plan-roadmap-field">
                    <span>Exists because: </span>
                    {m.pain_point_addressed}
                  </p>
                )}
                {(spec?.features?.length ?? 0) > 0 && (
                  <div className="studio-plan-checklist mt-3">
                    {spec!.features.map((f, j) => (
                      <div className="studio-plan-checkrow" key={f.name || j}>
                        <CheckIcon className="studio-plan-checkicon" />
                        <p>
                          <strong className="text-slate-900">{f.name}.</strong> {f.description}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
                {spec?.ai?.role && (
                  <p className="studio-plan-roadmap-field mt-3">
                    <span>Where the AI works: </span>
                    {spec.ai.role}
                    {spec.ai.hands_off ? ` Hands off to a human: ${spec.ai.hands_off}` : ''}
                  </p>
                )}
                {(spec?.kpis?.length ?? 0) > 0 && (
                  <p className="studio-plan-roadmap-field">
                    <span>You'll know it's working when: </span>
                    {spec!.kpis.join(' · ')}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {(buildFirst || successRows.length > 0) && (
        <div className="studio-plan-columns">
          {buildFirst && (
            <PlanPanel eyebrow="What we'd build first">
              <BlueprintProse text={buildFirst.body} />
            </PlanPanel>
          )}
          {successRows.length > 0 && (
            <PlanPanel eyebrow="What success looks like">
              <div className="studio-plan-checklist">
                {successRows.map((row, i) => (
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
                      <span className={`studio-pb-who studio-pb-who--${s.who}`}>
                        {PLAYBOOK_WHO[s.who] ?? s.who}
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
  const waMessage = `Hi, I saw the "${preview.concept_name || preview.business_name}" demo and want to move forward.\n\n${selectionSummary}`;

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
        {preview.deck_available && (
          <a className="studio-cta studio-plans-deckbtn mt-6" href={studioDeckUrl(preview.id)}>
            Download the deck (PowerPoint)
          </a>
        )}
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
        <a
          className="studio-cta studio-stepnav-cta"
          href={whatsappUrl(waMessage)}
          target="_blank"
          rel="noopener noreferrer"
        >
          WhatsApp this plan
        </a>
        <p className="studio-hint">
          Or just reply to the email you gave us — we already have the blueprint.
        </p>
      </div>
    </div>
  );
}

export default function StudioPage() {
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const { id: idParam } = useParams<{ id: string }>();
  const routeId = idParam && /^\d+$/.test(idParam) ? Number(idParam) : null;

  const [act, setAct] = useState<Act>(routeId == null ? 'intake' : 'loading');
  const [progress, setProgress] = useState<StudioProgress | null>(null);
  const [preview, setPreview] = useState<StudioPreview | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [failureDetail, setFailureDetail] = useState<string | null>(null);
  const [whisper, setWhisper] = useState(0);
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
    needs_ai: 'yes',
    budget_range: BUDGET_OPTIONS[0],
    timeline: 'Flexible',
    whatsapp: '',
    site_url: '',
    revenue_today: '',
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(0);

  const dialogRef = useRef<HTMLDialogElement>(null);
  const elapsed = useElapsed(act === 'building', startedAt);

  const resultUrl = routeId != null ? `${window.location.origin}${studioResultPath(routeId)}` : null;

  const showResult = useCallback(async (id: number) => {
    try {
      const data = await getStudioPreview(id);
      setPreview(data);
      setActiveTab('screens');
      setAct('reveal');
    } catch (err) {
      if (isNotFound(err)) setAct('missing');
      else {
        setFailureDetail('Your screens were generated, but the studio could not load them just now. Refreshing this page usually brings them back.');
        setAct('failed');
      }
    }
  }, []);

  // Decide what a run's state means — used both on first load of a result URL
  // and on every poll, so there is exactly one set of rules.
  const applyProgress = useCallback(
    (id: number, p: StudioProgress) => {
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
      if (p.is_generating) {
        sessionStorage.setItem(RESUME_KEY, String(id));
        setAct('building');
        return;
      }
      // Not generating and not failed: either finished, or a run that was
      // abandoned before it ever started. showResult tells them apart by
      // whether there is anything to show.
      sessionStorage.removeItem(RESUME_KEY);
      void showResult(id);
    },
    [showResult],
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
        setAct('building');
        return;
      }
      const stored = sessionStorage.getItem(RESUME_KEY);
      if (stored && /^\d+$/.test(stored)) navigate(studioResultPath(Number(stored)), { replace: true });
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
        } else {
          setFailureDetail('The studio is not reachable right now. Your run is safe — this page will show it as soon as the connection is back.');
          setAct('failed');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeId, navigate, applyProgress]);

  // Rotate the rendering-stage whispers.
  useEffect(() => {
    if (act !== 'building') return;
    const t = setInterval(() => setWhisper((w) => (w + 1) % RENDER_WHISPERS.length), 5200);
    return () => clearInterval(t);
  }, [act]);

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
  const validateStep = (i: number): boolean => {
    let key: keyof FieldErrors | null = null;
    let message: string | null = null;
    if (i === 0 && form.business_name.trim().length < 2) {
      key = 'business_name';
      message = 'Give your business its real name.';
    }
    if (i === 1 && form.business_description.trim().length < 30) {
      key = 'business_description';
      message = 'A couple of sentences — what you do, for whom, and what eats your day.';
    }
    if (i === 2 && form.reference_url.trim() && !form.what_you_like.trim()) {
      key = 'what_you_like';
      message = "Tell us what to borrow from it — otherwise we won't know what you liked.";
    }
    if (i === 4 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      key = 'email';
      message = 'A real address, so we can reach you about it.';
    }
    setErrors((prev) => {
      const next = { ...prev };
      const clears: (keyof FieldErrors)[] =
        i === 0 ? ['business_name'] : i === 1 ? ['business_description'] : i === 2 ? ['what_you_like'] : i === 4 ? ['email'] : [];
      clears.forEach((k) => delete next[k]);
      if (key) next[key] = message ?? undefined;
      return next;
    });
    return key === null;
  };

  const goNext = () => {
    if (!validateStep(step)) return;
    setStep((s) => Math.min(s + 1, INTAKE_STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Enter in a text field submits the nearest form regardless of which
    // button is on screen — on an earlier step that means "next", not "go".
    if (step < INTAKE_STEPS.length - 1) {
      goNext();
      return;
    }
    setSubmitError(null);
    // The last step is the only one whose Continue button submits — walk
    // every step's rule once more so a stale error from an earlier step
    // (edited, then navigated away from) can't slip through.
    const allValid = [0, 1, 2, 4].every((i) => validateStep(i));
    if (!allValid || submitting) return;
    setSubmitting(true);
    try {
      const { id } = await createStudioRequest({
        business_name: form.business_name.trim(),
        business_description: form.business_description.trim(),
        email: form.email.trim(),
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
      });
      sessionStorage.setItem(RESUME_KEY, String(id));
      // The run gets its address the moment it exists, not when it finishes —
      // so a refresh, a closed laptop or a shared link all land somewhere.
      navigate(studioResultPath(id));
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

  const pct = progress?.pct ?? 4;
  const stageStates = useMemo(
    () =>
      STAGES.map((s, i) => {
        const nextAt = STAGES[i + 1]?.at ?? 100;
        if (pct >= nextAt) return 'done';
        if (pct >= s.at) return 'active';
        return 'pending';
      }),
    [pct],
  );

  const allScreens: StudioScreen[] = preview?.generated_pages.attraction_images ?? [];
  const screens = allScreens.filter((s) => !brokenSrc[s.image_url]);
  const visibleTabs = preview ? RESULT_TABS.filter((t) => t.available(preview)) : [];
  const buildingName = progress?.business_name || form.business_name.trim() || 'Your business';
  const fade = reduceMotion
    ? {}
    : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -12 } };

  return (
    <div className="studio-page relative">
      <SiteNav />
      <div className="studio-grid-field" aria-hidden="true" />

      <main className="relative z-10 section-padding pt-28 pb-20">
        <div className="container-max max-w-6xl">
          <AnimatePresence mode="wait">
            {act === 'loading' && (
              <motion.section key="loading" {...fade} transition={{ duration: 0.3 }}>
                <div className="max-w-xl mx-auto text-center py-24">
                  <span className="studio-spinner" aria-hidden="true" />
                  <p className="mt-6 text-slate-600">Opening your studio run…</p>
                </div>
              </motion.section>
            )}

            {act === 'intake' && (
              <motion.section key="intake" {...fade} transition={{ duration: 0.45 }}>
                {/* items-stretch + the left column as a flex column: the row's
                    height is the form's height, and mt-auto on the diagram
                    pins its bottom edge to the form's bottom edge. */}
                <div className="grid lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-16 items-start lg:items-stretch">
                  <div className="pt-4 lg:flex lg:flex-col lg:min-h-0">
                    {/* Badge above the kicker on mobile (matching the phone
                        design); kicker first with the badge stacked under it
                        on desktop (matching the desktop design). */}
                    <div className="flex flex-col-reverse sm:flex-col items-start gap-3 mb-6">
                      <p className="studio-kicker">The Demo</p>
                      <span className="studio-trust-badge">
                        <Icon path={INTAKE_ICONS.shield} className="w-3.5 h-3.5" />
                        Built around your business — not a generic AI demo.
                      </span>
                    </div>
                    <h1 className="studio-display text-4xl sm:text-5xl lg:text-[2.65rem] font-bold leading-[1.05] text-navy">
                      Before you invest in AI, see exactly what we'd build.
                    </h1>
                    <p className="mt-4 text-slate-600 text-base sm:text-lg lg:text-base max-w-xl leading-relaxed">
                      Tell us where your business is slow, manual, or expensive. We'll turn it
                      into a tailored AI system concept — built around your workflows, your data,
                      your tools, and your economics.
                    </p>

                    {/* On desktop the form sits right beside this copy — nothing
                        to jump to. On mobile it's a long scroll past the
                        diagram and three cards, so give it a shortcut. */}
                    <div className="mt-7 flex items-center gap-4 lg:hidden">
                      <a href="#studio-form" className="studio-cta studio-jumplink">
                        Start your demo
                        <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />
                      </a>
                      <span className="flex items-center gap-1.5 text-xs text-slate-500 whitespace-nowrap">
                        <Icon path={INTAKE_ICONS.shield} className="w-3.5 h-3.5" />
                        No call required
                      </span>
                    </div>

                    <div className="mt-7 studio-outcomes">
                      {OUTCOMES.map((o, i) => (
                        <div className="studio-outcome" key={o.title}>
                          <span className="studio-outcome-bubble">
                            <Icon path={o.icon} className="studio-outcome-icon" />
                          </span>
                          <span className="studio-outcome-no">{String(i + 1).padStart(2, '0')}</span>
                          <div className="studio-outcome-body">
                            <h3 className="studio-outcome-title">{o.title}</h3>
                            <p className="studio-outcome-desc">{o.body}</p>
                          </div>
                          <Icon path="m8.25 4.5 7.5 7.5-7.5 7.5" className="studio-outcome-chevron" />
                        </div>
                      ))}
                    </div>

                    <div className="hidden lg:block lg:mt-auto lg:pt-5">
                      <SystemDiagram />
                    </div>
                    <div className="lg:hidden">
                      <MobileSystemDiagram />
                    </div>
                  </div>

                  <motion.form
                    id="studio-form"
                    className="studio-panel p-6 sm:p-8"
                    onSubmit={submit}
                    noValidate
                    initial={reduceMotion ? undefined : { opacity: 0, y: 24 }}
                    animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.08 }}
                  >
                    <div className="studio-steps" aria-hidden="true">
                      {INTAKE_STEPS.map((s, i) => (
                        <div className="studio-step" data-state={i < step ? 'done' : i === step ? 'active' : 'pending'} key={s.id}>
                          <span className="studio-step-no">{i < step ? '✓' : i + 1}</span>
                          <span className="studio-step-label">{s.label}</span>
                        </div>
                      ))}
                    </div>
                    <p className="studio-hint mb-6">{INTAKE_STEPS[step].subtitle}</p>

                    <AnimatePresence mode="wait">
                      <motion.div
                        key={step}
                        initial={reduceMotion ? undefined : { opacity: 0, x: 16 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={reduceMotion ? undefined : { opacity: 0, x: -16 }}
                        transition={{ duration: 0.3 }}
                        className="space-y-5"
                      >
                        {step === 0 && (
                          <>
                            <div className="studio-field" data-invalid={!!errors.business_name}>
                              <label htmlFor="st-name">Business name</label>
                              <div className="studio-inputwrap">
                                <Icon path={INTAKE_ICONS.building} />
                                <input
                                  id="st-name"
                                  value={form.business_name}
                                  onChange={(e) => setForm({ ...form, business_name: e.target.value })}
                                  placeholder="Beacon Physiotherapy"
                                  autoComplete="organization"
                                />
                              </div>
                              {errors.business_name && <p className="studio-error-text">{errors.business_name}</p>}
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-industry">
                                Industry <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <div className="studio-inputwrap">
                                <Icon path={INTAKE_ICONS.briefcase} />
                                <input
                                  id="st-industry"
                                  value={form.industry}
                                  onChange={(e) => setForm({ ...form, industry: e.target.value })}
                                  placeholder="Physiotherapy clinic"
                                />
                              </div>
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-siteurl">
                                Your website or Google/Instagram page{' '}
                                <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <div className="studio-inputwrap">
                                <Icon path={INTAKE_ICONS.globe} />
                                <input
                                  id="st-siteurl"
                                  value={form.site_url}
                                  onChange={(e) => setForm({ ...form, site_url: e.target.value })}
                                  placeholder="https://yourbusiness.com"
                                  autoComplete="url"
                                />
                              </div>
                              <p className="studio-hint">
                                We'll read it before analyzing — real services, hours and tone make
                                everything sharper.
                              </p>
                            </div>
                          </>
                        )}

                        {step === 1 && (
                          <>
                            <div className="studio-field" data-invalid={!!errors.business_description}>
                              <label htmlFor="st-desc">What does it do?</label>
                              <textarea
                                id="st-desc"
                                rows={4}
                                value={form.business_description}
                                onChange={(e) => setForm({ ...form, business_description: e.target.value })}
                                placeholder="Physiotherapy clinic with six therapists. Patients book assessments and follow-ups; we juggle availability, insurance pre-approvals and no-shows…"
                              />
                              {errors.business_description ? (
                                <p className="studio-error-text">{errors.business_description}</p>
                              ) : (
                                <SpecificityMeter value={form.business_description} />
                              )}
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-customers">
                                Who are your customers? <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-customers"
                                value={form.target_customers}
                                onChange={(e) => setForm({ ...form, target_customers: e.target.value })}
                                placeholder="Busy professionals, 30-55, referred by their doctor"
                              />
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-problem">
                                Biggest headache <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-problem"
                                value={form.main_problem}
                                onChange={(e) => setForm({ ...form, main_problem: e.target.value })}
                                placeholder="Scheduling eats our evenings"
                              />
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-outcome">
                                What would fixing it get you? <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-outcome"
                                value={form.desired_outcome}
                                onChange={(e) => setForm({ ...form, desired_outcome: e.target.value })}
                                placeholder="Evenings back, zero double-bookings"
                              />
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-revenue">
                                How do you make money today? <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-revenue"
                                value={form.revenue_today}
                                onChange={(e) => setForm({ ...form, revenue_today: e.target.value })}
                                placeholder="Per-session fees, packages, a monthly membership…"
                              />
                              <p className="studio-hint">
                                This is what lets the blueprint talk about your revenue, not revenue in general.
                              </p>
                            </div>
                          </>
                        )}

                        {step === 2 && (
                          <>
                            <div className="studio-field">
                              {/* "not your own website" is load-bearing: a real
                                  production lead put their own company site here
                                  because it was the only URL field they noticed. */}
                              <label htmlFor="st-refurl">
                                A tool you admire — not your own website{' '}
                                <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-refurl"
                                value={form.reference_url}
                                onChange={(e) => setForm({ ...form, reference_url: e.target.value })}
                                placeholder="https://example.com"
                                autoComplete="url"
                              />
                            </div>
                            <div className="studio-field" data-invalid={!!errors.what_you_like}>
                              <label htmlFor="st-refwhy">
                                What do you like about it?
                                {!form.reference_url.trim() && (
                                  <span className="text-slate-500 font-normal"> (optional)</span>
                                )}
                              </label>
                              <textarea
                                id="st-refwhy"
                                rows={3}
                                value={form.what_you_like}
                                onChange={(e) => setForm({ ...form, what_you_like: e.target.value })}
                                placeholder="The clean booking calendar and how simple it is to reschedule"
                              />
                              {errors.what_you_like && <p className="studio-error-text">{errors.what_you_like}</p>}
                            </div>
                          </>
                        )}

                        {step === 3 && (
                          <>
                            <div className="studio-field">
                              <label>Want AI running any of this?</label>
                              <StudioPills
                                options={NEEDS_AI_OPTIONS}
                                value={NEEDS_AI_REVERSE[form.needs_ai] ?? NEEDS_AI_OPTIONS[0]}
                                onChange={(v) => setForm({ ...form, needs_ai: NEEDS_AI_MAP[v] })}
                              />
                            </div>
                            <div className="studio-field">
                              <label>Rough scope</label>
                              <StudioPills
                                options={BUDGET_OPTIONS}
                                value={form.budget_range}
                                onChange={(v) => setForm({ ...form, budget_range: v })}
                              />
                            </div>
                            <div className="studio-field">
                              <label>Timeline</label>
                              <StudioPills
                                options={TIMELINE_OPTIONS}
                                value={form.timeline}
                                onChange={(v) => setForm({ ...form, timeline: v })}
                              />
                            </div>
                          </>
                        )}

                        {step === 4 && (
                          <>
                            <div className="studio-field" data-invalid={!!errors.email}>
                              <label htmlFor="st-email">Email</label>
                              <input
                                id="st-email"
                                type="email"
                                value={form.email}
                                onChange={(e) => setForm({ ...form, email: e.target.value })}
                                placeholder="you@yourbusiness.com"
                                autoComplete="email"
                              />
                              {errors.email && <p className="studio-error-text">{errors.email}</p>}
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-whatsapp">
                                WhatsApp <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-whatsapp"
                                value={form.whatsapp}
                                onChange={(e) => setForm({ ...form, whatsapp: e.target.value })}
                                placeholder="+1 555 010 1234"
                                autoComplete="tel"
                              />
                            </div>
                          </>
                        )}
                      </motion.div>
                    </AnimatePresence>

                    {submitError && (
                      <p className="studio-error-text mt-5" role="alert">
                        {submitError}
                      </p>
                    )}

                    <div className="studio-stepnav">
                      {step > 0 && (
                        <button type="button" className="studio-ghost-btn" onClick={goBack} disabled={submitting}>
                          Back
                        </button>
                      )}
                      {step < INTAKE_STEPS.length - 1 ? (
                        <button type="button" className="studio-cta studio-stepnav-cta" onClick={goNext}>
                          Continue
                          <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />
                        </button>
                      ) : (
                        <button className="studio-cta studio-stepnav-cta" type="submit" disabled={submitting}>
                          {submitting ? 'Opening the studio…' : 'Design my software'}
                          {!submitting && <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />}
                        </button>
                      )}
                    </div>
                    <p className="studio-hint studio-hint--trust text-center mt-4">
                      <Icon path={INTAKE_ICONS.shield} className="w-3.5 h-3.5" />
                      Free. No call, no deck — you watch it get made.
                    </p>
                  </motion.form>
                </div>
              </motion.section>
            )}

            {act === 'building' && (
              <motion.section key="building" {...fade} transition={{ duration: 0.45 }}>
                <div className="max-w-3xl mx-auto text-center mb-10">
                  <p className="studio-kicker mb-4">Now designing</p>
                  <h1 className="studio-display text-3xl sm:text-4xl font-bold text-navy">
                    {buildingName} is in the studio
                  </h1>
                  <p className="mt-3 text-slate-600">
                    {progress?.label ?? 'Warming up…'}
                    {progress?.detail ? <span className="text-slate-500"> — {progress.detail}</span> : null}
                  </p>
                </div>

                <div className="grid lg:grid-cols-[320px_1fr] gap-8 items-start">
                  <div className="studio-panel p-6">
                    {STAGES.map((s, i) => (
                      <div className="studio-stage-row" data-state={stageStates[i]} key={s.name}>
                        <span className="studio-stage-dot" aria-hidden="true" />
                        <div>
                          <p className="studio-stage-name">{s.name}</p>
                          <p className="studio-stage-sub">{s.sub}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="studio-panel p-6 sm:p-8">
                    <div className="studio-easel" role="img" aria-label="Your screens being drafted">
                      <span className="studio-easel-wire" style={{ left: '6%', top: '9%', width: '26%', height: '82%' }} />
                      <span className="studio-easel-wire" style={{ left: '36%', top: '9%', width: '58%', height: '30%' }} />
                      <span className="studio-easel-wire" style={{ left: '36%', top: '45%', width: '28%', height: '46%' }} />
                      <span className="studio-easel-wire" style={{ left: '68%', top: '45%', width: '26%', height: '46%' }} />
                    </div>

                    <div className="mt-6 flex items-center gap-4">
                      <div className="studio-meter flex-1">
                        <div className="studio-meter-fill" style={{ width: `${Math.max(4, pct)}%` }} />
                      </div>
                      <span className="studio-elapsed">{elapsed}</span>
                    </div>

                    <AnimatePresence mode="wait">
                      <motion.p
                        key={whisper}
                        className="mt-4 text-sm text-slate-600"
                        initial={reduceMotion ? undefined : { opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={reduceMotion ? undefined : { opacity: 0 }}
                        transition={{ duration: 0.5 }}
                      >
                        {RENDER_WHISPERS[whisper]}
                      </motion.p>
                    </AnimatePresence>

                    {resultUrl && (
                      <div className="studio-keepsafe mt-6">
                        <p className="studio-keepsafe-label">
                          This page is your run. Close it, come back, open it on your phone — the
                          address doesn't change.
                        </p>
                        <div className="studio-linkrow">
                          <code className="studio-link">{resultUrl}</code>
                          <button type="button" className="studio-ghost-btn" onClick={copyLink}>
                            {copied ? 'Copied' : 'Copy link'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </motion.section>
            )}

            {act === 'reveal' && preview && (
              <motion.section key="reveal" {...fade} transition={{ duration: 0.5 }}>
                <div className="max-w-3xl mx-auto text-center mb-10">
                  <p className="studio-kicker mb-4">Fresh from the studio</p>
                  <h1 className="studio-display text-4xl sm:text-5xl font-bold text-navy">
                    {preview.concept_name || `${preview.business_name} OS`}
                  </h1>
                  <p className="mt-4 text-slate-600 text-lg">
                    Designed for {preview.business_name}
                    {preview.industry ? ` · ${preview.industry}` : ''}.
                    {screens.length > 0 ? ' Click any screen to see it full size.' : ''}
                  </p>
                </div>

                {/* What class of software this is, before the screens. A
                    customer who pictured something else needs to read that
                    here rather than work it out from three screenshots —
                    and the sentence is composed server-side from strings
                    already on their request, so it can be checked against
                    the rest of the page. */}
                {preview.what_this_is && (
                  <div className="studio-panel studio-whatthisis max-w-3xl mx-auto mb-10 p-6">
                    <p className="studio-kicker mb-3">What you're looking at</p>
                    <p className="text-slate-600 leading-relaxed">{preview.what_this_is}</p>
                  </div>
                )}

                {/* The link comes first, before the customer scrolls into the
                    screens and forgets the page has an address at all. */}
                {resultUrl && (
                  <div className="studio-keepsafe studio-keepsafe--wide mb-12">
                    <div className="studio-linkrow">
                      <code className="studio-link">{resultUrl}</code>
                      <button type="button" className="studio-ghost-btn" onClick={copyLink}>
                        {copied ? 'Copied' : 'Copy link'}
                      </button>
                      {preview.deck_available && (
                        <a className="studio-ghost-btn" href={studioDeckUrl(preview.id)}>
                          Download the deck
                        </a>
                      )}
                    </div>
                    <p className="studio-keepsafe-label mt-3">
                      Bookmark it. Your screens stay at this address — share it with anyone who
                      should see them.
                    </p>
                  </div>
                )}

                {/* The diagnosis that produced everything below it — shown as
                    its own moment, before the tabs, so the reveal reads as
                    "we found this, so we recommend that" rather than a
                    dashboard of unrelated outputs. Absent entirely when the
                    analyze stage's fallback fired instead of a real read. */}
                {preview.business_model && (
                  <div className="studio-panel studio-diagnosis max-w-3xl mx-auto mb-10 p-6 sm:p-7">
                    <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                      <p className="studio-kicker">Our diagnosis</p>
                      <span className="studio-diagnosis-badge">{preview.business_model}</span>
                    </div>
                    {preview.site_research && (
                      <div className="studio-diagnosis-site">
                        <p className="studio-diagnosis-label">
                          Pulled from {preview.site_research.source_url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/.*$/, '')}
                        </p>
                        {preview.site_research.services.length > 0 && (
                          <ul className="studio-diagnosis-pains">
                            {preview.site_research.services.map((s) => (
                              <li key={s}>{s}</li>
                            ))}
                          </ul>
                        )}
                        {(preview.site_research.hours || preview.site_research.tone) && (
                          <p className="studio-diagnosis-site-meta">
                            {[preview.site_research.hours, preview.site_research.tone].filter(Boolean).join(' · ')}
                          </p>
                        )}
                      </div>
                    )}
                    {preview.target_customer_profile && (
                      <p className="text-slate-600 leading-relaxed mb-4">{preview.target_customer_profile}</p>
                    )}
                    {preview.pain_points.length > 0 && (
                      <div className="studio-diagnosis-block">
                        <p className="studio-diagnosis-label">What we found</p>
                        <ul className="studio-diagnosis-pains">
                          {preview.pain_points.map((p) => (
                            <li key={p}>{p}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {preview.growth_opportunity && (
                      <div className="studio-diagnosis-block">
                        <p className="studio-diagnosis-label">The opportunity</p>
                        <p className="studio-diagnosis-growth">{preview.growth_opportunity}</p>
                      </div>
                    )}
                    <p className="studio-diagnosis-handoff">
                      Here's what we recommend, because of what we found.
                    </p>
                  </div>
                )}

                {/* One tab per thing this run actually produced — a run that
                    skipped the technical plan or named no AI employees never
                    shows an empty tab, since RESULT_TABS filters on that. */}
                {visibleTabs.length > 1 && (
                  <div className="studio-tabs" role="tablist" aria-label="Result sections">
                    {visibleTabs.map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        role="tab"
                        aria-selected={activeTab === tab.id}
                        className={`studio-tab${activeTab === tab.id ? ' studio-tab--active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
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
                        {preview.deck_available && (
                          <a className="studio-ghost-btn" href={studioDeckUrl(preview.id)}>
                            Download the deck
                          </a>
                        )}
                      </div>
                    </div>
                    <TechnicalCinematic preview={preview} />
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
        </div>
      </main>

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

      <SiteFooter />
    </div>
  );
}
