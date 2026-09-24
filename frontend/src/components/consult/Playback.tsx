/**
 * "Here's what we heard." The last moment to correct anything for free.
 *
 * This used to be a chat: the consultant played the brief back in a
 * paragraph, and a wrong figure had to be typed out as a correction in
 * conversation. Now every figure sits on its own and can be changed where it
 * stands — the edit rewrites the sentence it was read from, so the diagnosis
 * reads the corrected answer, not the old one plus a note.
 *
 * Their own idea is shown as one explanation to test. Showing it as the plan
 * would be agreeing with them before we had checked.
 */
import { useState } from 'react';

import type { CaseFigure, CaseFile } from '../../api/consultant';

function FigureCell({ f, onEdit }: { f: CaseFigure; onEdit: (f: CaseFigure, next: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(f.token);
  return (
    <div className="flex min-h-[112px] flex-col justify-center border-t border-[var(--cx-line)] py-4 pr-4">
      {editing ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim() && draft.trim() !== f.token) onEdit(f, draft.trim());
            setEditing(false);
          }}
        >
          <label className="cx-small cx-muted" htmlFor={`fig-${f.source}-${f.value}`}>
            Correct "{f.token}"
          </label>
          <input
            id={`fig-${f.source}-${f.value}`}
            className="cx-input h-11"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setEditing(false);
            }}
          />
          <div className="flex gap-3">
            <button type="submit" className="cx-btn cx-btn--blue cx-btn--sm">Save</button>
            <button type="button" className="cx-link cx-small" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <b className="block cx-display text-[30px] leading-none">{f.value}</b>
            <span className="cx-muted mt-2 block text-[15.5px]">{f.label}</span>
          </div>
          <button
            type="button"
            className="cx-link cx-small"
            onClick={() => {
              setDraft(f.token);
              setEditing(true);
            }}
            aria-label={`Edit ${f.value} ${f.label}`}
          >
            edit
          </button>
        </div>
      )}
    </div>
  );
}

export default function Playback({
  file,
  loading,
  businessName,
  fallbackAnswers,
  mainProblem,
  onEditFigure,
  correction,
  onCorrection,
  onStart,
  onBack,
  submitting,
  error,
}: {
  file: CaseFile | null;
  loading: boolean;
  businessName: string;
  fallbackAnswers: { question: string; answer: string }[];
  mainProblem: string;
  onEditFigure: (f: CaseFigure, next: string) => void;
  correction: string;
  onCorrection: (v: string) => void;
  onStart: () => void;
  onBack: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const figures = file?.figures ?? [];
  const summary = file?.summary?.trim();
  const words = file?.their_words?.trim() || mainProblem.trim();
  const fix = file?.their_fix;
  const count = figures.length;
  const countWord = ['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight'][count] ?? String(count);

  return (
    <section className="pt-10">
      <h1 className="cx-h1">Here's what we heard.</h1>
      <p className="cx-lead mt-5">Correct anything now. The diagnosis uses only what's on this screen.</p>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_0.95fr]">
        <div className="cx-card p-8 sm:p-10">
          <p className="cx-small font-semibold text-[var(--cx-txt3)]">{businessName || 'Your business'}</p>
          {loading ? (
            <div className="mt-4 space-y-3" aria-label="Reading your answers">
              <div className="cx-skel w-11/12" />
              <div className="cx-skel w-10/12" />
              <div className="cx-skel w-8/12" />
            </div>
          ) : summary ? (
            <p className="mt-3 text-[clamp(18px,1.45vw,21px)] leading-[1.6]">{summary}</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {fallbackAnswers.map((a) => (
                <li key={a.question} className="text-[16px]">
                  <span className="cx-muted">{a.question}</span> {a.answer}
                </li>
              ))}
            </ul>
          )}

          {words ? (
            <>
              <p className="cx-small mt-8 font-semibold text-[var(--cx-txt3)]">What's going on, in your words</p>
              <blockquote className="mt-3 border-l-2 border-[var(--cx-line)] pl-5 text-[clamp(17px,1.35vw,20px)] italic leading-[1.6] text-[var(--cx-txt2)]">
                "{words}"
              </blockquote>
            </>
          ) : null}

          {fix ? (
            <div className="cx-tint mt-8 p-6">
              <p className="text-[19px] font-semibold">You think {fix} would fix it.</p>
              <p className="cx-muted mt-2">
                That's one explanation. We'll test it against the others and tell you honestly how it holds up.
              </p>
            </div>
          ) : null}
        </div>

        <div className="cx-card p-8 sm:p-10">
          <p className="cx-small font-semibold text-[var(--cx-txt3)]">
            {loading ? 'Your figures' : count ? `Your figures, ${count === 1 ? 'just the one' : `all ${countWord} of them`}` : 'Your figures'}
          </p>
          {loading ? (
            <div className="mt-6 grid grid-cols-2 gap-6">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="space-y-3">
                  <div className="cx-skel h-7 w-20" />
                  <div className="cx-skel w-28" />
                </div>
              ))}
            </div>
          ) : count ? (
            <div className="mt-3 grid grid-cols-2 gap-x-6">
              {figures.map((f) => (
                <FigureCell key={`${f.source}-${f.value}-${f.token}`} f={f} onEdit={onEditFigure} />
              ))}
            </div>
          ) : (
            <p className="cx-muted mt-4">
              You haven't given us figures yet. That's fine — the diagnosis will say plainly what it couldn't check.
            </p>
          )}
          <label htmlFor="cx-correct" className="sr-only">Anything we got wrong?</label>
          <input
            id="cx-correct"
            className="cx-input mt-6 w-full"
            value={correction}
            onChange={(e) => onCorrection(e.target.value)}
            placeholder="Anything we got wrong? e.g. We have three instructors, not two"
            maxLength={600}
          />
        </div>
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-6 border-t border-[var(--cx-line)] pt-8">
        <p className="cx-muted max-w-[62ch] text-[17px] leading-relaxed">
          <b className="text-[var(--cx-txt)]">Next, we diagnose.</b> We write out every plausible
          explanation, test each one against your figures, and have two reviewers try to knock the
          strongest one down. About two minutes, and you can watch it happen.
        </p>
        <div className="flex flex-wrap items-center gap-5">
          <button type="button" className="cx-link" onClick={onBack} disabled={submitting}>Back to the questions</button>
          <button type="button" className="cx-btn cx-btn--blue" onClick={onStart} disabled={submitting}>
            {submitting ? 'Starting…' : 'Start the diagnosis'}
          </button>
        </div>
      </div>
      {error ? <p className="cx-error mt-4 text-right" role="alert">{error}</p> : null}
    </section>
  );
}
