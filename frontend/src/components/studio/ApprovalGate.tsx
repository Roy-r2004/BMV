/**
 * The decision, before anything is built on it.
 *
 * This screen exists because the pipeline used to run thirteen stages
 * straight through: the client submitted a form and came back to a finished
 * blueprint built on a diagnosis they had never read. A wrong reading cost
 * them the wait and cost us the generation.
 *
 * So it is deliberately not a confirmation dialog. It is the brief — what we
 * understood, what we concluded, and what we would build — and the client
 * either presses Build or tells us what we got wrong.
 */
import { useState } from 'react';
import { motion } from 'framer-motion';

import type { StudioDecision, StudioFigure } from '../../api/consultant';
import DiagnosisView from './DiagnosisView';
import EvidenceDrop from './EvidenceDrop';

const ICON = {
  check: 'M4.5 12.75l6 6 9-13.5',
  pencil: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z',
  spark: 'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z',
};

function Glyph({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} className={className} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

/** A labelled block of the brief. Renders nothing when it has nothing to
 *  say — an empty "What we understand" heading reads as a system that
 *  failed, which is worse than a shorter brief. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <section className="mt-7 first:mt-0">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</h2>
      <div className="mt-2.5 text-slate-700 leading-relaxed">{children}</div>
    </section>
  );
}

export const BUDGET_OPTIONS = ['Starter scope', 'Standard scope', 'Full build', 'Not sure yet'];
export const TIMELINE_OPTIONS = ['ASAP (2–4 weeks)', '1–2 months', '2–3 months', 'Flexible'];

/** A row of choices. Local to the gate rather than imported from the intake —
 *  the intake no longer has a screen these belong on. */
function Choices({
  options,
  value,
  onChange,
  disabled,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o)}
          className={`rounded-full border px-4 py-1.5 text-sm font-medium transition ${
            value === o
              ? 'border-blue-500 bg-blue-50 text-blue-700'
              : 'border-slate-300 text-slate-600 hover:border-slate-400'
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  process: 'the way the work flows',
  pricing: 'what you charge',
  staffing: 'people and hours',
  none: 'nothing we can build',
};

export default function ApprovalGate({
  decision,
  onApprove,
  onAccept,
  onRevise,
  busy,
  error,
  accepted,
  figures,
  onUpload,
  onDeleteFigure,
  evidenceBusy,
  evidenceNote,
  evidenceError,
}: {
  decision: StudioDecision;
  onApprove: (scope: { budget_range: string; timeline: string }) => void;
  onAccept: () => void;
  onRevise: (note: string) => void;
  busy: boolean;
  error: string | null;
  /** They took the advice. The brief is the deliverable; nothing is building. */
  accepted: boolean;
  figures: StudioFigure[];
  onUpload: (file: File) => void;
  onDeleteFigure: (id: string) => void;
  evidenceBusy: boolean;
  evidenceNote: string | null;
  evidenceError: string | null;
}) {
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState('');
  // Asked here, not on the way in. They only reach the playbook at stage ten,
  // and someone who has just read a diagnosis and wants it built is happy to
  // answer them — someone who has just arrived is not.
  const [budget, setBudget] = useState(BUDGET_OPTIONS[0]);
  const [timeline, setTimeline] = useState(TIMELINE_OPTIONS[TIMELINE_OPTIONS.length - 1]);

  const { understanding, decision: verdict } = decision;
  const name = decision.business_name || 'Your business';
  const employees = verdict.recommended_ai_employees ?? [];
  const features = verdict.recommended_features ?? [];
  const pains = understanding.pain_points ?? [];

  // We are telling them not to spend. The build stays available — they paid
  // for one and it is their business — but it stops being the obvious action,
  // because an equally-weighted "Build it" next to "we don't think you should"
  // is not advice, it is a disclaimer.
  const advising = !decision.builds;

  // 10 is the server's own floor. Mirrored so the button disables rather
  // than letting them write four words and receive a 422.
  const noteReady = note.trim().length >= 10;

  return (
    <motion.section
      key="decision"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45 }}
    >
      <div className="max-w-3xl mx-auto text-center mb-9">
        <p className="studio-kicker mb-4">{advising ? 'Our honest answer' : 'Before we build'}</p>
        <h1 className="studio-display text-3xl sm:text-4xl font-bold text-navy">
          {accepted
            ? `This is your answer for ${name}`
            : advising
              ? "We don't think you should build this"
              : `Here's what we concluded about ${name}`}
        </h1>
        <p className="mt-3 text-slate-600">
          {accepted ? (
            // No "come back later", and no claim about charges. The first
            // version promised "you were not charged" (we do not know that
            // — it is a commercial fact nobody gave us) and told them to
            // return and press a Build button this page did not have.
            'Nothing has been built yet. If you want the full package anyway — the Blueprint, Technical Plan and Operations Manual — you can build it right now, below.'
          ) : advising ? (
            <>
              You came for software. What we found is{' '}
              {KIND_LABEL[verdict.intervention_kind ?? ''] ?? 'something a build would not move'} —
              and building around it would cost you money without fixing it. You can still tell us
              to build; we'd rather you knew first.
            </>
          ) : (
            "Read it. If it's right, we'll build it. If it isn't, tell us what we missed — nothing gets built on a diagnosis you don't agree with."
          )}
        </p>
      </div>

      <div className="max-w-3xl mx-auto">
        {decision.revisions ? (
          <div className="studio-panel p-5 mb-6 border-l-4 border-l-amber-400">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-700">
              You sent this back
            </p>
            <p className="mt-2 text-slate-700">{decision.revisions}</p>
            <p className="mt-2 text-sm text-slate-500">
              This diagnosis was made again with that in front of us.
            </p>
          </div>
        ) : null}

        {/* The reasoning comes before the recommendation that rests on it.
            When no diagnosis could be made we fall back to the understanding
            panel — which is what this screen showed before the stage existed
            — rather than leaving a gap where the thinking should be. */}
        {decision.diagnosis ? <DiagnosisView diagnosis={decision.diagnosis} /> : null}

        <div className={`studio-panel p-6 sm:p-9${decision.diagnosis ? ' mt-6' : ''}`}>
          {decision.diagnosis ? null : (
            <>
              <Section title="What we understand">
                {understanding.business_model || understanding.target_customer_profile ? (
                  <>
                    {understanding.business_model ? <p>{understanding.business_model}</p> : null}
                    {understanding.target_customer_profile ? (
                      <p className="mt-2 text-slate-600">
                        <span className="text-slate-500">Who you serve — </span>
                        {understanding.target_customer_profile}
                      </p>
                    ) : null}
                  </>
                ) : null}
              </Section>

              <Section title="What's costing you">
                {pains.length > 0 ? (
                  <ul className="space-y-1.5">
                    {pains.map((p, i) => (
                      <li key={i} className="flex gap-2.5">
                        <span className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </Section>
            </>
          )}

          <Section title={decision.diagnosis ? 'So this is what we recommend' : 'The decision'}>
            {verdict.summary ? (
              <p className="text-[1.05rem] text-slate-800">{verdict.summary}</p>
            ) : null}
          </Section>

          {verdict.why_not_the_others && advising ? (
            <Section title="Why not software">
              <p>{verdict.why_not_the_others}</p>
            </Section>
          ) : null}

          <Section title={advising ? "What we'd still build, if anything" : "What we'd build"}>
            {employees.length > 0 || features.length > 0 ? (
              <>
                <div className="space-y-3">
                  {employees.map((e, i) => (
                    <div key={i} className="flex gap-3">
                      <Glyph path={ICON.spark} className="mt-0.5 w-4 h-4 shrink-0 text-blue-600" />
                      <div>
                        <p className="font-semibold text-navy">{e.title}</p>
                        {e.why ? <p className="text-slate-600 text-[0.95rem]">{e.why}</p> : null}
                      </div>
                    </div>
                  ))}
                </div>
                {features.length > 0 ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {features.map((f, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              // An empty list is a real answer here, and saying so beats a
              // blank space the client reads as a stage that broke.
              <p className="text-slate-500">
                Nothing. Building anything here would be spending against the wrong cause.
              </p>
            )}
          </Section>

          {verdict.unverified.length > 0 ? (
            <Section title="What we could not establish">
              <ul className="space-y-1.5">
                {verdict.unverified.map((u, i) => (
                  <li key={i} className="flex gap-2.5">
                    <span className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                    <span>{u}</span>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {verdict.confidence ? (
            <p className="mt-6 border-t border-slate-200 pt-4 text-sm text-slate-500">
              Our confidence in this: <span className="font-semibold text-slate-700">{verdict.confidence}</span>
              {verdict.confidence !== 'high'
                ? ' — read the gaps above before you commit money to it.'
                : '.'}
            </p>
          ) : null}
        </div>

        {/* After the argument, not inside it: the diagnosis and the
            recommendation that follows from it read as one piece, and this is
            a third action beside Build and Not quite — strengthen it first.
            Never hidden: accepting our advice records that they read it, it
            does not close the engagement. */}
        <EvidenceDrop
          figures={figures}
          wouldNeed={decision.diagnosis?.leading.would_need ?? null}
          onUpload={onUpload}
          onDelete={onDeleteFigure}
          busy={evidenceBusy}
          note={evidenceNote}
          error={evidenceError}
        />

        {error ? (
          <p className="mt-4 text-sm text-rose-600" role="alert">
            {error}
          </p>
        ) : null}

        {revising ? (
          <div className="studio-panel p-6 mt-6">
            <label htmlFor="gate-note" className="block font-semibold text-navy">
              What did we get wrong?
            </label>
            <p className="mt-1 text-sm text-slate-500">
              A sentence or two. It goes to the next diagnosis as your correction.
            </p>
            <textarea
              id="gate-note"
              className="mt-3 w-full rounded-xl border border-slate-300 p-3 text-slate-800 focus:border-blue-500 focus:outline-none"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Missed bookings aren't the problem — we turn work away. The bottleneck is scheduling staff, not taking calls."
              autoFocus
            />
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                className="studio-cta sm:w-auto sm:px-7"
                disabled={busy || !noteReady}
                onClick={() => onRevise(note.trim())}
              >
                {busy ? 'Sending…' : 'Diagnose again'}
              </button>
              <button
                type="button"
                className="rounded-xl px-5 py-3 font-semibold text-slate-600 hover:text-navy"
                disabled={busy}
                onClick={() => setRevising(false)}
              >
                Back
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="studio-panel p-6 mt-6">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                Before we build
              </p>
              <div className="mt-4">
                <p className="font-semibold text-navy">What can you spend?</p>
                <p className="mb-2.5 text-sm text-slate-500">
                  A constraint on the build plan, not a price.
                </p>
                <Choices options={BUDGET_OPTIONS} value={budget} onChange={setBudget} disabled={busy} />
              </div>
              <div className="mt-5">
                <p className="font-semibold text-navy">How soon do you need it?</p>
                <Choices
                  options={TIMELINE_OPTIONS}
                  value={timeline}
                  onChange={setTimeline}
                  disabled={busy}
                />
              </div>
            </div>

            <div className="mt-7 flex flex-col sm:flex-row gap-3 sm:items-center">
            {advising ? (
              <>
                {accepted ? (
                  <span className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-50 px-6 py-3 font-semibold text-emerald-700">
                    <Glyph path={ICON.check} className="w-4 h-4" />
                    Brief saved
                  </span>
                ) : (
                  <button type="button" className="studio-cta sm:w-auto sm:px-9" disabled={busy} onClick={onAccept}>
                    <Glyph path={ICON.check} className="w-4 h-4" />
                    {busy ? 'Saving…' : 'Understood — keep the brief'}
                  </button>
                )}
                {/* Once they have read the advice, building is THEIR call and
                    becomes the main button. Before that it stays secondary. */}
                <button
                  type="button"
                  className={
                    accepted
                      ? 'studio-cta sm:w-auto sm:px-9'
                      : 'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-6 py-3 font-semibold text-slate-700 hover:border-slate-400 hover:text-navy'
                  }
                  disabled={busy}
                  onClick={() => onApprove({ budget_range: budget, timeline })}
                >
                  {busy ? 'Starting…' : accepted ? 'Build the package now' : 'Build it anyway'}
                </button>
              </>
            ) : (
              <button type="button" className="studio-cta sm:w-auto sm:px-9" disabled={busy} onClick={() => onApprove({ budget_range: budget, timeline })}>
                <Glyph path={ICON.check} className="w-4 h-4" />
                {busy ? 'Starting…' : 'Build it'}
              </button>
            )}
            <button
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-6 py-3 font-semibold text-slate-700 hover:border-slate-400 hover:text-navy"
              disabled={busy}
              onClick={() => setRevising(true)}
            >
              <Glyph path={ICON.pencil} className="w-4 h-4" />
              Not quite
            </button>
            </div>
          </>
        )}

        <p className="studio-hint studio-hint--trust mt-6">
          {advising && !accepted
            ? "Building takes about ten minutes and real money. We'd rather you spent it on the thing above."
            : 'Building takes about ten minutes. Nothing starts until you press it.'}
        </p>
      </div>
    </motion.section>
  );
}
