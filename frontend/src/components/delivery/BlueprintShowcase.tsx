import { useRef, type ReactElement } from 'react';
import { motion, useInView } from 'framer-motion';
import type { MarkdownSection } from '../../utils/parseMarkdownSections';
import { extractListItems, extractScalar } from '../../utils/parseMarkdownSections';

const ease = [0.22, 1, 0.36, 1] as const;

interface Props {
  sections: MarkdownSection[];
  conceptName?: string | null;
  fitScore?: number | null;
}

/* ─── Icon set (inline SVG, no deps) ─────────────────────────── */
const icons: Record<string, ReactElement> = {
  features: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  journey: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  ),
  risk: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
    </svg>
  ),
  arrow: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
    </svg>
  ),
};

/* ─── Main component ──────────────────────────────────────────── */
export default function BlueprintShowcase({ sections, conceptName, fitScore }: Props) {
  const summaries = sections.filter((s) => s.kind === 'summary' || s.kind === 'general');
  const journeys = sections.filter((s) => s.kind === 'journey');
  const features = sections.filter((s) => s.kind === 'features');
  const timelines = sections.filter((s) => s.kind === 'timeline');
  const questions = sections.filter((s) => s.kind === 'questions');
  const concepts = sections.filter((s) => s.kind === 'concept');

  const scoreSection = sections.find((s) => s.kind === 'score');
  const displayScore = fitScore ?? (scoreSection ? parseInt(extractScalar(scoreSection.body), 10) : null);
  const displayConcept = conceptName ?? concepts[0]?.body.replace(/\*\*/g, '').trim();

  const used = new Set(
    [...summaries, ...journeys, ...features, ...timelines, ...questions, ...concepts,
      ...(scoreSection ? [scoreSection] : [])].map((s) => s.title)
  );
  const rest = sections.filter((s) => !used.has(s.title));

  /* All features items flattened for the film strip */
  const allFeatureItems = features.flatMap((s) => {
    const items = extractListItems(s.body);
    return items.length ? items : [s.body.replace(/\*\*/g, '').trim()];
  });

  /* Summaries prose */
  const narratives = [...summaries, ...rest].slice(0, 6);

  return (
    <div className="blueprint-cinematic space-y-0">

      {/* ── 1. OPENING CHAPTER ─────────────────────────────────── */}
      <ChapterOpener score={displayScore} concept={displayConcept} timelines={timelines} />

      {/* ── 2. NARRATIVE FLOW ──────────────────────────────────── */}
      {narratives.length > 0 && (
        <NarrativeFlow sections={narratives} />
      )}

      {/* ── 3. FEATURES FILM STRIP ─────────────────────────────── */}
      {allFeatureItems.length > 0 && (
        <FilmStrip items={allFeatureItems} />
      )}

      {/* ── 4. JOURNEYS TIMELINE ───────────────────────────────── */}
      {journeys.length > 0 && (
        <JourneyTimeline sections={journeys} />
      )}

      {/* ── 5. RISKS / QUESTIONS ───────────────────────────────── */}
      {questions.length > 0 && (
        <RiskStrip sections={questions} />
      )}
    </div>
  );
}

/* ─── Chapter Opener ─────────────────────────────────────────── */
function ChapterOpener({
  score,
  concept,
  timelines,
}: {
  score: number | null;
  concept?: string;
  timelines: MarkdownSection[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '-80px' });

  const timelineVals = timelines
    .map((s) => ({ label: shortLabel(s.title), val: extractScalar(s.body) }))
    .filter((t) => t.val);

  return (
    <div
      ref={ref}
      className="rounded-3xl overflow-hidden bg-slate-950 relative mb-8"
      style={{ minHeight: 340 }}
    >
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-indigo-600/20 blur-3xl" />
        <div className="absolute -bottom-16 -left-16 w-72 h-72 rounded-full bg-violet-600/15 blur-3xl" />
      </div>

      <div className="relative z-10 px-8 py-12 sm:px-12 sm:py-14 flex flex-col gap-8">
        {/* Eyebrow */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, ease }}
        >
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            Strategic Blueprint
          </span>
        </motion.div>

        {/* Concept + Score row */}
        <div className="flex flex-col sm:flex-row sm:items-end gap-6">
          {concept && (
            <motion.h2
              initial={{ opacity: 0, x: -28 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 0.1, duration: 0.7, ease }}
              className="flex-1 text-3xl sm:text-4xl lg:text-5xl font-black text-white leading-tight tracking-tight"
            >
              {concept}
            </motion.h2>
          )}

          {score != null && !Number.isNaN(score) && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={inView ? { opacity: 1, scale: 1 } : {}}
              transition={{ delay: 0.25, duration: 0.6, ease }}
              className="flex-shrink-0 flex flex-col items-center gap-2"
            >
              <ScoreRing score={score} />
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Business fit
              </p>
            </motion.div>
          )}
        </div>

        {/* Timeline pills */}
        {timelineVals.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.35, duration: 0.55, ease }}
            className="flex flex-wrap gap-3"
          >
            {timelineVals.map((t) => (
              <div
                key={t.label}
                className="flex items-center gap-2.5 rounded-2xl bg-white/8 border border-white/10 px-4 py-2.5"
              >
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {t.label}
                </span>
                <span className="text-sm font-bold text-white">{t.val}</span>
              </div>
            ))}
          </motion.div>
        )}
      </div>
    </div>
  );
}

/* ─── Score ring ─────────────────────────────────────────────── */
function ScoreRing({ score }: { score: number }) {
  const r = 38;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  return (
    <div className="relative w-24 h-24 flex items-center justify-center">
      <svg className="absolute inset-0 -rotate-90" width="96" height="96" viewBox="0 0 96 96">
        <circle cx="48" cy="48" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
        <motion.circle
          cx="48" cy="48" r={r}
          fill="none"
          stroke="url(#scoreGrad)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ - dash }}
          transition={{ delay: 0.4, duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
        />
        <defs>
          <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
      </svg>
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.7, duration: 0.4 }}
        className="text-2xl font-black text-white"
      >
        {score}
        <span className="text-sm font-bold text-slate-400">%</span>
      </motion.span>
    </div>
  );
}

/* ─── Narrative Flow ─────────────────────────────────────────── */
function NarrativeFlow({ sections }: { sections: MarkdownSection[] }) {
  return (
    <div className="grid sm:grid-cols-2 gap-4 mb-8">
      {sections.map((s, i) => {
        const items = extractListItems(s.body);
        const isWide = i === 0 || (i % 5 === 0);
        const isDark = i % 4 === 1;
        return (
          <motion.div
            key={s.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ delay: i * 0.07, duration: 0.55, ease }}
            className={`${isWide ? 'sm:col-span-2' : ''} ${
              isDark
                ? 'rounded-3xl bg-slate-900 p-7 sm:p-9'
                : 'rounded-3xl border border-slate-200/60 bg-white p-7 sm:p-9 shadow-sm'
            }`}
          >
            <p className={`text-[10px] font-bold uppercase tracking-[0.2em] mb-3 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>
              {s.title}
            </p>
            {items.length > 0 ? (
              <ul className="space-y-2">
                {items.slice(0, 5).map((item, j) => (
                  <motion.li
                    key={j}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.07 + j * 0.05, duration: 0.4, ease }}
                    className={`flex items-start gap-3 text-sm leading-snug ${isDark ? 'text-slate-300' : 'text-slate-700'}`}
                  >
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
                    <span className="line-clamp-2">{cleanText(item.length > 100 ? item.slice(0, 100) + '…' : item)}</span>
                  </motion.li>
                ))}
              </ul>
            ) : (
              <p className={`text-sm leading-relaxed line-clamp-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                {cleanText(s.body).slice(0, 200)}{cleanText(s.body).length > 200 ? '…' : ''}
              </p>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

/* ─── Features Film Strip ─────────────────────────────────────── */
function FilmStrip({ items }: { items: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '-60px' });

  return (
    <div className="mb-8" ref={ref}>
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.5, ease }}
        className="mb-5 flex items-center gap-4"
      >
        <div className="flex items-center gap-2.5 text-indigo-600">
          {icons.features}
          <span className="text-[11px] font-bold uppercase tracking-[0.2em]">Features & scope</span>
        </div>
        <div className="flex-1 h-px bg-slate-200" />
        <span className="text-xs text-slate-400">{items.length} included</span>
      </motion.div>

      {/* Horizontal scroll strip */}
      <div className="overflow-x-auto pb-4 -mx-1">
        <div className="flex gap-3 w-max px-1">
          {items.map((item, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: 20 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: i * 0.04, duration: 0.45, ease }}
              className="group flex-shrink-0 w-52 rounded-2xl border border-slate-200/60 bg-white p-5 shadow-sm hover:border-indigo-200 hover:shadow-md transition-all duration-300 cursor-default"
            >
              <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center mb-3 group-hover:bg-indigo-100 transition-colors">
                <span className="text-xs font-bold text-indigo-600">{i + 1}</span>
              </div>
              <p className="text-sm font-semibold text-slate-900 leading-snug">{item}</p>
            </motion.div>
          ))}

          {/* End marker */}
          <div className="flex-shrink-0 w-16 rounded-2xl border border-dashed border-slate-200 bg-slate-50 flex items-center justify-center">
            <span className="text-slate-300 text-xl">→</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Journey Timeline ───────────────────────────────────────── */
function JourneyTimeline({ sections }: { sections: MarkdownSection[] }) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-4 mb-6">
        <div className="flex items-center gap-2.5 text-violet-600">
          {icons.journey}
          <span className="text-[11px] font-bold uppercase tracking-[0.2em]">User journeys</span>
        </div>
        <div className="flex-1 h-px bg-slate-200" />
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        {sections.map((s, i) => {
          const steps = extractListItems(s.body);
          return (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * 0.1, duration: 0.6, ease }}
              className="rounded-3xl border border-slate-200/60 bg-white overflow-hidden shadow-sm"
            >
              {/* Header */}
              <div className={`px-6 py-5 ${i % 2 === 0 ? 'bg-indigo-600' : 'bg-violet-600'}`}>
                <p className="text-[10px] font-bold uppercase tracking-wider text-white/60 mb-1">
                  Journey {i + 1}
                </p>
                <h3 className="text-base font-bold text-white leading-snug">{s.title}</h3>
              </div>

              {/* Steps */}
              <div className="px-6 py-5 relative">
                {/* Vertical line */}
                {steps.length > 1 && (
                  <div className="absolute left-[2.35rem] top-5 bottom-5 w-px bg-slate-100" />
                )}
                <ol className="space-y-4 relative">
                  {steps.map((step, j) => (
                    <motion.li
                      key={j}
                      initial={{ opacity: 0, x: -16 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: i * 0.1 + j * 0.07, duration: 0.4, ease }}
                      className="flex items-start gap-4"
                    >
                      <span
                        className={`shrink-0 w-7 h-7 rounded-xl flex items-center justify-center text-xs font-bold relative z-10 ${
                          i % 2 === 0
                            ? 'bg-indigo-600 text-white'
                            : 'bg-violet-600 text-white'
                        }`}
                      >
                        {j + 1}
                      </span>
                      <p className="text-sm text-slate-700 leading-relaxed pt-0.5">{step}</p>
                    </motion.li>
                  ))}
                  {steps.length === 0 && (
                    <p className="text-sm text-slate-600 leading-relaxed">{cleanText(s.body)}</p>
                  )}
                </ol>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Risk strip ─────────────────────────────────────────────── */
function RiskStrip({ sections }: { sections: MarkdownSection[] }) {
  const allItems = sections.flatMap((s) => {
    const items = extractListItems(s.body);
    return items.length ? items : [cleanText(s.body)];
  }).slice(0, 8);

  if (!allItems.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.55, ease }}
      className="rounded-3xl border border-amber-200/60 bg-gradient-to-br from-amber-50/80 to-orange-50/40 p-7 sm:p-9 mb-4"
    >
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center text-amber-600">
          {icons.risk}
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-700">
            Assumptions & open questions
          </p>
          <p className="text-xs text-amber-700/60 mt-0.5">To clarify before building</p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {allItems.map((item, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.06, duration: 0.4, ease }}
            className="flex items-start gap-3 rounded-2xl bg-white/70 border border-amber-100 px-4 py-3.5"
          >
            <span className="shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400" />
            <p className="text-sm text-amber-900/90 leading-relaxed">{cleanText(item)}</p>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ─── Helpers ─────────────────────────────────────────────────── */
function shortLabel(title: string) {
  return title.replace(/\*\*/g, '').replace(/\(0-100\)/i, '').replace(/suggested\s+/i, '').slice(0, 26);
}

function cleanText(body: string) {
  return body
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/^[-=]{3,}\s*$/gm, '')
    .trim();
}
