import { Link } from 'react-router-dom';
import { CloseBand, FirmPage, PageHero, Section } from '../components/firm/FirmPage';
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
      'Where you do not know a number, you can say so. The gap is recorded as a gap.',
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

const NEVER = [
  {
    title: 'Invent a figure',
    body: 'A number we do not have is reported as missing. If the answer depends on it, we say which figure would settle the question.',
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
    <FirmPage>
      <PageHero
        kicker="Approach"
        title="Every answer is tested against your own figures before you read it"
        lede="A consultation follows the same method whatever the business or the question. It is written down here so you know what to expect, and what to hold us to."
        actions={
          <>
            <Link to="/demo" className="fm-btn">
              Start a consultation
            </Link>
            <a href="#labels" className="fm-btn-line">
              How figures are labelled
            </a>
          </>
        }
      />

      <Section split title="How a consultation runs" intro="Six stages, in this order, for every client.">
        <ol className="fm-steps">
          {STEPS.map((s) => (
            <li key={s.title}>
              <div>
                <h3>{s.title}</h3>
                {s.body.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        id="labels"
        mist
        title="Every figure says where it came from"
        intro="Each number in the answer, the documents and the presentation carries one of four labels. You can see at a glance which figures are yours and which are ours."
      >
        <div className="fm-labels">
          {LABELS.map((l) => (
            <div key={l.name}>
              <p>
                <span className={`fm-tag fm-tag--${l.tag}`}>{l.name}</span>
              </p>
              <p>{l.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section split title="How the answer is written">
        <div>
          <p className="fm-p">
            <b>The answer comes first.</b> Page one of every file states it in two lines, followed by the figures it rests
            on.
          </p>
          <p className="fm-p">
            <b>Every page is titled with what it found.</b> A reader who stops after the titles still has the argument.
          </p>
          <p className="fm-p">
            <b>The ranges add up.</b> Each action in the recommendation register is worth a stated range, and the ranges
            add up to the headline figure.
          </p>
          <p className="fm-p">
            <b>The documents agree.</b> The presentation carries the same titles and figures as the written files.
          </p>
        </div>
      </Section>

      <Section mist split title="What we will not do">
        <ul className="fm-rows">
          {NEVER.map((n) => (
            <li key={n.title}>
              <h3>{n.title}</h3>
              <p>{n.body}</p>
            </li>
          ))}
        </ul>
      </Section>

      <CloseBand />
    </FirmPage>
  );
}
