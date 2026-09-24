/**
 * Watching it think: the diagnosis, marked up as it happens.
 *
 * The explanations are laid out like a page on a consultant's desk. The one
 * that holds up best is circled; the ones their own figures rule out are
 * struck through; the two reviewers argue in the margin, in handwriting,
 * against whichever one leads. The wait is the proof: they watch their own
 * idea being tested like any other, and see it survive or not.
 *
 * Purely presentational — it reads the narrated trail and decides nothing.
 */
import { motion, useReducedMotion } from 'framer-motion';

import type { ThinkingStep } from '../../api/consultant';
import { derivePasses, stageOf, type BoardHypothesis, type BoardPass } from '../../utils/runBoard';
import { shortName } from '../../utils/names';

const DECIDING = new Set(['consulting', 'answering', 'awaiting_approval']);

function Circle({ reduce }: { reduce: boolean }) {
  return (
    <svg className="cx-circle" viewBox="0 0 1000 200" preserveAspectRatio="none" aria-hidden="true">
      <motion.path
        d="M140 22 C 380 2, 820 6, 968 34 C 1012 48, 1004 150, 950 176 C 760 206, 260 204, 40 182 C -6 170, -8 70, 52 38 C 90 18, 150 14, 196 12"
        fill="none"
        stroke="var(--cx-blue)"
        strokeWidth={2.6}
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        initial={reduce ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1.1, ease: 'easeInOut' }}
      />
    </svg>
  );
}

function Strike({ children, reduce }: { children: React.ReactNode; reduce: boolean }) {
  return (
    <span className="cx-strike">
      {children}
      <svg viewBox="0 0 400 14" preserveAspectRatio="none" aria-hidden="true">
        <motion.path
          d="M2 9 C 60 3, 120 12, 190 6 S 320 3, 398 8"
          fill="none"
          stroke="var(--cx-hot)"
          strokeWidth={2.2}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          initial={reduce ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.7 }}
        />
      </svg>
    </span>
  );
}

function Verdict({ h }: { h: BoardHypothesis }) {
  if (!h.verdict) return null;
  if (h.verdict === 'supported') return <span className="cx-chip cx-chip--green">Supported</span>;
  if (h.verdict === 'refuted') {
    return h.theirs
      ? <span className="cx-chip cx-chip--amber">Doesn't hold up</span>
      : <span className="cx-chip cx-chip--dim">Ruled out</span>;
  }
  return <span className="cx-chip cx-chip--dim">Couldn't check with your figures</span>;
}

function Card({ h, n, testing, reduce, delay }: {
  h: BoardHypothesis;
  n: number;
  testing: boolean;
  reduce: boolean;
  delay: number;
}) {
  const out = h.verdict === 'refuted';
  return (
    <motion.article
      className={`cx-card cx-hyp${h.leading ? ' lead' : ''}${out ? ' out' : ''}`}
      initial={reduce ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: reduce ? 0 : delay }}
    >
      {h.leading ? (
        <>
          <Circle reduce={reduce} />
          <motion.span
            className="cx-note-tag cx-hand"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.9 }}
          >
            holds up best
          </motion.span>
        </>
      ) : null}
      <span className="cx-hyp-n">{n}</span>
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap gap-2">
          {h.theirs ? <span className="cx-chip cx-chip--blue">What you told us</span> : null}
          {h.area ? <span className="cx-chip cx-chip--dim">{h.area.charAt(0).toUpperCase() + h.area.slice(1)}</span> : null}
          {h.software === false ? <span className="cx-chip cx-chip--dim">Software can't fix this</span> : null}
        </div>
        <p className="cx-hyp-s">{out ? <Strike reduce={reduce}>{h.text}</Strike> : h.text}</p>
      </div>
      <div className="min-w-0">
        {h.verdict ? (
          <motion.div initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-3">
            <Verdict h={h} />
            {h.because ? (
              <p className="cx-muted text-[15.5px] leading-relaxed">
                {h.because}
                {h.because.length >= 399 ? "…" : ""}
              </p>
            ) : null}
          </motion.div>
        ) : testing ? (
          <div className="space-y-3 pt-1" aria-label="Being tested">
            <div className="cx-skel w-24" />
            <div className="cx-skel w-11/12" />
            <div className="cx-skel w-8/12" />
          </div>
        ) : null}
      </div>
    </motion.article>
  );
}

const ANGLES = [
  { angle: 'alternative' as const, ask: 'Does anything else explain it?' },
  { angle: 'confirmation' as const, ask: 'Are we just agreeing with you?' },
];

function Margin({ pass, leadN, reduce }: { pass: BoardPass; leadN: number; reduce: boolean }) {
  if (!pass.challenging && pass.reviewers.length === 0) return null;
  return (
    <aside className="cx-margin space-y-10" aria-live="polite">
      <p className="text-[16px] font-semibold text-[var(--cx-red)]">
        Two reviewers, arguing against number {leadN}
      </p>
      {ANGLES.map(({ angle, ask }) => {
        const r = pass.reviewers.find((x) => x.angle === angle);
        return (
          <div key={angle}>
            <h4>{ask}</h4>
            {r ? (
              <motion.div initial={reduce ? false : { opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}>
                <p className="cx-hand">{r.because}</p>
                <p className={`cx-hand mt-2 ${r.kills ? 'text-[var(--cx-red)] text-[30px]' : 'cx-held'}`}>
                  {r.kills ? 'found a hole ✗' : 'held ✓'}
                </p>
              </motion.div>
            ) : (
              <p className="cx-hand text-[var(--cx-red)] opacity-70">
                reading<span className="cx-typing"><i /><i /><i /></span>
              </p>
            )}
          </div>
        );
      })}
    </aside>
  );
}

export default function Thinking({ steps, stage, elapsed, businessName }: {
  steps: ThinkingStep[];
  stage: string | null;
  elapsed: string;
  businessName: string;
}) {
  const reduce = Boolean(useReducedMotion());
  const passes = derivePasses(steps);
  const pass = passes[passes.length - 1];
  const reading = steps.filter((s) => s.kind === 'reading');
  const hasFile = reading.length > 0 || stage === 'reading';

  const rail = [
    ...(hasFile ? ['Reading your file'] : []),
    'Writing explanations',
    'Testing against your figures',
    'Trying to break it',
    'Deciding what to do',
  ];
  let at: number;
  if (stage === 'reading') at = 0;
  else if (stage && DECIDING.has(stage)) at = rail.length - 1;
  else if (!pass) at = hasFile ? 1 : 0;
  else {
    const s = stageOf(pass);
    const base = hasFile ? 1 : 0;
    at = base + (s === 'considering' ? 0 : s === 'testing' ? 1 : s === 'challenging' ? 2 : 3);
  }

  const phrase = (() => {
    const name = rail[at];
    if (name === 'Reading your file') return `Reading ${reading[reading.length - 1]?.text ?? 'your file'} — every figure checked against its cell.`;
    if (name === 'Writing explanations') {
      return pass ? `${pass.hypotheses.length} possible explanations, including yours.` : 'Reading what you told us and writing out every explanation that fits it.';
    }
    if (name === 'Testing against your figures') return 'Testing each explanation against your own figures.';
    if (name === 'Trying to break it') return 'Two reviewers are trying to break the strongest explanation.';
    return 'Deciding what to do about it — including whether software is the answer at all.';
  })();

  const lead = pass?.hypotheses.findIndex((h) => h.leading) ?? -1;
  const earlierKilled = passes.length > 1;
  const short = shortName(businessName);

  return (
    <section className="pt-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <h1 className="cx-h2">Working out what's going on at {short}</h1>
          <p className="mt-4 flex items-center gap-3 text-[18px] cx-muted">
            <span className={`cx-live${rail[at] === 'Trying to break it' ? '' : ' calm'}`} aria-hidden="true" />
            <span aria-live="polite">{phrase}</span>
          </p>
        </div>
        <div className="text-right">
          <p className="cx-display text-[44px]">{elapsed}</p>
          <p className="cx-faint text-[15px]">usually about two minutes</p>
        </div>
      </div>

      <ol className="cx-rail mt-8" style={{ gridTemplateColumns: `repeat(${rail.length}, minmax(0, 1fr))` }}>
        {rail.map((name, i) => (
          <li key={name} className={i < at ? 'done' : i === at ? `now${name === 'Trying to break it' ? ' attack' : ''}` : ''}>
            <b />
            <span>{name}</span>
          </li>
        ))}
      </ol>

      {earlierKilled ? (
        <p className="cx-tint mt-8 px-6 py-4 text-[16px]">
          <b>Our first reading didn't survive the reviewers.</b>{' '}
          <span className="cx-muted">We're thinking again with their objections — this is the second pass.</span>
        </p>
      ) : null}

      <div className="mt-10 grid gap-10 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-6">
          {pass ? (
            pass.hypotheses.map((h, i) => (
              <Card key={`${passes.length}-${i}`} h={h} n={i + 1} testing={pass.testing} reduce={reduce} delay={i * 0.08} />
            ))
          ) : (
            [0, 1, 2].map((i) => (
              <div key={i} className="cx-card cx-hyp" aria-hidden="true">
                <span className="cx-hyp-n">{i + 1}</span>
                <div className="space-y-3 pt-2">
                  <div className="cx-skel w-11/12" />
                  <div className="cx-skel w-7/12" />
                </div>
                <div />
              </div>
            ))
          )}
        </div>
        {pass ? <Margin pass={pass} leadN={lead + 1} reduce={reduce} /> : null}
      </div>

      <div className="mt-12 flex flex-wrap justify-between gap-4 border-t border-[var(--cx-line)] pt-6 text-[15.5px]">
        <p className="cx-muted"><b className="text-[var(--cx-txt)]">Nothing is built from this.</b> Next, you read the answer and decide.</p>
        <p className="cx-faint">Every figure on this screen is one you gave us.</p>
      </div>
    </section>
  );
}
