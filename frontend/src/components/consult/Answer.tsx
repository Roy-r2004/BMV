/**
 * The answer, and the plans being written beside it.
 *
 * The answer is a pyramid: the governing thought first, then the few points
 * that hold it up, each with its arithmetic shown in small type underneath.
 * What we estimated or could not check is boxed in amber, because it is marked
 * the same way in every plan. On the right, the plans write themselves while
 * they read; nothing waits on a button. Pushing back is always one click away.
 */
import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

import type { StudioDecision, StudioDiagnosis } from '../../api/consultant';
import { fmt } from '../../utils/week';

interface Pillar {
  key: string;
  text: string;
  lead?: string;
  fig?: string;
  work?: string;
}

/** `locked` holds the dialog open while what it sends is in flight, so a failure
 *  is read where it was caused rather than after the dialog has gone. */
function Modal({ children, onClose, label, locked = false }: {
  children: React.ReactNode;
  onClose: () => void;
  label: string;
  locked?: boolean;
}) {
  return (
    <div
      className="cx-modal-back"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onClick={(e) => !locked && e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => !locked && e.key === 'Escape' && onClose()}
    >
      <div className="cx-card cx-modal">{children}</div>
    </div>
  );
}

/** What the leading explanation's own test found. It is the one we went with,
 *  not necessarily one that held up: the chip says which. */
function LeadingChip({ leading }: { leading: StudioDiagnosis['leading'] }) {
  if (leading.not_tested) return <span className="cx-chip cx-chip--amber">We couldn't run this test</span>;
  if (leading.verdict === 'supported') return <span className="cx-chip cx-chip--green">Held up</span>;
  if (leading.verdict === 'refuted') return <span className="cx-chip cx-chip--amber">Didn't hold up</span>;
  if (leading.verdict === 'untestable') return <span className="cx-chip cx-chip--amber">Couldn't be checked</span>;
  return null;
}

export default function Answer({
  decision,
  firstName,
  pct,
  writing,
  stopped = false,
  documents,
  mailPromise,
  onOpenPlans,
  onRevise,
  onStartPlans,
  busy,
  error,
  reviseError,
}: {
  decision: StudioDecision;
  firstName: string | null;
  pct: number;
  writing: boolean;
  /** The run stopped before the plans were finished: the answer is read on
   *  its own, with what was written before the stop, and nothing on this
   *  screen says plans are on their way. */
  stopped?: boolean;
  /** The documents the run has written or is writing, as the server reports
   *  them. The list is exactly this: nothing is shown ahead of the run. */
  documents: { key: string; title: string; state: 'ready' | 'writing' }[];
  /** True only when mail can actually be sent. The screen promises an email
   *  only then. */
  mailPromise: boolean;
  onOpenPlans?: () => void;
  /** Resolves true once the note was accepted. The dialog stays open, with the
   *  note in it, until then, so a note that could not be sent is not lost. */
  onRevise: (note: string) => Promise<boolean>;
  onStartPlans?: () => void;
  busy: boolean;
  /** Why starting the plans failed. Shown under the button. */
  error: string | null;
  /** Why sending the note failed. Shown in the dialog, beside the note. */
  reviseError: string | null;
}) {
  const reduce = useReducedMotion();
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState('');

  const a = decision.answer ?? null;
  const d = decision.decision;
  const diag = decision.diagnosis;
  const headline = a?.headline || d.central_problem || 'Here is what we found.';
  const turn = a?.turn || '';
  const sub = a?.sub || (a ? '' : d.summary || '');
  const unverified = d.unverified ?? [];
  const cites = diag?.leading?.cites ?? [];
  const citeText = (ids: string[]) =>
    ids
      .map((id) => cites.find((c) => c.id === id))
      .filter(Boolean)
      .map((c) => c!.source || c!.text)
      .filter(Boolean)
      .join('; ');

  // The points that hold the answer up, in order: their own figures, then the
  // value of the move, then anything else the diagnosis rests on.
  const pillars: Pillar[] = [];
  const usedCites = new Set<string>();
  for (const f of a?.figures ?? []) {
    f.cites.forEach((c) => usedCites.add(c));
    const from = citeText(f.cites);
    pillars.push({ key: `f-${f.value}-${f.label}`, text: f.label, fig: f.value, work: from ? `From your answers: ${from}.` : 'From your answers.' });
  }
  const move = a?.move ?? null;
  if (move) {
    move.cites.forEach((c) => usedCites.add(c));
    const proposed = move.proposed.length
      ? ` ${move.proposed.map((p) => `${p.label || 'The target'} (${fmt(p.value)})`).join(' and ')} ${move.proposed.length > 1 ? 'are' : 'is'} our proposal; the rest is yours.`
      : ' Every term is one of your figures.';
    pillars.push({ key: 'move', text: move.label, fig: move.display, work: `${move.working}.${proposed}` });
  }
  for (const c of cites) {
    if (usedCites.has(c.id) || !c.text) continue;
    pillars.push({ key: `c-${c.id}`, text: c.text, work: c.source ? `From ${c.source}.` : undefined });
  }
  const shown = pillars.slice(0, 5);

  const legacy = !stopped && !writing && (decision.status === 'awaiting_approval' || decision.status === 'advised');
  const ready = pct >= 100;
  const written = documents.filter((doc) => doc.state === 'ready');

  const enter = (delay: number) =>
    reduce ? {} : { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay } };

  return (
    <section className="cx-stage">
      <p className="cx-kicker">{firstName ? `${firstName}, the answer` : 'The answer'}</p>
      <div className="cx-ans">
        <motion.div className="cx-pane cx-gov" {...enter(0)}>
          <h2>
            {headline}
            {turn ? <span>{turn}</span> : null}
          </h2>
          {sub ? <p className="cx-sub">{sub}</p> : null}

          {shown.length ? (
            <ol className="cx-pillars">
              {shown.map((p, i) => (
                <li key={p.key} className="cx-pillar">
                  <span className="k">{i + 1}</span>
                  <div>
                    <p>{p.lead ? <b>{p.lead} </b> : null}{p.text}</p>
                    {p.work ? <p className="work">{p.work}</p> : null}
                  </div>
                  {p.fig ? <span className="fig">{p.fig}</span> : <span />}
                </li>
              ))}
            </ol>
          ) : null}

          {decision.revisions ? (
            <p className="cx-faint" style={{ marginTop: 18, fontSize: 14 }}>
              Worked through again with what you told us: “{decision.revisions}”
            </p>
          ) : null}

          {unverified.length ? (
            <div className="cx-estd">
              <b>What we estimated or couldn't check.</b> Each is marked in every plan.
              <ul>
                {unverified.map((u) => (
                  <li key={u}>• {u}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </motion.div>

        <motion.aside className="cx-pane cx-writing" {...enter(0.15)} aria-live="polite">
          {stopped ? (
            <>
              <h3>Your plans were not finished</h3>
              {written.length ? (
                <>
                  <p>What was written before it stopped:</p>
                  <div className="cx-docs">
                    {written.map((doc) => (
                      <div key={doc.key} className="cx-docline ok">
                        <span className="ic" aria-hidden="true" />
                        <div>
                          <b>{doc.title}</b>
                        </div>
                        <span className="st">Ready</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p>It stopped before any of them was written.</p>
              )}
            </>
          ) : (
            <>
              <h3>{legacy ? 'Your plans' : ready ? 'Your plans are ready' : 'Your plans are being written'}</h3>
              <p>Everything needed to build this, for you or for any team.</p>
              {legacy ? (
                // At the gate nothing has been written, whatever the server lists
                // (the AI team is known before the gate, and is not a plan).
                <p className="cx-faint" style={{ marginTop: 16, fontSize: 14 }}>We start writing them when you press the button.</p>
              ) : documents.length ? (
                <div className="cx-docs">
                  {documents.map((doc) => (
                    <div key={doc.key} className={`cx-docline${doc.state === 'writing' ? ' busy' : ' ok'}`}>
                      <span className="ic" aria-hidden="true" />
                      <div>
                        <b>{doc.title}</b>
                      </div>
                      <span className="st">{doc.state === 'writing' ? 'Writing' : 'Ready'}</span>
                    </div>
                  ))}
                </div>
              ) : !ready ? (
                <p className="cx-faint" style={{ marginTop: 16, fontSize: 14 }}>Your plans start in a moment.</p>
              ) : null}
              {legacy ? (
                <button type="button" className="cx-btn cx-btn--blue" onClick={onStartPlans} disabled={busy || !onStartPlans}>
                  {busy ? 'Starting…' : 'Write my plans'}
                </button>
              ) : (
                <button type="button" className="cx-btn cx-btn--blue" onClick={onOpenPlans} disabled={!ready || !onOpenPlans}>
                  Open your plans
                </button>
              )}
              {!ready && !legacy ? (
                <p className="cx-faint" style={{ marginTop: 10, fontSize: 13, textAlign: 'center' }}>
                  {mailPromise
                    ? "You don't need to wait here. We'll email you when it's ready."
                    : 'This page updates itself as each document is finished.'}
                </p>
              ) : null}
            </>
          )}
          <p className="cx-pushback">
            Something off? <button type="button" onClick={() => setRevising(true)} disabled={busy}>Push back on the answer</button>
          </p>
          {error ? <p className="cx-error" role="alert" style={{ marginTop: 10, textAlign: 'center' }}>{error}</p> : null}
        </motion.aside>
      </div>

      <details className="cx-howwe">
        <summary>How we got here: the explanations we tested, and what the reviewers said</summary>
        <div className="cx-howwe-grid">
          {diag ? (
            <div className="cx-card" style={{ padding: 28 }}>
              <h2 className="cx-h3">The explanations we tested</h2>
              <ul style={{ marginTop: 18, display: 'grid', gap: 18 }}>
                <li>
                  <LeadingChip leading={diag.leading} />
                  <p style={{ marginTop: 8, fontWeight: 600 }}>{diag.leading.statement}</p>
                  {diag.leading.because ? <p className="cx-muted" style={{ marginTop: 4, fontSize: 15 }}>{diag.leading.because}</p> : null}
                </li>
                {diag.considered.map((c) => (
                  <li key={c.statement}>
                    <span className={`cx-chip ${c.verdict === 'refuted' ? 'cx-chip--dim' : 'cx-chip--amber'}`}>
                      {c.not_tested
                        ? "We couldn't run this test"
                        : c.verdict === 'refuted' ? 'Ruled out' : c.verdict === 'supported' ? 'Also supported' : "Couldn't check"}
                    </span>
                    <p style={{ marginTop: 8 }}>{c.statement}</p>
                    {c.because ? <p className="cx-muted" style={{ marginTop: 4, fontSize: 15 }}>{c.because}</p> : null}
                  </li>
                ))}
              </ul>
              {diag.challenges.length ? (
                <>
                  <h3 style={{ marginTop: 28, fontWeight: 600, fontFamily: 'var(--cx-body)', letterSpacing: 0 }}>What the two reviewers said</h3>
                  <ul style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                    {diag.challenges.map((c) => (
                      <li key={c.angle} style={{ fontSize: 15.5 }}>
                        <span style={{ fontWeight: 600, color: c.kills ? 'var(--cx-red)' : 'var(--cx-green)' }}>
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
          <div className="cx-card" style={{ padding: 28 }}>
            <h2 className="cx-h3">What we couldn't check</h2>
            {unverified.length ? (
              <ul style={{ marginTop: 14, display: 'grid', gap: 8 }}>
                {unverified.map((u) => (
                  <li key={u} style={{ fontSize: 15.5 }}>• {u}</li>
                ))}
              </ul>
            ) : (
              <p className="cx-muted" style={{ marginTop: 12 }}>Nothing listed.</p>
            )}
            {d.why_not_the_others ? (
              <>
                <h3 style={{ marginTop: 24, fontWeight: 600, fontFamily: 'var(--cx-body)', letterSpacing: 0 }}>Why not the other kinds of fix</h3>
                <p className="cx-muted" style={{ marginTop: 8, fontSize: 15.5 }}>{d.why_not_the_others}</p>
              </>
            ) : null}
          </div>
        </div>
      </details>

      {revising ? (
        <Modal label="Tell us what we got wrong" onClose={() => setRevising(false)} locked={busy}>
          <h2 className="cx-h3">Tell us what we got wrong</h2>
          <p className="cx-muted" style={{ marginTop: 8 }}>
            We re-run the analysis with what you tell us, and rewrite the plans to match.
          </p>
          <textarea
            className="cx-textarea"
            style={{ marginTop: 18 }}
            rows={4}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            autoFocus
            aria-label="Your note"
            placeholder="e.g. The evening waiting list is only two or three people, and most of them get in."
          />
          <div className="cx-row" style={{ marginTop: 20, justifyContent: 'flex-end' }}>
            <button type="button" className="cx-textbtn" onClick={() => setRevising(false)} disabled={busy}>Cancel</button>
            <button
              type="button"
              className="cx-btn cx-btn--blue"
              disabled={busy || note.trim().length < 10}
              onClick={async () => {
                if (await onRevise(note.trim())) setRevising(false);
              }}
            >
              Send
            </button>
          </div>
          {reviseError ? <p className="cx-error" role="alert" style={{ marginTop: 12, textAlign: 'right' }}>{reviseError}</p> : null}
        </Modal>
      ) : null}
    </section>
  );
}
