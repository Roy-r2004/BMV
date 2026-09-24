/**
 * The honest answer. The screen the whole consultation exists for.
 *
 * It has to land in five seconds and survive a sceptical second read. So the
 * finding is two short lines, their own week is drawn beside it, and the
 * three figures that prove it sit along the bottom next to the choice they
 * now have to make. Everything that got us here is one click below, for the
 * second read.
 *
 * Building is never a dead end: whichever answer we gave, the other path is
 * one click away.
 */
import { useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

import type { StudioDecision, StudioFigure } from '../../api/consultant';
import WeekGrid, { WeekLegend } from './WeekGrid';
import { fmt } from '../../utils/week';

const SCOPES = ['Starter scope', 'Standard scope', 'Full build', 'Not sure yet'];
const TIMELINES = ['ASAP (2–4 weeks)', '1–2 months', '2–3 months', 'Flexible'];

function Emphasised({ text, emphasis }: { text: string; emphasis: string }) {
  if (!emphasis || !text.includes(emphasis)) return <>{text}</>;
  const [a, b] = text.split(emphasis, 2);
  return (
    <>
      {a}
      <b className="font-semibold text-[var(--cx-txt)]">{emphasis}</b>
      {b}
    </>
  );
}

function Modal({ children, onClose, label }: { children: React.ReactNode; onClose: () => void; label: string }) {
  return (
    <div className="cx-modal-back" role="dialog" aria-modal="true" aria-label={label} onClick={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <div className="cx-card cx-modal">{children}</div>
    </div>
  );
}

function Choices({ options, value, onChange, label }: { options: string[]; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="mt-3 flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o} type="button" role="radio" aria-checked={value === o} className={`cx-choice${value === o ? ' on' : ''}`} onClick={() => onChange(o)}>
          {o}
        </button>
      ))}
    </div>
  );
}

export default function Answer({
  decision,
  firstName,
  onBuild,
  onAccept,
  onRevise,
  onUpload,
  busy,
  error,
  evidenceBusy,
  evidenceNote,
  evidenceError,
  figures,
  onDeleteFigure,
}: {
  decision: StudioDecision;
  firstName: string | null;
  onBuild: (scope: { budget_range: string; timeline: string }) => void;
  onAccept: () => void;
  onRevise: (note: string) => void;
  onUpload: (f: File) => void;
  busy: boolean;
  error: string | null;
  evidenceBusy: boolean;
  evidenceNote: string | null;
  evidenceError: string | null;
  /** Figures read out of files they sent, each verified against its cell. */
  figures: StudioFigure[];
  onDeleteFigure: (id: string) => void;
}) {
  const reduce = useReducedMotion();
  const [building, setBuilding] = useState(false);
  const [revising, setRevising] = useState(false);
  const [scope, setScope] = useState(SCOPES[3]);
  const [timeline, setTimeline] = useState(TIMELINES[3]);
  const [note, setNote] = useState('');
  const [showWorking, setShowWorking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const a = decision.answer;
  const d = decision.decision;
  const picture = decision.capacity ?? null;
  const headline = a?.headline || d.central_problem || 'Here is what we found.';
  const turn = a?.turn || '';
  const sub = a?.sub || d.summary || '';
  const move = a?.move ?? null;
  const actionName = a?.action?.name || 'first-weeks plan';
  const builds = decision.builds;

  const band: { value: string; label: string }[] = [];
  if (picture && picture.taken != null) {
    band.push({
      value: `${fmt(picture.taken)} of ${fmt(picture.capacity)}`,
      label: picture.shape === 'total' ? `${picture.unit_plural} used a ${picture.period ?? 'week'}` : `${picture.unit_plural} taken every week`,
    });
  }
  for (const f of a?.figures ?? []) band.push({ value: f.value, label: f.label });

  const enter = (delay: number) =>
    reduce ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay } };

  const diag = decision.diagnosis;
  const unverified = d.unverified ?? [];

  return (
    <section className="pt-8">
      <div className="grid items-start gap-12 xl:grid-cols-[minmax(0,1fr)_minmax(560px,0.95fr)]">
        <div className="min-w-0">
          <motion.p className="cx-faint text-[17px]" {...enter(0)}>
            {firstName ? `${firstName}, here's what we found.` : "Here's what we found."}
          </motion.p>
          <motion.h1 className="cx-h1 mt-5" {...enter(0.08)}>
            {headline}
            {turn ? <span className="block text-[var(--cx-blue)]">{turn}</span> : null}
          </motion.h1>
          {sub ? (
            <motion.p className="cx-lead mt-8 max-w-[44ch]" {...enter(0.2)}>
              <Emphasised text={sub} emphasis={a?.emphasis ?? ''} />
            </motion.p>
          ) : null}
          {decision.revisions ? (
            <p className="cx-faint mt-6 max-w-[60ch] text-[15px]">
              Diagnosed again with what you told us: "{decision.revisions}"
            </p>
          ) : null}
        </div>

        {picture ? (
          <motion.div className="cx-card p-7 sm:p-8" {...enter(0.35)}>
            <WeekLegend picture={picture} />
            <div className="mt-6">
              <WeekGrid picture={picture} />
            </div>
            <p className="cx-faint mt-6 text-[14px]">
              Drawn only from what you told us: {picture.basis.join(', ')}.
            </p>
          </motion.div>
        ) : diag?.leading?.cites?.length ? (
          <motion.div className="cx-card p-8" {...enter(0.35)}>
            <p className="cx-small font-semibold text-[var(--cx-txt3)]">What this rests on — your own figures</p>
            <ul className="mt-4 space-y-4">
              {diag.leading.cites.map((c) => (
                <li key={c.id} className="border-l-2 border-[var(--cx-line)] pl-4 text-[16.5px]">{c.text}</li>
              ))}
            </ul>
          </motion.div>
        ) : null}
      </div>

      <motion.div
        className="mt-16 grid items-end gap-10 border-t border-[var(--cx-line)] pt-8 lg:grid-cols-[repeat(auto-fit,minmax(200px,1fr))]"
        {...enter(0.5)}
      >
        {band.slice(0, 2).map((f) => (
          <div key={f.value + f.label}>
            <b className="block cx-display text-[clamp(30px,2.8vw,42px)]">{f.value}</b>
            <span className="cx-muted mt-2 block text-[15px]">{f.label}</span>
          </div>
        ))}
        {move ? (
          <div>
            <b className="block cx-display text-[clamp(30px,2.8vw,42px)] text-[var(--cx-blue)]">{move.display}</b>
            <span className="cx-muted mt-2 block text-[15px]">{move.label}</span>
            <button type="button" className="cx-link cx-small mt-2" onClick={() => setShowWorking((v) => !v)} aria-expanded={showWorking}>
              {showWorking ? 'Hide the working' : 'How we worked it out'}
            </button>
          </div>
        ) : null}
        <div className="flex flex-col items-start gap-3 lg:items-end">
          {decision.status === 'awaiting_approval' || decision.status === 'advised' ? (
            builds ? (
              <>
                <button type="button" className="cx-btn cx-btn--blue" onClick={() => setBuilding(true)} disabled={busy}>
                  Build the package
                </button>
                <div className="flex flex-wrap gap-5">
                  <button type="button" className="cx-link" onClick={onAccept} disabled={busy}>Just the {actionName} for now</button>
                  <button type="button" className="cx-link" onClick={() => setRevising(true)} disabled={busy}>This isn't right</button>
                </div>
              </>
            ) : (
              <>
                <button type="button" className="cx-btn cx-btn--blue" onClick={onAccept} disabled={busy}>
                  {busy ? 'Starting…' : `Start the ${actionName}`}
                </button>
                <div className="flex flex-wrap gap-5">
                  <button type="button" className="cx-link" onClick={() => setBuilding(true)} disabled={busy}>Build the system too</button>
                  <button type="button" className="cx-link" onClick={() => setRevising(true)} disabled={busy}>This isn't right</button>
                </div>
              </>
            )
          ) : null}
        </div>
      </motion.div>
      {error ? <p className="cx-error mt-4 text-right" role="alert">{error}</p> : null}

      {showWorking && move ? (
        <div className="cx-tint mt-6 p-6">
          <p className="text-[16.5px]"><b>The working:</b> {move.working}.</p>
          {move.proposed.length ? (
            <p className="cx-muted mt-2 text-[15px]">
              {move.proposed.map((p) => `${p.label || 'The proposed figure'} (${fmt(p.value)})`).join(' and ')} {move.proposed.length > 1 ? 'are' : 'is'} our proposal, not your figure. Everything else is yours.
            </p>
          ) : (
            <p className="cx-muted mt-2 text-[15px]">Every term is one of your own figures or a calendar constant.</p>
          )}
        </div>
      ) : null}

      <details className="mt-16 group">
        <summary className="cx-link cursor-pointer list-none text-[16.5px]">
          How we got here: the explanations we tested, what the reviewers said, and what we couldn't check
        </summary>
        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          {diag ? (
            <div className="cx-card p-8">
              <h2 className="cx-h3">The explanations we tested</h2>
              <ul className="mt-5 space-y-5">
                <li>
                  <span className="cx-chip cx-chip--green">Held up</span>
                  <p className="mt-2 font-semibold">{diag.leading.statement}</p>
                  {diag.leading.because ? <p className="cx-muted mt-1 text-[15px]">{diag.leading.because}</p> : null}
                </li>
                {diag.considered.map((c) => (
                  <li key={c.statement}>
                    <span className={`cx-chip ${c.verdict === 'refuted' ? 'cx-chip--dim' : 'cx-chip--amber'}`}>
                      {c.verdict === 'refuted' ? 'Ruled out' : c.verdict === 'supported' ? 'Also supported' : "Couldn't check"}
                    </span>
                    <p className="mt-2">{c.statement}</p>
                    {c.because ? <p className="cx-muted mt-1 text-[15px]">{c.because}</p> : null}
                  </li>
                ))}
              </ul>
              {diag.challenges.length ? (
                <>
                  <h3 className="mt-8 font-semibold">What the two reviewers said</h3>
                  <ul className="mt-3 space-y-3">
                    {diag.challenges.map((c) => (
                      <li key={c.angle} className="text-[15.5px]">
                        <span className={c.kills ? 'text-[var(--cx-red)] font-semibold' : 'text-[var(--cx-green)] font-semibold'}>
                          {c.kills ? 'Found a hole: ' : 'Held: '}
                        </span>
                        {c.because}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}
          <div className="cx-card p-8">
            <h2 className="cx-h3">What we couldn't check</h2>
            {unverified.length ? (
              <ul className="mt-4 space-y-2">
                {unverified.map((u) => (
                  <li key={u} className="text-[15.5px]">• {u}</li>
                ))}
              </ul>
            ) : (
              <p className="cx-muted mt-3">Nothing listed. Confidence: {d.confidence ?? 'medium'}.</p>
            )}
            {d.why_not_the_others ? (
              <>
                <h3 className="mt-6 font-semibold">Why not the other kinds of fix</h3>
                <p className="cx-muted mt-2 text-[15.5px]">{d.why_not_the_others}</p>
              </>
            ) : null}
            <div className="mt-8 border-t border-[var(--cx-line)] pt-6">
              <p className="font-semibold">Have the actual numbers?</p>
              <p className="cx-muted mt-1 text-[15px]">
                Send a booking export or a sales sheet and we'll diagnose again with it. Every figure is checked against its cell.
              </p>
              <input ref={fileRef} type="file" className="hidden" accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onUpload(f);
                  e.target.value = '';
                }} />
              <button type="button" className="cx-btn cx-btn--ghost cx-btn--sm mt-4" disabled={evidenceBusy} onClick={() => fileRef.current?.click()}>
                {evidenceBusy ? 'Reading…' : 'Send a file'}
              </button>
              {figures.length ? (
                <ul className="mt-5 space-y-3">
                  {figures.map((f) => (
                    <li key={f.id} className="flex items-start justify-between gap-4 text-[15px]">
                      <span>
                        <b>{f.value.toLocaleString('en-US')} {f.unit}</b> {f.text}
                        <span className="cx-faint block text-[13px]">{f.source}</span>
                      </span>
                      <button type="button" className="cx-link cx-small" onClick={() => onDeleteFigure(f.id)} disabled={evidenceBusy}>
                        remove
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {evidenceNote ? <p className="cx-muted mt-3 text-[15px]">{evidenceNote}</p> : null}
              {evidenceError ? <p className="cx-error mt-3">{evidenceError}</p> : null}
            </div>
          </div>
        </div>
      </details>

      {building ? (
        <Modal label="Before we build" onClose={() => setBuilding(false)}>
          <h2 className="cx-h3">Before we build</h2>
          <p className="cx-muted mt-2">
            {builds
              ? 'About ten minutes. Everything is built around the answer you just read.'
              : "We still think the fix doesn't need software to start. The package carries out the change; it won't replace it."}
          </p>
          <p className="mt-6 font-semibold">What scope are you thinking?</p>
          <Choices options={SCOPES} value={scope} onChange={setScope} label="Scope" />
          <p className="mt-6 font-semibold">And when?</p>
          <Choices options={TIMELINES} value={timeline} onChange={setTimeline} label="Timeline" />
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <button type="button" className="cx-btn cx-btn--blue" disabled={busy}
              onClick={() => onBuild({ budget_range: scope, timeline })}>
              {busy ? 'Starting…' : 'Start building'}
            </button>
            <button type="button" className="cx-link" onClick={() => setBuilding(false)}>Not yet</button>
          </div>
        </Modal>
      ) : null}

      {revising ? (
        <Modal label="What did we get wrong?" onClose={() => setRevising(false)}>
          <h2 className="cx-h3">What did we get wrong?</h2>
          <p className="cx-muted mt-2">
            Tell us in a sentence or two. We'll diagnose again with it, and you'll watch it happen.
          </p>
          <textarea className="cx-textarea mt-5" rows={4} value={note} onChange={(e) => setNote(e.target.value)} autoFocus
            placeholder="e.g. The evening waiting list is only two or three people, and most of them get in." />
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <button type="button" className="cx-btn cx-btn--blue" disabled={busy || note.trim().length < 10}
              onClick={() => onRevise(note.trim())}>
              Diagnose again
            </button>
            <button type="button" className="cx-link" onClick={() => setRevising(false)}>Cancel</button>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
