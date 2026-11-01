/**
 * The first screen of a finished result: the question, the answer, and what
 * it rests on. Every number is a figure the server already checked.
 */
import type { FigureJson, FigureKind, FigureMap, StudioAnswerPage } from '../../api/consultant';
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

/** The payload's map, plus any number this page names that the map does not. */
function figuresFor(page: StudioAnswerPage, figures?: FigureMap | null): FigureMap {
  const out: FigureMap = { ...(figures ?? {}) };
  for (const number of page.numbers) {
    if (out[number.figure_id]) continue;
    const extra: FigureJson = {
      display: number.display,
      kind: kindOf(number.tag),
      tag: number.tag,
      source: '',
    };
    out[number.figure_id] = extra;
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
  return (
    <section className="cx-stage cx-answer-page" aria-label="The answer">
      {page.question ? <h1 className="cx-title">{page.question}</h1> : null}
      {lines.map((line, i) => (
        <p className="cx-lede" key={i}>{line}</p>
      ))}
      {page.numbers.length ? (
        <FigTags ids={page.numbers.map((n) => n.figure_id)} figures={known} labelled />
      ) : null}
      {page.believed ? <p><b>What you believed. </b>{page.believed}</p> : null}
      {page.tested ? <p><b>What we tested. </b>{page.tested}</p> : null}
      {page.monday ? <p><b>Monday. </b>{page.monday}</p> : null}
      {page.would_not.length ? (
        <>
          <h2 className="cx-h3">What we would not do</h2>
          <ul className="cx-plain-list">
            {page.would_not.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
      {page.rests_on ? <p className="cx-faint">{page.rests_on}</p> : null}
    </section>
  );
}
