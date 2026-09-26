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

import type { StudioDecision } from '../../api/consultant';
import { fmt } from '../../utils/week';

/** Each document and the stretch of the run's progress it is written in. */
const DOCS: { title: string; note: string; from: number; to: number }[] = [
  { title: 'The blueprint', note: 'The decision, the case, every module', from: 42, to: 56 },
  { title: 'The technical plan', note: 'For whoever builds it', from: 56, to: 60 },
  { title: 'The operations manual', note: 'Who does what, every day', from: 60, to: 61 },
  { title: 'The implementation roadmap', note: 'Who does what, week by week', from: 61, to: 62 },
  { title: 'Your product screens', note: 'Drawn for you, checked twice', from: 62, to: 100 },
  { title: 'Your AI team', note: 'What each one decides alone', from: 42, to: 56 },
];

interface Pillar {
  key: string;
  text: string;
  lead?: string;
  fig?: string;
  work?: string;
}

function Modal({ children, onClose, label }: { children: React.ReactNode; onClose: () => void; label: string }) {
  return (
    <div
      className="cx-modal-back"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
    >
      <div className="cx-card cx-modal">{children}</div>
    </div>
  );
}

export default function Answer({
  decision,
  firstName,
  pct,
  writing,
  onOpenPlans,
  onRevise,
  onStartPlans,
  busy,
  error,
}: {
  decision: StudioDecision;
  firstName: string | null;
  pct: number;
  writing: boolean;
  onOpenPlans?: () => void;
  onRevise: (note: string) => void;
  onStartPlans?: () => void;
  busy: boolean;
  error: string | null;
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

  const legacy = !writing && (decision.status === 'awaiting_approval' || decision.status === 'advised');
  const ready = pct >= 100;
  const docState = (from: number, to: number): 'queued' | 'busy' | 'ok' => {
    if (pct >= to || (!writing && ready)) return 'ok';
    if (writing && pct >= from) return 'busy';
    return 'queued';
  };

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
          <h3>{legacy ? 'Your plans' : ready ? 'Your plans are ready' : 'Your plans are being written'}</h3>
          <p>Everything needed to build this, for you or for any team.</p>
          <div className="cx-docs">
            {DOCS.map((doc) => {
              const st = legacy ? 'queued' : docState(doc.from, doc.to);
              return (
                <div key={doc.title} className={`cx-docline${st === 'busy' ? ' busy' : st === 'ok' ? ' ok' : ''}`}>
                  <span className="ic" aria-hidden="true" />
                  <div>
                    <b>{doc.title}</b>
                    <small>{doc.note}</small>
                  </div>
                  <span className="st">{legacy ? '' : st === 'ok' ? 'Ready' : st === 'busy' ? 'Writing' : 'Queued'}</span>
                </div>
              );
            })}
          </div>
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
              You don't need to wait here. We'll email you when it's ready.
            </p>
          ) : null}
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
                  <span className="cx-chip cx-chip--green">Held up</span>
                  <p style={{ marginTop: 8, fontWeight: 600 }}>{diag.leading.statement}</p>
                  {diag.leading.because ? <p className="cx-muted" style={{ marginTop: 4, fontSize: 15 }}>{diag.leading.because}</p> : null}
                </li>
                {diag.considered.map((c) => (
                  <li key={c.statement}>
                    <span className={`cx-chip ${c.verdict === 'refuted' ? 'cx-chip--dim' : 'cx-chip--amber'}`}>
                      {c.verdict === 'refuted' ? 'Ruled out' : c.verdict === 'supported' ? 'Also supported' : "Couldn't check"}
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
              <p className="cx-muted" style={{ marginTop: 12 }}>Nothing listed. Confidence: {d.confidence ?? 'medium'}.</p>
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
        <Modal label="Tell us what we got wrong" onClose={() => setRevising(false)}>
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
            <button type="button" className="cx-textbtn" onClick={() => setRevising(false)}>Cancel</button>
            <button
              type="button"
              className="cx-btn cx-btn--blue"
              disabled={busy || note.trim().length < 10}
              onClick={() => {
                onRevise(note.trim());
                setRevising(false);
              }}
            >
              Send
            </button>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
