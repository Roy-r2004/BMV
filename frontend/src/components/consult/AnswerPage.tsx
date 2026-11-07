/**
 * The first screen of a finished result: the question, the answer, and what
 * it rests on. Every number is a figure the server already checked.
 *
 * Wide screens put the question beside the facts. A phone stacks them.
 */
import type { FigureKind, FigureMap, StudioAnswerPage } from '../../api/consultant';
import { FigTags } from './Fig';

const KIND_OF_TAG: [string, FigureKind][] = [
  ['estimate', 'ours'],
  ['worked', 'derived'],
  ['reference', 'reference'],
  ['source', 'reference'],
];

function kindOf(tag: string): FigureKind {
  const lower = tag.toLowerCase();
  return KIND_OF_TAG.find(([word]) => lower.includes(word))?.[1] ?? 'theirs';
}

function figuresFor(page: StudioAnswerPage, figures?: FigureMap | null): FigureMap {
  const out: FigureMap = { ...(figures ?? {}) };
  for (const number of page.numbers) {
    if (out[number.figure_id]) continue;
    out[number.figure_id] = {
      display: number.display,
      kind: kindOf(number.tag),
      tag: number.tag,
      source: '',
    };
  }
  return out;
}

export default function AnswerPage({
  page,
  figures,
}: {
  page: StudioAnswerPage;
  figures?: FigureMap | null;
  readOnly?: boolean;
}) {
  const lines = page.answer_lines.filter((line) => line.trim());
  const known = figuresFor(page, figures);
  const facts = [
    page.believed ? ['What you believed', page.believed] : null,
    page.tested ? ['What we tested', page.tested] : null,
    page.monday ? ['Monday', page.monday] : null,
  ].filter((fact): fact is [string, string] => fact !== null);

  return (
    <section className="cx-answer-page" aria-label="The answer">
      <div className="cx-answer-open">
        <div className="cx-answer-lead">
          {page.question ? <h1 className="cx-h1">{page.question}</h1> : null}
          {lines.length ? (
            <div className="cx-answer-lines">
              {lines.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          ) : null}
          {page.numbers.length ? (
            <FigTags ids={page.numbers.map((n) => n.figure_id)} figures={known} labelled />
          ) : null}
          {page.rests_on ? <p className="cx-answer-rests">{page.rests_on}</p> : null}
        </div>
        {facts.length || page.would_not.length ? (
          <dl className="cx-answer-facts">
            {facts.map(([label, text]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{text}</dd>
              </div>
            ))}
            {page.would_not.length ? (
              <div>
                <dt>What we would not do</dt>
                <dd>
                  <ul>
                    {page.would_not.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </div>
    </section>
  );
}
