/**
 * The method, as shots: the six stages of every consultation, the four labels
 * every figure carries, how the answer is written, and what the firm will not
 * do. The id `labels` is linked from other pages.
 */
import { Link } from 'react-router-dom';
import { CloseBand } from '../components/firm/FirmPage';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { usePageMeta } from '../utils/pageMeta';

const STEPS = [
  {
    title: 'You state the question in your own words',
    body: ['The problem, the decision or the venture you are weighing. There is no form to complete first.'],
  },
  {
    title: 'We ask only what the answer depends on',
    body: [
      'Questions come one at a time, and each depends on your answer to the one before. You can upload a spreadsheet or an export; the figures are read directly from it.',
      'Where you do not know a number, you can say so. We estimate it and label the estimate as ours, wherever it appears.',
    ],
  },
  {
    title: 'We test every explanation against your figures',
    body: [
      'We set out every cause consistent with what you have told us, including your own view, and test each one against your numbers. An explanation your figures contradict is ruled out, with the reason written down.',
    ],
  },
  {
    title: 'Two reviewers try to disprove the strongest explanation',
    body: ['An explanation is kept only when it survives both. What could cause the plan to fail is written into the blueprint, not left out of it.'],
  },
  {
    title: 'Every page is checked before release',
    body: [
      'Each figure is traced back to its source and each file is checked against the answer page. A page that fails a check is fixed before you receive it.',
    ],
  },
  {
    title: 'You read the answer and decide',
    body: [
      'You can challenge any part of it, and your objection is tested the same way. Nothing is built until you have read the answer and decided.',
    ],
  },
] as const;

const LABELS = [
  { tag: 'theirs', name: 'Yours', body: 'A figure you gave us or that we read from your files.' },
  { tag: 'derived', name: 'Worked out', body: 'Calculated from your figures. The calculation is shown beside it.' },
  { tag: 'ours', name: 'Our estimate', body: 'A judgement we made where your figures were silent, with the reason.' },
  { tag: 'cited', name: 'Cited', body: 'A published reference, named so you can read it yourself.' },
] as const;

const WRITING = [
  { title: 'The answer comes first.', body: 'Page one of every file states it in two lines, followed by the figures it rests on.' },
  { title: 'Every page is titled with what it found.', body: 'A reader who stops after the titles still has the argument.' },
  { title: 'The ranges add up.', body: 'Each action in the recommendation register is worth a stated range, and the ranges add up to the headline figure.' },
  { title: 'The documents agree.', body: 'The presentation carries the same titles and figures as the written files.' },
] as const;

const NEVER = [
  {
    title: 'Invent a figure',
    body: 'Every number is yours, worked out from yours, a cited reference, or an estimate labelled as ours. If the answer hangs on a figure nobody can estimate fairly, we say which figure would settle it.',
  },
  {
    title: 'Present an estimate as a fact',
    body: 'Every estimate carries its label wherever it appears, in the documents and in the presentation.',
  },
  {
    title: 'Recommend software the business does not need',
    body: 'If the answer is a change in pricing, staffing or schedule, the answer says so before anything is built.',
  },
  {
    title: 'Give an answer the figures cannot support',
    body: 'When the evidence is not enough, the answer page states what is missing instead of a conclusion.',
  },
] as const;

export default function ApproachPage() {
  usePageMeta(
    'Approach',
    'How a consultation is run: one question at a time, every explanation tested against your figures, every figure labelled with its source.',
  );

  return (
    <>
      <Shot title="The method" first>
        <p className="film-mark">Approach</p>
        <Rise as="h1" className="film-h">
          Every answer is tested against *your own figures* before you read it.
        </Rise>
        <p className="film-body">
          A consultation follows the same method whatever the business or the question. It is written down here so you know
          what to expect, and what to hold us to.
        </p>
        <div className="film-actions">
          <Link to="/demo" className="film-pill">
            Start a consultation
          </Link>
          <Link to="/approach#labels" className="film-pill film-pill--ghost">
            How figures are labelled
          </Link>
        </div>
      </Shot>

      <Shot tone="dark" title="Six stages" wide>
        <p className="film-mark">01 · How a consultation runs</p>
        <Rise className="film-h2">Six stages, *in this order,* for every client.</Rise>
        <ul className="film-rows">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <b>0{i + 1}</b>
              <div>
                <strong>{s.title}</strong>
                {s.body.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot tone="dark" title="Labels" id="labels">
        <p className="film-mark">02 · How figures are labelled</p>
        <Rise className="film-h2">Every figure says *where it came from.*</Rise>
        <p className="film-body">
          Each number in the answer, the documents and the presentation carries one of four labels. You can see at a glance
          which figures are yours and which are ours.
        </p>
        <div className="film-labels">
          {LABELS.map((l) => (
            <div className="film-label" key={l.name}>
              <span className={`film-chip film-chip--${l.tag}`}>{l.name}</span>
              <p>{l.body}</p>
            </div>
          ))}
        </div>
      </Shot>

      <Shot title="The writing" wide>
        <p className="film-mark">03 · How the answer is written</p>
        <Rise className="film-h2">The answer *comes first.*</Rise>
        <ul className="film-rows">
          {WRITING.map((w, i) => (
            <li key={w.title}>
              <b>Rule {i + 1}</b>
              <div>
                <strong>{w.title}</strong>
                <span>{w.body}</span>
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot title="What we will not do" wide>
        <p className="film-mark">04 · What we will not do</p>
        <Rise className="film-h2">Four things *we will not do.*</Rise>
        <ul className="film-rows">
          {NEVER.map((n) => (
            <li key={n.title}>
              <b>Never</b>
              <div>
                <strong>{n.title}</strong>
                <span>{n.body}</span>
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <CloseBand />
    </>
  );
}
