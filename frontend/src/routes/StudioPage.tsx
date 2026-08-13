import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

interface FieldErrors {
  business_name?: string;
  business_description?: string;
  email?: string;
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
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  const dialogRef = useRef<HTMLDialogElement>(null);
  const elapsed = useElapsed(act === 'building', startedAt);

  const resultUrl = routeId != null ? `${window.location.origin}${studioResultPath(routeId)}` : null;

  const showResult = useCallback(async (id: number) => {
    try {
      const data = await getStudioPreview(id);
      setPreview(data);
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

  const validate = (): boolean => {
    const next: FieldErrors = {};
    if (form.business_name.trim().length < 2) next.business_name = 'Give your business its real name.';
    if (form.business_description.trim().length < 30) {
      next.business_description = 'A couple of sentences — what you do, for whom, and what eats your day.';
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) next.email = 'A real address, so we can reach you about it.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    if (!validate() || submitting) return;
    setSubmitting(true);
    try {
      const { id } = await createStudioRequest({
        business_name: form.business_name.trim(),
        business_description: form.business_description.trim(),
        email: form.email.trim(),
        industry: form.industry.trim() || undefined,
        main_problem: form.main_problem.trim() || undefined,
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
                    <div className="space-y-5">
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

                      <div className="grid sm:grid-cols-2 gap-5">
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
                      </div>

                      {submitError && (
                        <p className="studio-error-text" role="alert">
                          {submitError}
                        </p>
                      )}

                      <button className="studio-cta" type="submit" disabled={submitting}>
                        {submitting ? 'Opening the studio…' : 'Design my software'}
                      </button>
                      <p className="studio-hint text-center">
                        Free. No call, no deck — you watch it get made.
                      </p>
                    </div>
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

                {screens.length === 0 ? (
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
                )}

                {preview.ai_features.length > 0 && (
                  <div className="mt-16">
                    <h2 className="studio-display text-xl font-bold text-off-white mb-4">
                      The AI employees inside it
                    </h2>
                    {/* Cards, not chips: these descriptions are a sentence or
                        two of real reasoning, and a pill full of prose reads
                        like a bug. */}
                    <div className="studio-aicards">
                      {preview.ai_features.map((f) => (
                        <article className="studio-aicard" key={f.id}>
                          <h3>{f.name}</h3>
                          <p>{f.description}</p>
                        </article>
                      ))}
                    </div>
                  </div>
                )}

                {preview.preview_features.length > 0 && (
                  <div className="mt-14">
                    <h2 className="studio-display text-xl font-bold text-off-white mb-4">
                      What it does for you
                    </h2>
                    <ul className="studio-featurelist">
                      {preview.preview_features.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {preview.mvp_blueprint && (
                  <details className="studio-details-block mt-14">
                    <summary>
                      <span className="studio-display text-xl font-bold text-off-white">
                        Read the blueprint
                      </span>
                      <span className="studio-hint">
                        What we'd build first, in plain words
                      </span>
                    </summary>
                    <BlueprintProse text={preview.mvp_blueprint} />
                  </details>
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
