/**
 * The recommendation register. A table on a wide screen, one card per row
 * on a phone. The range ends are figures, never numbers typed here.
 */
import type { FigureJson, FigureKind, FigureMap, RegisterEnd, StudioRegister } from '../../api/consultant';
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
      const extra: FigureJson = {
        display: end.display,
        kind: kindOf(end.tag),
        tag: end.tag,
        source: '',
      };
      out[end.figure_id] = extra;
    }
  }
  return out;
}

function End({ end, figures }: { end: RegisterEnd | null; figures: FigureMap }) {
  if (!end) return null;
  return <FigTags ids={[end.figure_id]} figures={figures} labelled className="" />;
}

export default function Register({
  register,
  figures,
}: {
  register: StudioRegister;
  figures?: FigureMap | null;
}) {
  const known = figuresFor(register, figures);
  return (
    <section className="cx-stage cx-register" aria-label="The register">
      <h2 className="cx-h3">The register</h2>
      <table className="cx-reg-table">
        <thead>
          <tr>
            <th>Recommendation</th>
            <th>What changes</th>
            <th>When</th>
            <th>Owner</th>
            <th>Comes after</th>
            <th>Low</th>
            <th>Middle</th>
            <th>High</th>
          </tr>
        </thead>
        <tbody>
          {register.rows.map((row, i) => (
            <tr key={`${row.recommendation}-${i}`}>
              <td data-label="Recommendation">{row.recommendation}</td>
              <td data-label="What changes">{row.changes}</td>
              <td data-label="When">{row.when}</td>
              <td data-label="Owner">{row.owner}</td>
              <td data-label="Comes after">{row.depends_on.length ? row.depends_on.join(', ') : ''}</td>
              <td data-label="Low"><End end={row.low} figures={known} /></td>
              <td data-label="Middle"><End end={row.mid} figures={known} /></td>
              <td data-label="High"><End end={row.high} figures={known} /></td>
            </tr>
          ))}
        </tbody>
      </table>
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
