/**
 * The recommendation register. A ledger on a wide screen, one card per row
 * on a phone. The range ends are figures, never numbers typed here.
 */
import type { ReactNode } from 'react';
import type { FigureKind, FigureMap, RegisterEnd, StudioRegister } from '../../api/consultant';
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

function figuresFor(register: StudioRegister, figures?: FigureMap | null): FigureMap {
  const out: FigureMap = { ...(figures ?? {}) };
  for (const row of register.rows) {
    for (const end of [row.low, row.mid, row.high]) {
      if (!end || out[end.figure_id]) continue;
      out[end.figure_id] = {
        display: end.display,
        kind: kindOf(end.tag),
        tag: end.tag,
        source: '',
      };
    }
  }
  return out;
}

function Cell({ k, children, className }: { k?: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      {k ? <span className="cx-reg-k">{k}</span> : null}
      <div className="cx-reg-v">{children}</div>
    </div>
  );
}

function End({ end, figures, label }: { end: RegisterEnd | null; figures: FigureMap; label: string }) {
  return (
    <div className="cx-reg-end">
      <span className="cx-reg-k">{label}</span>
      {end ? (
        <>
          <div className="cx-reg-num">{end.display}</div>
          <FigTags ids={[end.figure_id]} figures={figures} labelled={false} className="cx-reg-tag" />
        </>
      ) : null}
    </div>
  );
}

export default function Register({
  register,
  figures,
}: {
  register: StudioRegister;
  figures?: FigureMap | null;
}) {
  const known = figuresFor(register, figures);
  // An answer with no value to share out has no range, so it has no column for one.
  const hasRange = register.rows.some((row) => row.low || row.mid || row.high);
  return (
    <section className={`cx-register${hasRange ? '' : ' cx-register--plain'}`} aria-label="The register">
      <h2 className="cx-h3">The register</h2>
      <div className="cx-reg-head" aria-hidden="true">
        <span>Recommendation</span>
        <span>What changes</span>
        <span>When</span>
        <span>Owner</span>
        <span>Comes after</span>
        {hasRange ? <span>The range</span> : null}
      </div>
      <div className="cx-reg-list">
        {register.rows.map((row, i) => (
          <article className="cx-reg-row" key={`${row.recommendation}-${i}`}>
            <Cell className="cx-reg-rec">
              <h3>{row.recommendation}</h3>
            </Cell>
            <Cell k="What changes">{row.changes}</Cell>
            <Cell k="When">{row.when}</Cell>
            <Cell k="Owner">{row.owner}</Cell>
            <Cell k="Comes after" className={row.depends_on.length ? undefined : 'cx-reg-skip'}>
              {row.depends_on.length ? row.depends_on.join(', ') : ''}
            </Cell>
            {hasRange ? (
              <div className="cx-reg-ends">
                <End end={row.low} figures={known} label="Low" />
                <End end={row.mid} figures={known} label="Middle" />
                <End end={row.high} figures={known} label="High" />
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {register.footnotes.length ? (
        <ul className="cx-reg-notes">
          {register.footnotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
