/**
 * The opening conversation, in place of a fixed list of questions.
 *
 * The static step asked the same four questions whatever the client said. It
 * could not follow "340 visits a month at $85" with "and what caps that
 * number?" — which is the question that decides whether their problem is
 * demand or capacity, and the one nobody volunteers.
 *
 * So rounds accumulate on screen rather than replacing each other. The client
 * can see what they have already told us and change it; a consultant who
 * hides the first half of the conversation is one you cannot correct.
 *
 * Every question is optional except the ones that fill a field the
 * engagement cannot start without (the business's name). A blank answer is
 * better than a guessed figure, because the diagnosis will treat a guess as
 * evidence.
 */
import type { DiscoveryQuestion } from '../../api/consultant';

export interface Round {
  questions: DiscoveryQuestion[];
  /** What the consultant said it still needed before asking these. */
  because: string;
}

const ICON = {
  shield:
    'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  check: 'M4.5 12.75l6 6 9-13.5',
};

function Glyph({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} className={className} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

export default function Conversation({
  rounds,
  answers,
  onAnswer,
  onMore,
  loading,
  done,
  closing,
  required = [],
}: {
  rounds: Round[];
  answers: Record<string, string>;
  onAnswer: (id: string, value: string) => void;
  onMore: () => void;
  loading: boolean;
  /** No more rounds are coming — the consultant has what it needs. */
  done: boolean;
  /** Its own words on why it stopped, or what it still wants. */
  closing: string;
  /** Intake fields the engagement cannot start without. A question filling
   *  one of these is not labelled optional: the first version called the
   *  business name "(optional)" while the launch refused to proceed without
   *  it, which is a label that lies exactly when someone believes it. */
  required?: string[];
}) {
  const asked = rounds.reduce((n, r) => n + r.questions.length, 0);
  const answeredCount = rounds.reduce(
    (n, r) => n + r.questions.filter((q) => (answers[q.id] ?? '').trim()).length,
    0,
  );
  // Only offer another round once this one has been engaged with. Asking for
  // follow-ups to nothing produces follow-ups to nothing.
  const canAskMore = !done && !loading && answeredCount > 0;

  return (
    <div className="studio-discovery">
      <div className="studio-disc-intro">
        <Glyph path={ICON.shield} className="w-4 h-4" />
        <p>
          Answer what you know, skip the rest — every figure in your plan is calculated{' '}
          <strong>only</strong> from numbers you give us. We never invent one, and a blank is
          better than a guess.
        </p>
      </div>

      {rounds.map((round, ri) => (
        <div key={ri}>
          {ri > 0 && round.because ? (
            <p className="studio-hint mt-6 mb-1 italic text-slate-600">{round.because}</p>
          ) : null}
          {round.questions.map((q, i) => {
            const n = rounds.slice(0, ri).reduce((t, r) => t + r.questions.length, 0) + i + 1;
            return (
              <div className="studio-field studio-disc-q" key={q.id}>
                <label htmlFor={'st-dq-' + q.id}>
                  <span className="studio-disc-no">{String(n).padStart(2, '0')}</span>
                  {q.label}{' '}
                  {q.field && required.includes(q.field) ? (
                    <span className="font-normal text-blue-600">(needed to start)</span>
                  ) : (
                    <span className="text-slate-500 font-normal">(optional)</span>
                  )}
                </label>
                <input
                  id={'st-dq-' + q.id}
                  value={answers[q.id] ?? ''}
                  onChange={(e) => onAnswer(q.id, e.target.value)}
                  // The model writes these as realistic examples, without the
                  // "e.g." that says so — so "Mostly women aged 30-55" sat in
                  // the box looking like an answer already given, and invented
                  // a demographic in a product that promises never to invent
                  // anything. Marked as an example here, whatever it wrote.
                  placeholder={/^(e\.g\.|eg|for example)/i.test(q.placeholder) || !q.placeholder
                    ? q.placeholder
                    : `e.g. ${q.placeholder}`}
                />
                {q.why ? <p className="studio-hint studio-disc-why">{q.why}</p> : null}
              </div>
            );
          })}
        </div>
      ))}

      {loading ? (
        <div className="studio-disc-loading" aria-live="polite">
          <span className="studio-disc-spinner" aria-hidden="true" />
          {asked === 0
            ? 'Reading your brief and writing your questions…'
            : 'Reading your answers…'}
        </div>
      ) : null}

      {canAskMore ? (
        <button
          type="button"
          className="mt-5 inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 px-5 py-2.5 font-semibold text-slate-700 hover:border-slate-400 hover:text-navy"
          onClick={onMore}
        >
          Anything else you need to ask?
        </button>
      ) : null}

      {done && asked > 0 && !loading ? (
        <p className="studio-hint mt-5 flex items-start gap-2 text-emerald-700">
          <Glyph path={ICON.check} className="mt-0.5 w-4 h-4 shrink-0" />
          <span>{closing || "That's everything we need to start."}</span>
        </p>
      ) : null}
    </div>
  );
}
