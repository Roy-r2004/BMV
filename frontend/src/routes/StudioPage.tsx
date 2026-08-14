import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import '../styles/studio.css';

// The orchestrator's real stages, told as studio work. `at` mirrors the
// progress_pct each stage emits so the timeline advances from the poll's
// pct even if a stage name ever changes server-side.
const STAGES = [
  { at: 10, name: 'Reading your business', sub: 'What you do, who you serve, where it hurts' },
  { at: 25, name: 'Consulting', sub: 'Deciding what your AI employees should take over' },
  { at: 35, name: 'Planning the product', sub: 'Which screens your software actually needs' },
  { at: 45, name: 'Writing the blueprint', sub: 'The MVP, in plain words' },
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

type ResultTab = 'screens' | 'blueprint' | 'technical' | 'team';

// Each tab knows its own availability rule, so a run that skipped a stage
// (no technical plan yet, no AI employees named) never shows an empty tab —
// the tab bar itself is evidence of what this run actually produced.
const RESULT_TABS: { id: ResultTab; label: string; available: (p: StudioPreview) => boolean }[] = [
  { id: 'screens', label: 'Screens', available: () => true },
  { id: 'blueprint', label: 'Blueprint', available: (p) => Boolean(p.mvp_blueprint) },
  { id: 'technical', label: 'Technical plan', available: (p) => Boolean(p.technical_plan) },
  { id: 'team', label: 'AI team', available: (p) => p.ai_features.length > 0 },
];

interface FieldErrors {
  business_name?: string;
  business_description?: string;
  email?: string;
  what_you_like?: string;
}

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
      <h2 className="studio-display text-2xl sm:text-3xl font-bold text-off-white mb-4">{title}</h2>
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

function TechnicalCinematic({ preview }: { preview: StudioPreview }) {
  const md = preview.technical_plan ?? '';
  const sections = useMemo(() => splitH2Sections(md), [md]);
  const arch = findSection(sections, /architecture/);
  const blocks = findSection(sections, /building blocks|components/);
  const aiWork = findSection(sections, /employees work|how the ai/);
  const implPhases = findSection(sections, /implementation/);
  const security = findSection(sections, /security|data/);

  if (!arch && !blocks && !aiWork) return <BlueprintProse text={md} />;

  const archText = arch ? stripInlineMarkdown(arch.body.replace(/\n+/g, ' ')) : '';
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
                  <p className="mt-6 text-slate-400">Opening your studio run…</p>
                </div>
              </motion.section>
            )}

            {act === 'intake' && (
              <motion.section key="intake" {...fade} transition={{ duration: 0.45 }}>
                <div className="grid lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-16 items-start">
                  <div className="pt-4">
                    <p className="studio-kicker mb-5">The Demo</p>
                    <h1 className="studio-display text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.05] text-off-white">
                      See your software before anyone writes a line of it.
                    </h1>
                    <p className="mt-6 text-slate-400 text-lg max-w-xl leading-relaxed">
                      Describe your business. The studio designs the product you'd actually run it
                      with — real screens, your services, your numbers — and hands them to you in
                      about three minutes.
                    </p>
                    <ul className="mt-8 space-y-3 text-sm text-slate-300">
                      <li className="flex gap-3">
                        <span className="text-logo-cyan font-semibold">3</span>
                        production-grade screens of bespoke software, designed for your trade
                      </li>
                      <li className="flex gap-3">
                        <span className="text-logo-cyan font-semibold">2×</span>
                        every screen passes an aesthetic judge and a structural inspection before you see it
                      </li>
                      <li className="flex gap-3">
                        <span className="text-logo-cyan font-semibold">~3m</span>
                        from this form to your screens, watchable live
                      </li>
                    </ul>
                  </div>

                  <motion.form
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
                              <input
                                id="st-name"
                                value={form.business_name}
                                onChange={(e) => setForm({ ...form, business_name: e.target.value })}
                                placeholder="Beacon Physiotherapy"
                                autoComplete="organization"
                              />
                              {errors.business_name && <p className="studio-error-text">{errors.business_name}</p>}
                            </div>
                            <div className="studio-field">
                              <label htmlFor="st-industry">
                                Industry <span className="text-slate-500 font-normal">(optional)</span>
                              </label>
                              <input
                                id="st-industry"
                                value={form.industry}
                                onChange={(e) => setForm({ ...form, industry: e.target.value })}
                                placeholder="Physiotherapy clinic"
                              />
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
                                <p className="studio-hint">
                                  The more specific you are, the more the screens feel like yours.
                                </p>
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
                          </>
                        )}

                        {step === 2 && (
                          <>
                            <div className="studio-field">
                              <label htmlFor="st-refurl">
                                A tool or site you like <span className="text-slate-500 font-normal">(optional)</span>
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
                        </button>
                      ) : (
                        <button className="studio-cta studio-stepnav-cta" type="submit" disabled={submitting}>
                          {submitting ? 'Opening the studio…' : 'Design my software'}
                        </button>
                      )}
                    </div>
                    <p className="studio-hint text-center mt-4">
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
                  <h1 className="studio-display text-3xl sm:text-4xl font-bold text-off-white">
                    {buildingName} is in the studio
                  </h1>
                  <p className="mt-3 text-slate-400">
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
                        className="mt-4 text-sm text-slate-400"
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
                  <h1 className="studio-display text-4xl sm:text-5xl font-bold text-off-white">
                    {preview.concept_name || `${preview.business_name} OS`}
                  </h1>
                  <p className="mt-4 text-slate-400 text-lg">
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
                    <p className="text-slate-300 leading-relaxed">{preview.what_this_is}</p>
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
                    <p className="text-slate-300 font-semibold">This run's screens aren't on file.</p>
                    <p className="mt-3 text-slate-400 text-sm">
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

                {activeTab === 'blueprint' && preview.mvp_blueprint && (
                  <div className="studio-tabpanel">
                    <BlueprintCinematic preview={preview} />
                  </div>
                )}

                {activeTab === 'technical' && preview.technical_plan && (
                  <div className="studio-tabpanel">
                    <TechnicalCinematic preview={preview} />
                  </div>
                )}

                {/* The empty-state panel above already offers its own way
                    forward — a second CTA under it just reads as clutter. */}
                {screens.length > 0 && (
                  <div className="mt-16 flex flex-wrap items-center gap-4">
                    <button type="button" className="studio-cta max-w-xs" onClick={startOver}>
                      Design another
                    </button>
                    <p className="text-sm text-slate-400">
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
                  <h1 className="studio-display text-3xl font-bold text-off-white">
                    That run didn't make it
                  </h1>
                  <p className="mt-4 text-slate-400">
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
                  <h1 className="studio-display text-3xl font-bold text-off-white">
                    We couldn't find that run
                  </h1>
                  <p className="mt-4 text-slate-400">
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
