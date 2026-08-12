import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import {
  createStudioRequest,
  getStudioPreview,
  getStudioProgress,
  consultantAssetUrl,
  isAtCapacity,
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

type Act = 'intake' | 'building' | 'reveal' | 'failed';

interface FieldErrors {
  business_name?: string;
  business_description?: string;
  email?: string;
}

const RESUME_KEY = 'bmv_studio_request_id';

function useElapsed(running: boolean, startedAt: number | null) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  if (!startedAt) return '0:00';
  const s = Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export default function StudioPage() {
  const reduceMotion = useReducedMotion();
  const [act, setAct] = useState<Act>('intake');
  const [requestId, setRequestId] = useState<number | null>(null);
  const [progress, setProgress] = useState<StudioProgress | null>(null);
  const [preview, setPreview] = useState<StudioPreview | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [failureDetail, setFailureDetail] = useState<string | null>(null);
  const [whisper, setWhisper] = useState(0);
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);

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

  // A refresh mid-generation resumes the run instead of losing it.
  useEffect(() => {
    // Dev-only design hook: /studio?preview=building renders the theater
    // without a live run, so the act can be looked at without spending a
    // generation. Compiled out of production builds.
    if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('preview') === 'building') {
      setStartedAt(Date.now() - 74_000);
      setProgress({
        stage: 'images', label: 'Rendering your product screenshots...', pct: 70,
        detail: 'screen 2 of 3', is_generating: true, is_failed: false, updated_at: null,
      });
      setAct('building');
      return;
    }
    const stored = sessionStorage.getItem(RESUME_KEY);
    if (stored) {
      setRequestId(Number(stored));
      setStartedAt(Date.now());
      setAct('building');
    }
  }, []);

  // Rotate the rendering-stage whispers.
  useEffect(() => {
    if (act !== 'building') return;
    const t = setInterval(() => setWhisper((w) => (w + 1) % RENDER_WHISPERS.length), 5200);
    return () => clearInterval(t);
  }, [act]);

  const finishRun = useCallback(async (id: number, failed: boolean, detail?: string | null) => {
    sessionStorage.removeItem(RESUME_KEY);
    if (failed) {
      setFailureDetail(detail ?? null);
      setAct('failed');
      return;
    }
    try {
      const data = await getStudioPreview(id);
      setPreview(data);
      setAct('reveal');
    } catch {
      setFailureDetail('The screens were generated but could not be fetched — your email will still receive them.');
      setAct('failed');
    }
  }, []);

  // Poll progress while building.
  useEffect(() => {
    if (act !== 'building' || requestId == null) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const p = await getStudioProgress(requestId);
        if (cancelled) return;
        setProgress(p);
        if (p.is_failed) await finishRun(requestId, true, p.detail);
        else if (!p.is_generating && (p.pct ?? 0) >= 100) await finishRun(requestId, false);
        else if (!p.is_generating && p.stage === 'failed') await finishRun(requestId, true, p.detail);
      } catch {
        // transient poll failure: keep polling, the run continues server-side
      }
    };
    tick();
    const t = setInterval(tick, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [act, requestId, finishRun]);

  const validate = (): boolean => {
    const next: FieldErrors = {};
    if (form.business_name.trim().length < 2) next.business_name = 'Give your business its real name.';
    if (form.business_description.trim().length < 30) {
      next.business_description = 'A couple of sentences — what you do, for whom, and what eats your day.';
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) next.email = 'A real address — the screens land here too.';
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
      setRequestId(id);
      setStartedAt(Date.now());
      setProgress(null);
      setAct('building');
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

  const reset = () => {
    sessionStorage.removeItem(RESUME_KEY);
    setAct('intake');
    setRequestId(null);
    setProgress(null);
    setPreview(null);
    setStartedAt(null);
    setFailureDetail(null);
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

  const screens: StudioScreen[] = preview?.generated_pages.attraction_images ?? [];
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
            {act === 'intake' && (
              <motion.section key="intake" {...fade} transition={{ duration: 0.45 }}>
                <div className="grid lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-16 items-start">
                  <div className="pt-4">
                    <p className="studio-kicker mb-5">The Studio</p>
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
                    {form.business_name.trim() || 'Your business'} is in the studio
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

                    <p className="studio-hint mt-2">
                      Usually under three minutes. Leaving this page won't cancel the run — it will
                      be here when you come back.
                    </p>
                  </div>
                </div>
              </motion.section>
            )}

            {act === 'reveal' && preview && (
              <motion.section key="reveal" {...fade} transition={{ duration: 0.5 }}>
                <div className="max-w-3xl mx-auto text-center mb-12">
                  <p className="studio-kicker mb-4">Fresh from the studio</p>
                  <h1 className="studio-display text-4xl sm:text-5xl font-bold text-off-white">
                    {preview.concept_name || `${preview.business_name} OS`}
                  </h1>
                  <p className="mt-4 text-slate-400 text-lg">
                    Designed for {preview.business_name}. Click any screen to see it full size.
                  </p>
                </div>

                <div className="space-y-10">
                  {screens.map((screen, i) => {
                    const src = consultantAssetUrl(screen.hero_url ?? screen.image_url);
                    const full = consultantAssetUrl(screen.image_url);
                    if (!src || !full) return null;
                    return (
                      <motion.figure
                        key={`${screen.role_id}-${screen.variant}`}
                        className="m-0"
                        initial={reduceMotion ? undefined : { opacity: 0, y: 34 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, delay: reduceMotion ? 0 : 0.15 * i }}
                      >
                        <button
                          type="button"
                          className="studio-shot"
                          onClick={() => openLightbox(full, screen.role_label)}
                          aria-label={`Enlarge ${screen.role_label}`}
                        >
                          <img src={src} alt={`${screen.role_label} screen`} loading={i > 0 ? 'lazy' : 'eager'} />
                        </button>
                        <figcaption className="mt-3 flex items-baseline justify-between gap-4">
                          <span className="font-semibold text-slate-200">{screen.role_label}</span>
                          <a
                            className="text-sm text-logo-cyan hover:underline"
                            href={full}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open full resolution
                          </a>
                        </figcaption>
                      </motion.figure>
                    );
                  })}
                </div>

                {preview.ai_features.length > 0 && (
                  <div className="mt-14">
                    <h2 className="studio-display text-xl font-bold text-off-white mb-4">
                      The AI employees inside it
                    </h2>
                    <div className="flex flex-wrap gap-3">
                      {preview.ai_features.map((f) => (
                        <span className="studio-chip" key={f.id}>
                          <strong>{f.name}</strong> {f.description}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-14 flex flex-wrap items-center gap-4">
                  <button type="button" className="studio-cta max-w-xs" onClick={reset}>
                    Design another
                  </button>
                  <p className="text-sm text-slate-400">
                    A copy of everything is on its way to {form.email.trim() || 'your inbox'}.
                  </p>
                </div>
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
                  <button type="button" className="studio-cta mt-8" onClick={reset}>
                    Try again
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
