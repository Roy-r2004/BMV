/**
 * The running step, given the whole screen.
 *
 * This used to be a boxed card in the middle of a scrolling page: a narrow
 * column of log lines that grew off the bottom, so the newest reasoning
 * landed where nobody was looking, and a verdict appeared nowhere near the
 * explanation it belonged to. The wait is the most persuasive thing this
 * product does — explanations forming, being tested against the client's own
 * figures, and being attacked — and it was the least visible.
 *
 * Now it fills the viewport as a board. The explanations are cards; a
 * verdict lands ON its card; the reviewers sit beside them; the whole thing
 * fits on one screen and animates in place instead of scrolling away. While
 * a build is running instead, the same frame carries the three documents
 * being written, lighting up as each finishes.
 *
 * Purely presentational: it reads the trail and the progress it is handed and
 * decides nothing.
 */
import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

import type { ThinkingStep } from '../../api/consultant';
import {
  derivePasses,
  stageOf,
  type BoardHypothesis,
  type BoardPass,
  type BoardReviewer,
  type Verdict,
} from '../../utils/runBoard';

export type RunPhase = 'diagnosing' | 'building';

// `at` mirrors the progress_pct each stage emits, so the rail advances from
// the poll's own number even if a stage is renamed server-side.
const DIAGNOSIS_STAGES = [
  { at: 5, name: 'Reading what you told us', sub: 'Your situation, your figures, your website' },
  { at: 16, name: 'Forming explanations', sub: 'Several possible causes, not one story' },
  { at: 22, name: 'Trying to break them', sub: 'Your own numbers, then two skeptical reviewers' },
  { at: 25, name: 'Deciding what to do', sub: 'Including whether software is the answer' },
] as const;
/** Where the diagnosis half ends and the client's decision begins. */
const GATE_PCT = 30;

const BUILD_STAGES = [
  { at: 30, name: 'Getting ready', sub: 'Carrying your approved diagnosis into the build' },
  { at: 35, name: 'Planning the product', sub: 'Which screens your software actually needs' },
  { at: 42, name: 'Decomposing the business', sub: 'Module by module, each with its own spec' },
  { at: 50, name: 'Writing the blueprint', sub: 'The modules, the money, the build order' },
  { at: 60, name: 'Writing your playbook', sub: 'Every step you take, who does it, and when' },
  { at: 62, name: 'Art direction', sub: 'Layout, palette and hierarchy — set per screen' },
  { at: 70, name: 'Rendering your screens', sub: 'Drawn in parallel, inspected, re-rolled if flawed' },
] as const;

// What the client is actually waiting for. Showing the three documents by
// name is the answer to "what will I get?" — the rail names the work, this
// names the result.
const DELIVERABLES = [
  { name: 'Blueprint', sub: 'The modules, the money, the build order', at: 50, doneAt: 56 },
  { name: 'Technical plan', sub: 'How it is actually built', at: 56, doneAt: 60 },
  { name: 'Operations manual', sub: 'Every step, who does it, and when', at: 60, doneAt: 62 },
  { name: 'Product screens', sub: 'Drawn, inspected, re-rolled if flawed', at: 62, doneAt: 100 },
] as const;

const DIAGNOSIS_WHISPERS = [
  'Nothing gets built until you have read this and agreed with it…',
  'Every figure we use is one you gave us. We never invent one…',
  'If two reviewers can knock a conclusion down, it does not reach you as fact…',
  'If the honest answer is not software, we will say so…',
];
const BUILD_WHISPERS = [
  'Every screen is inspected by two independent checks before it ships…',
  'A screen that fails inspection gets one re-roll — quality over speed…',
  'Typesetting your real numbers, not placeholders…',
  'Your navigation, your services, your customers — nothing generic…',
];

type State = 'done' | 'active' | 'pending';
const stateAt = (pct: number, at: number, doneAt: number): State =>
  pct >= doneAt ? 'done' : pct >= at ? 'active' : 'pending';

const CHECK = 'M4.5 12.75l6 6 9-13.5';

function Check({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} className={className} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={CHECK} />
    </svg>
  );
}

const CARD =
  'rounded-2xl border bg-white/90 backdrop-blur shadow-[0_12px_30px_-18px_rgba(15,23,42,0.28)]';

// ── the four steps of the diagnosis ─────────────────────────────────────────

function Stepper({ pct }: { pct: number }) {
  return (
    <ol className="grid grid-cols-2 gap-x-4 gap-y-3 lg:grid-cols-4">
      {DIAGNOSIS_STAGES.map((s, i) => {
        const next = DIAGNOSIS_STAGES[i + 1]?.at ?? GATE_PCT;
        const state = stateAt(pct, s.at, next);
        const dot =
          state === 'done'
            ? 'bg-blue-600 text-white'
            : state === 'active'
              ? 'border-2 border-blue-500 bg-white text-blue-600'
              : 'border border-slate-300 bg-white text-slate-400';
        return (
          <li
            key={s.name}
            className={`flex items-start gap-3 transition-opacity duration-500 ${state === 'pending' ? 'opacity-45' : ''}`}
          >
            <span
              className={`relative grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold transition-colors duration-500 ${dot}`}
              aria-hidden="true"
            >
              {state === 'done' ? <Check className="h-3.5 w-3.5" /> : i + 1}
              {state === 'active' ? (
                <span className="absolute -inset-1 animate-ping rounded-full border border-blue-400/60" />
              ) : null}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-navy">{s.name}</p>
              <p className="text-xs leading-snug text-slate-500">{s.sub}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ── the explanations ────────────────────────────────────────────────────────

const VERDICT_STYLE: Record<Verdict, { label: string; tone: string }> = {
  supported: { label: 'Supported', tone: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  refuted: { label: 'Ruled out', tone: 'border-slate-200 bg-slate-100 text-slate-600' },
  untestable: { label: "Couldn't verify", tone: 'border-amber-200 bg-amber-50 text-amber-700' },
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const v = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.untestable;
  // `w-fit self-start`: the first version was a bare flex child, and flex
  // children stretch to the height of their row — so `rounded-full` on a box
  // as tall as the whole verdict rendered a giant yellow oval down the side
  // of every result.
  return (
    <span
      className={`inline-flex w-fit self-start items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${v.tone}`}
    >
      {v.label}
    </span>
  );
}

function Tag({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {children}
    </span>
  );
}

function Skeleton() {
  return (
    <div className="mt-2 space-y-2" aria-hidden="true">
      <div className="h-2.5 w-11/12 animate-pulse rounded bg-slate-200/80" />
      <div className="h-2.5 w-8/12 animate-pulse rounded bg-slate-200/80" />
    </div>
  );
}

function ExplanationCard({
  h,
  index,
  testing,
  reduce,
}: {
  h: BoardHypothesis;
  index: number;
  testing: boolean;
  reduce: boolean;
}) {
  return (
    <motion.article
      layout={!reduce}
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: reduce ? 0 : index * 0.09, ease: [0.3, 0.8, 0.3, 1] }}
      className={`relative flex flex-col p-5 transition-[box-shadow,border-color] duration-500 ${CARD} ${
        h.leading
          ? 'border-blue-400 ring-4 ring-blue-100 shadow-[0_22px_48px_-20px_rgba(37,99,235,0.55)]'
          : 'border-slate-200'
      }`}
    >
      {h.leading ? (
        <motion.span
          initial={reduce ? false : { opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="absolute -top-3 right-5 rounded-full bg-blue-600 px-3 py-1 text-xs font-semibold text-white shadow-md"
        >
          Holds up best
        </motion.span>
      ) : null}

      <div className="flex items-start gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-500">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {h.area ? <Tag tone="bg-slate-100 capitalize text-slate-600">{h.area}</Tag> : null}
            {h.software === false ? (
              <Tag tone="border border-slate-300 bg-white text-slate-600">Software can't fix this</Tag>
            ) : null}
            {h.theirs ? <Tag tone="bg-blue-50 text-blue-700">What you told us</Tag> : null}
          </div>
          <h3 className="mt-2 text-[1.02rem] font-semibold leading-snug text-navy sm:text-lg">{h.text}</h3>
        </div>
      </div>

      <div className="mt-4 border-t border-slate-100 pt-4">
        {h.verdict ? (
          <motion.div
            key="verdict"
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: reduce ? 0 : 0.1 + index * 0.1 }}
            className="flex flex-col gap-2"
          >
            <VerdictBadge verdict={h.verdict} />
            {h.because ? <p className="text-sm leading-relaxed text-slate-600">{h.because}</p> : null}
            {h.cites.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {h.cites.map((c) => (
                  <span key={c} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
                    {c}
                  </span>
                ))}
              </div>
            ) : null}
          </motion.div>
        ) : testing ? (
          <div>
            <p className="text-sm font-medium text-blue-600">Testing against your figures…</p>
            <Skeleton />
          </div>
        ) : (
          <p className="text-sm text-slate-400">Waiting its turn</p>
        )}
      </div>
    </motion.article>
  );
}

// ── the reviewers ───────────────────────────────────────────────────────────

const ANGLE_TITLE: Record<BoardReviewer['angle'], string> = {
  alternative: 'Does something else explain it?',
  confirmation: 'Are we just agreeing with you?',
};

function Dots() {
  return (
    <span className="inline-flex gap-1" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-500"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function ReviewerCard({
  angle,
  result,
  arguing,
}: {
  angle: BoardReviewer['angle'];
  result?: BoardReviewer;
  arguing: boolean;
}) {
  return (
    <div className={`p-4 ${CARD} border-slate-200`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-navy">{ANGLE_TITLE[angle]}</p>
        {result ? (
          <span
            className={`inline-flex w-fit self-start items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${
              result.kills
                ? 'border-rose-200 bg-rose-50 text-rose-700'
                : 'border-emerald-200 bg-emerald-50 text-emerald-700'
            }`}
          >
            {result.kills ? 'Found a hole' : 'Held'}
          </span>
        ) : null}
      </div>
      {result ? (
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{result.because}</p>
      ) : arguing ? (
        <p className="mt-2 flex items-center gap-2 text-sm text-blue-600">
          Arguing against it <Dots />
        </p>
      ) : (
        <p className="mt-2 text-sm text-slate-400">Waiting for a conclusion to test</p>
      )}
    </div>
  );
}

const SECTION_LABEL = 'text-xs font-semibold uppercase tracking-[0.16em] text-slate-500';

function settledLine(pass: BoardPass, isFirst: boolean): { text: string; tone: string } | null {
  if (!pass.settled) return null;
  if (pass.settled === 'survived')
    return {
      text: 'Neither reviewer could bring it down. It goes to the decision next.',
      tone: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    };
  if (pass.settled === 'killed')
    return {
      text: isFirst
        ? 'A reviewer found a hole in it — so we are taking a second look.'
        : 'A reviewer found a hole in it. We will show you exactly where.',
      tone: 'border-amber-200 bg-amber-50 text-amber-900',
    };
  return {
    text: 'The review could not be run, so nothing has tested this but your figures.',
    tone: 'border-slate-200 bg-slate-50 text-slate-700',
  };
}

// ── the board ───────────────────────────────────────────────────────────────

function BoardSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]" aria-hidden="true">
      <div className="grid gap-4 md:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`p-5 ${CARD} border-slate-200`}>
            <div className="h-3 w-16 animate-pulse rounded bg-slate-200/80" />
            <div className="mt-4 h-4 w-11/12 animate-pulse rounded bg-slate-200/80" />
            <div className="mt-2 h-4 w-8/12 animate-pulse rounded bg-slate-200/80" />
            <div className="mt-6 h-3 w-10/12 animate-pulse rounded bg-slate-100" />
          </div>
        ))}
      </div>
      <div className="space-y-4">
        <div className={`h-32 animate-pulse ${CARD} border-slate-200`} />
        <div className={`h-24 animate-pulse ${CARD} border-slate-200`} />
        <div className={`h-24 animate-pulse ${CARD} border-slate-200`} />
      </div>
    </div>
  );
}

function DiagnosisBoard({ steps, reduce }: { steps: ThinkingStep[]; reduce: boolean }) {
  const passes = useMemo(() => derivePasses(steps), [steps]);
  const pass = passes[passes.length - 1];
  if (!pass) return <BoardSkeleton />;

  const earlier = passes.slice(0, -1);
  const stage = stageOf(pass);
  const lead = pass.hypotheses.find((h) => h.leading);
  const settled = settledLine(pass, passes.length === 1);

  return (
    <div>
      {pass.retry ? (
        <motion.div
          initial={reduce ? false : { opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <span className="font-semibold">Second look.</span> The first reading was knocked down by a
          reviewer, so we thought again with their objections in front of us.
        </motion.div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section aria-label="Explanations">
          <p className={SECTION_LABEL}>
            {pass.hypotheses.length} possible explanations
            {stage === 'considering' ? ' — forming' : ''}
          </p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {pass.hypotheses.map((h, i) => (
              <ExplanationCard
                key={h.text}
                h={h}
                index={i}
                testing={pass.testing && !h.verdict}
                reduce={reduce}
              />
            ))}
          </div>
        </section>

        <aside className="space-y-4" aria-label="Reviewers">
          <div>
            <p className={SECTION_LABEL}>The one that holds up best</p>
            <div className="mt-3">
              {lead ? (
                <motion.div
                  key={lead.text}
                  initial={reduce ? false : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5 }}
                  className="rounded-2xl border border-blue-200 bg-blue-50/80 p-5"
                >
                  <p className="text-lg font-semibold leading-snug text-navy">{lead.text}</p>
                </motion.div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-sm text-slate-400">
                  Once every explanation has been tested, the strongest one is picked out here.
                </div>
              )}
            </div>
          </div>

          <div>
            <p className={SECTION_LABEL}>Two reviewers try to break it</p>
            <div className="mt-3 space-y-3">
              {(['alternative', 'confirmation'] as const).map((angle) => (
                <ReviewerCard
                  key={angle}
                  angle={angle}
                  result={pass.reviewers.find((r) => r.angle === angle)}
                  arguing={pass.challenging && !pass.settled}
                />
              ))}
            </div>
          </div>

          {settled ? (
            <motion.p
              key={pass.settled}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`rounded-xl border px-4 py-3 text-sm font-medium ${settled.tone}`}
            >
              {settled.text}
            </motion.p>
          ) : null}

          {earlier.length > 0 ? (
            <details className={`p-4 ${CARD} border-slate-200`}>
              <summary className="cursor-pointer text-sm font-semibold text-slate-700">
                The first reading, and why it fell
              </summary>
              <div className="mt-3 space-y-3">
                {earlier.map((p, i) => {
                  const first = p.hypotheses.find((h) => h.leading);
                  return (
                    <div key={i} className="text-sm">
                      {first ? <p className="font-medium text-navy">{first.text}</p> : null}
                      {p.reviewers
                        .filter((r) => r.kills)
                        .map((r) => (
                          <p key={r.angle} className="mt-1 text-slate-600">
                            {r.because}
                          </p>
                        ))}
                    </div>
                  );
                })}
              </div>
            </details>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

// ── the build ───────────────────────────────────────────────────────────────

function BuildBoard({ pct }: { pct: number }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="studio-panel h-fit p-6">
        {BUILD_STAGES.map((s, i) => {
          const next = BUILD_STAGES[i + 1]?.at ?? 100;
          return (
            <div className="studio-stage-row" data-state={stateAt(pct, s.at, next)} key={s.name}>
              <span className="studio-stage-dot" aria-hidden="true" />
              <div>
                <p className="studio-stage-name">{s.name}</p>
                <p className="studio-stage-sub">{s.sub}</p>
              </div>
            </div>
          );
        })}
      </aside>

      <section className="space-y-6">
        <div>
          <p className={SECTION_LABEL}>What you're getting</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {DELIVERABLES.map((d) => {
              const state = stateAt(pct, d.at, d.doneAt);
              const tone =
                state === 'done'
                  ? 'border-emerald-200 bg-emerald-50/70'
                  : state === 'active'
                    ? 'border-blue-300 bg-white shadow-[0_18px_40px_-20px_rgba(37,99,235,0.55)]'
                    : 'border-slate-200 bg-white/60 opacity-70';
              return (
                <div key={d.name} className={`rounded-2xl border p-5 transition-all duration-500 ${tone}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-navy">{d.name}</p>
                    {state === 'done' ? (
                      <Check className="h-4 w-4 text-emerald-600" />
                    ) : state === 'active' ? (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{d.sub}</p>
                  <p
                    className={`mt-3 text-xs font-semibold uppercase tracking-[0.12em] ${
                      state === 'done' ? 'text-emerald-700' : state === 'active' ? 'text-blue-600' : 'text-slate-400'
                    }`}
                  >
                    {state === 'done' ? 'Ready' : state === 'active' ? 'Writing…' : 'Queued'}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="studio-panel p-6 sm:p-8">
          <div className="studio-easel" role="img" aria-label="Your screens being drafted">
            <span className="studio-easel-wire" style={{ left: '6%', top: '9%', width: '26%', height: '82%' }} />
            <span className="studio-easel-wire" style={{ left: '36%', top: '9%', width: '58%', height: '30%' }} />
            <span className="studio-easel-wire" style={{ left: '36%', top: '45%', width: '28%', height: '46%' }} />
            <span className="studio-easel-wire" style={{ left: '68%', top: '45%', width: '26%', height: '46%' }} />
          </div>
        </div>
      </section>
    </div>
  );
}

// ── the stage ───────────────────────────────────────────────────────────────

export default function RunStage({
  phase,
  businessName,
  label,
  detail,
  pct,
  elapsed,
  steps,
  resultUrl,
  copied,
  onCopy,
}: {
  phase: RunPhase;
  businessName: string;
  label: string | null;
  detail: string | null;
  pct: number;
  elapsed: string;
  steps: ThinkingStep[];
  resultUrl: string | null;
  copied: boolean;
  onCopy: () => void;
}) {
  const reduce = Boolean(useReducedMotion());
  const diagnosing = phase === 'diagnosing';

  const whispers = diagnosing ? DIAGNOSIS_WHISPERS : BUILD_WHISPERS;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 6000);
    return () => clearInterval(t);
  }, []);
  const whisper = whispers[tick % whispers.length];

  return (
    <div className="mx-auto flex min-h-[calc(100vh-12rem)] w-full flex-col">
      <header className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <p className="studio-kicker">{diagnosing ? 'Diagnosing' : 'Building'}</p>
          <span className="studio-elapsed">{elapsed}</span>
        </div>
        <h1 className="studio-display mt-3 text-3xl font-bold leading-tight text-navy sm:text-4xl lg:text-5xl">
          {diagnosing ? `Working out what's going on at ${businessName}` : `${businessName} is in the studio`}
        </h1>
        <p className="mt-3 flex items-center gap-2.5 text-slate-600 lg:text-lg">
          <span className="relative flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-70" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500" />
          </span>
          <span>
            {label ?? 'Warming up…'}
            {detail ? <span className="text-slate-500"> — {detail}</span> : null}
          </span>
        </p>
        <div className="studio-meter mt-6">
          <div className="studio-meter-fill" style={{ width: `${Math.max(4, pct)}%` }} />
        </div>
        {diagnosing ? (
          <div className="mt-6">
            <Stepper pct={pct} />
          </div>
        ) : null}
      </header>

      <div className="flex-1">
        {diagnosing ? <DiagnosisBoard steps={steps} reduce={reduce} /> : <BuildBoard pct={pct} />}
      </div>

      <footer className="mt-10 grid gap-5 border-t border-slate-200 pt-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <AnimatePresence mode="wait">
            <motion.p
              key={whisper}
              className="text-sm text-slate-600"
              initial={reduce ? undefined : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduce ? undefined : { opacity: 0 }}
              transition={{ duration: 0.5 }}
            >
              {whisper}
            </motion.p>
          </AnimatePresence>
          {diagnosing ? (
            <p className="mt-2 text-sm text-slate-500">
              Next you'll read the decision and choose whether to build. The Blueprint, Technical Plan
              and Operations Manual are only made if you press Build.
            </p>
          ) : null}
        </div>
        {resultUrl ? (
          <div className="studio-keepsafe max-w-xl">
            <p className="studio-keepsafe-label">
              This page is your run. Close it, come back, open it on your phone — the address doesn't
              change.
            </p>
            <div className="studio-linkrow">
              <code className="studio-link">{resultUrl}</code>
              <button type="button" className="studio-ghost-btn" onClick={onCopy}>
                {copied ? 'Copied' : 'Copy link'}
              </button>
            </div>
          </div>
        ) : null}
      </footer>
    </div>
  );
}
