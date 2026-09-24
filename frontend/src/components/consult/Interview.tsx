/**
 * The conversation, one question at a time, with the case file filling in
 * beside it.
 *
 * The list version put four questions on screen at once, and a list reads as
 * a form: people skim it, answer the easy ones and leave. One question, asked
 * after the last answer, reads as someone listening. What they already said
 * stays above it, and any answer can be changed.
 *
 * The case file on the right is built only from their answers, checked on the
 * server against the words each figure was quoted from, and their week is
 * drawn the moment enough of it is known. It is the first thing on the page
 * that shows we are keeping track.
 */
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

import type { CaseFile, DiscoveryQuestion } from '../../api/consultant';
import WeekGrid from './WeekGrid';
import { fmt, weekHeadline } from '../../utils/week';

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xlsm,.pdf';

function exampleOf(placeholder: string): string {
  if (!placeholder) return 'Type your answer';
  return /^(e\.g\.|eg|for example)/i.test(placeholder) ? placeholder : `e.g. ${placeholder}`;
}

export function CaseFilePanel({ file, loading, theirFix }: {
  file: CaseFile | null;
  loading: boolean;
  theirFix?: string | null;
}) {
  const figures = file?.figures ?? [];
  const picture = file?.capacity ?? null;
  const fix = theirFix ?? file?.their_fix ?? null;
  return (
    <aside className="cx-card p-7 lg:sticky lg:top-6" aria-live="polite">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="cx-h3">Your business, so far</h2>
        {loading ? <span className="cx-faint cx-small">updating<span className="cx-typing"><i /><i /><i /></span></span> : null}
      </div>
      <p className="cx-faint mt-1 text-[15px]">Built only from what you've told us.</p>

      {picture ? (
        <div className="mt-5 border-t border-[var(--cx-line)] pt-5">
          <p className="cx-small font-semibold text-[var(--cx-txt2)]">Your week, as you've described it</p>
          <div className="mt-4">
            <WeekGrid picture={picture} mini />
          </div>
          <p className="mt-4 text-[15.5px]">
            <b className="text-[var(--cx-blue)]">{weekHeadline(picture)}.</b>{' '}
            {picture.full?.length ? <span className="cx-muted">The slots you said sell out are dark.</span> : null}
          </p>
        </div>
      ) : null}

      <div className="mt-5 border-t border-[var(--cx-line)] pt-5">
        <p className="cx-small font-semibold text-[var(--cx-txt2)]">Your figures</p>
        {figures.length === 0 ? (
          <p className="cx-faint mt-3 text-[15px]">
            {loading ? 'Reading your answers…' : 'Nothing yet. Your figures appear here as you give them.'}
          </p>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-4">
            <AnimatePresence initial={false}>
              {figures.map((f) => (
                <motion.div
                  key={`${f.source}-${f.value}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <b className="block cx-display text-[26px]">{f.value}</b>
                  <span className="cx-muted text-[14.5px] leading-snug block mt-1">{f.label}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {fix ? (
        <div className="mt-5 border-t border-[var(--cx-line)] pt-5">
          <p className="cx-small font-semibold text-[var(--cx-txt2)]">What you think would fix it</p>
          <p className="mt-2 text-[19px] italic">"{fix.charAt(0).toUpperCase() + fix.slice(1)}."</p>
          <span className="cx-chip cx-chip--blue mt-3">We'll test this, not assume it</span>
        </div>
      ) : null}
    </aside>
  );
}

export default function Interview({
  questions,
  answers,
  committed,
  onAnswer,
  onCommit,
  onReopen,
  loading,
  done,
  closing,
  estimatedTotal,
  caseFile,
  caseLoading,
  files,
  onAddFiles,
  onRemoveFile,
  onFinish,
  finishError,
}: {
  questions: DiscoveryQuestion[];
  answers: Record<string, string>;
  committed: string[];
  onAnswer: (id: string, value: string) => void;
  onCommit: (id: string) => void;
  onReopen: (id: string) => void;
  loading: boolean;
  done: boolean;
  closing: string;
  estimatedTotal: number;
  caseFile: CaseFile | null;
  caseLoading: boolean;
  files: File[];
  onAddFiles: (f: File[]) => void;
  onRemoveFile: (i: number) => void;
  onFinish: () => void;
  finishError?: string | null;
}) {
  const reduce = useReducedMotion();
  const current = questions.find((q) => !committed.includes(q.id)) ?? null;
  const history = questions.filter((q) => committed.includes(q.id));
  const index = current ? questions.indexOf(current) + 1 : questions.length;
  const total = Math.max(estimatedTotal, index);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, [current?.id]);

  const commit = () => {
    if (current) onCommit(current.id);
  };

  return (
    <div className="grid gap-10 pt-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.85fr)] lg:gap-16">
      <section className="min-w-0">
        {history.length > 0 ? (
          <ol className="space-y-4">
            {history.map((q) => {
              const a = (answers[q.id] ?? '').trim();
              return (
                <li key={q.id} className="group">
                  <p className="font-semibold text-[16.5px] text-[var(--cx-txt2)]">{q.label}</p>
                  <div className="mt-1 flex items-start gap-3 border-l-2 border-[var(--cx-line)] pl-4">
                    <p className={`text-[16.5px] ${a ? '' : 'cx-faint italic'}`}>{a || "You didn't know — left blank."}</p>
                    <button type="button" className="cx-link cx-small opacity-70 group-hover:opacity-100" onClick={() => onReopen(q.id)}>
                      change
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
        ) : null}

        <AnimatePresence mode="wait">
          {current ? (
            <motion.div
              key={current.id}
              className="mt-10"
              initial={reduce ? false : { opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, y: -10 }}
              transition={{ duration: 0.35 }}
            >
              <div className="flex items-center gap-4">
                <div className="h-[3px] w-[220px] max-w-[40%] rounded bg-[rgba(37,99,235,0.14)]">
                  <div className="h-full rounded bg-[var(--cx-blue)] transition-all duration-500" style={{ width: `${Math.min(100, (index / total) * 100)}%` }} />
                </div>
                <span className="cx-faint text-[15px]">Question {index} of about {total}</span>
              </div>
              <h1
                className="cx-h2 mt-6"
                // A long question set at headline size ran to seven lines;
                // past a sentence it steps down so it still reads as one.
                style={current.label.length > 70 ? { fontSize: "clamp(26px, 2.5vw, 38px)", maxWidth: "30ch" } : { maxWidth: "22ch" }}
              >
                {current.label}
              </h1>
              {current.why ? <p className="cx-lead mt-5 max-w-[52ch]">{current.why}</p> : null}

              <label htmlFor={`cx-q-${current.id}`} className="sr-only">{current.label}</label>
              <textarea
                id={`cx-q-${current.id}`}
                ref={inputRef}
                className="cx-field mt-8"
                rows={2}
                value={answers[current.id] ?? ''}
                onChange={(e) => onAnswer(current.id, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if ((answers[current.id] ?? '').trim()) commit();
                  }
                }}
                placeholder={exampleOf(current.placeholder)}
              />
              <div className="mt-6 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  className="cx-btn cx-btn--blue"
                  onClick={commit}
                  disabled={!(answers[current.id] ?? '').trim()}
                >
                  Answer
                </button>
                <button
                  type="button"
                  className="cx-btn cx-btn--ghost"
                  onClick={() => {
                    onAnswer(current.id, '');
                    commit();
                  }}
                >
                  I don't know
                </button>
                <span className="cx-faint">A blank beats a guess. We never fill one in.</span>
              </div>
            </motion.div>
          ) : loading ? (
            <motion.div key="loading" className="mt-12" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <p className="cx-lead">
                {questions.length === 0 ? 'Reading what you wrote' : 'Reading your answers'}
                <span className="cx-typing"><i /><i /><i /></span>
              </p>
            </motion.div>
          ) : done ? (
            <motion.div key="done" className="mt-12" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <h1 className="cx-h2">That's everything we need.</h1>
              <p className="cx-lead mt-4 max-w-[52ch]">
                {closing || 'Next, we play it back so you can correct anything before the diagnosis starts.'}
              </p>
              {finishError ? <p className="cx-error mt-4" role="alert">{finishError}</p> : null}
              <button type="button" className="cx-btn cx-btn--blue mt-8" onClick={onFinish}>
                See what we heard
              </button>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div
          className={`mt-10 flex flex-wrap items-center gap-4 rounded-2xl p-2 transition-colors ${dragging ? 'bg-[var(--cx-blue-soft)]' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            onAddFiles(Array.from(e.dataTransfer.files ?? []));
          }}
        >
          <button
            type="button"
            className="grid h-12 w-12 place-items-center rounded-xl border border-dashed border-[rgba(37,99,235,0.45)] text-[var(--cx-blue)]"
            onClick={() => fileRef.current?.click()}
            aria-label="Add a file"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0-6 6m6-6 6 6" />
            </svg>
          </button>
          <p className="cx-muted text-[16px]">
            Have a booking export or a sales sheet? Drop it in and we'll read the numbers ourselves.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              onAddFiles(Array.from(e.target.files ?? []));
              e.target.value = '';
            }}
          />
          {files.length > 0 ? (
            <div className="flex w-full flex-wrap gap-2 pl-16">
              {files.map((f, i) => (
                <span key={`${f.name}-${i}`} className="cx-chip cx-chip--blue gap-2">
                  {f.name} <span className="cx-faint">({fmt(Math.ceil(f.size / 1024))} KB)</span>
                  <button type="button" onClick={() => onRemoveFile(i)} aria-label={`Remove ${f.name}`} className="text-[var(--cx-txt2)]">×</button>
                </span>
              ))}
              <span className="cx-faint cx-small self-center">Read before the diagnosis starts.</span>
            </div>
          ) : null}
        </div>
      </section>

      <CaseFilePanel file={caseFile} loading={caseLoading} />
    </div>
  );
}
