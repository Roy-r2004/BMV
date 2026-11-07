/**
 * Who stands behind the method: consultants and engineers, as disciplines.
 * No names, photos, headcount or former employers: the site states only what
 * the firm has confirmed, and the method follows the large firms'
 * conventions without claiming their results.
 */
import { Link } from 'react-router-dom';

const ROLES = [
  {
    title: 'Consultants',
    body: 'Wrote the method: how a question is framed, which explanations are tested, and how an answer is written so that a reader who stops after the page titles still has the argument.',
  },
  {
    title: 'Engineers',
    body: 'Built the pipeline that runs it: every figure traced to its source, every calculation shown, and every page checked before release.',
  },
  {
    title: 'The standard',
    body: 'Every file follows the conventions of the large consulting firms: the answer first, each page titled with its finding, every figure labelled with its source, and a recommendation register whose ranges add up to the headline figure.',
  },
] as const;

const INTRO =
  'The method behind every consultation was written by consultants and built into software by engineers. Each rule in it comes from engagement experience: what a business’s own figures can prove, where an estimate misleads, and which recommendations hold up once a business acts on them.';

export default function Team({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <section className="fm-section">
        <div className="fm-wrap">
          <div className="fm-section-head fm-section-head--split">
            <h2 className="fm-h2">Built by consultants and engineers</h2>
            <div>
              <p className="fm-intro">{INTRO}</p>
              <div className="fm-actions">
                <Link to="/about#team" className="fm-btn-line">
                  About the firm
                </Link>
                <Link to="/approach" className="fm-btn-line">
                  Our approach
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="fm-section" id="team">
      <div className="fm-wrap">
        <div className="fm-section-head fm-section-head--split">
          <h2 className="fm-h2">Built by consultants and engineers</h2>
          <p className="fm-intro">{INTRO}</p>
        </div>
        <ul className="fm-rows">
          {ROLES.map((r) => (
            <li key={r.title}>
              <h3>{r.title}</h3>
              <p>{r.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
