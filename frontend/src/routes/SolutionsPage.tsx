import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import ConceptScreens from '../components/concepts/ConceptScreens';
import { EXAMPLES } from '../data/examples';
import { PRICE_LINE } from '../data/offer';
import { saveFrontDoor } from '../utils/frontDoor';
import { usePageMeta } from '../utils/pageMeta';
import '../styles/examples.css';

// The 3D scene draws each example's screens; it needs a name and the screens.
const SCENES = EXAMPLES.map((e) => ({ name: e.system, screens: e.screens }));

/**
 * The Examples page. A visitor picks the kind of business closest to theirs,
 * reads the question an owner of one brings us, what the consultation would
 * test and against which of their own figures, and what it could lead to.
 * Then they can start a consultation with that question already written,
 * ready to change into their own.
 */
export default function SolutionsPage() {
  usePageMeta(
    'Examples',
    'Eight kinds of business, the question an owner of each brings us, what a consultation tests and what it can lead to.',
  );
  const navigate = useNavigate();
  const [sel, setSel] = useState(0);
  const [own, setOwn] = useState('');
  const fileRef = useRef<HTMLDivElement>(null);
  const ex = EXAMPLES[sel];

  const choose = (i: number) => {
    setSel(i);
    // on a phone the case sits below the tabs; bring its top into view
    if (window.innerWidth < 1024) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      fileRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    }
  };
  const start = (text: string) => {
    saveFrontDoor(text);
    navigate('/demo');
  };

  return (
    <div className="fm-page ex-page min-h-screen">
      <SiteNav />
      <main>
        <header className="ex-head">
          <div className="fm-wrap">
            <p className="fm-kicker">Examples</p>
            <h1 className="fm-h1">Eight businesses, eight questions, and what a consultation does with each</h1>
            <p className="fm-lede">
              Choose the business closest to yours. You will see the question its owner brings us, what we would test
              against their own figures, and what it could lead to. These are illustrations of the method, not client
              results.
            </p>
          </div>
          <div className="ex-tabs-wrap">
            <div className="fm-wrap">
              <div className="ex-tabs" role="tablist" aria-label="Kind of business">
                {EXAMPLES.map((e, i) => (
                  <button
                    key={e.id}
                    type="button"
                    role="tab"
                    id={`ex-tab-${e.id}`}
                    aria-selected={i === sel}
                    aria-controls="ex-file"
                    onClick={() => choose(i)}
                  >
                    {e.business}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </header>

        <section className="ex-file" id="ex-file" role="tabpanel" aria-labelledby={`ex-tab-${ex.id}`} ref={fileRef}>
          <div className="fm-wrap ex-grid">
            <div className="ex-text">
              <p className="ex-label">The owner’s question</p>
              <blockquote className="ex-question">“{ex.question}”</blockquote>

              <div className="ex-block">
                <h2 className="ex-h">What the consultation tests</h2>
                <ul className="ex-tests">
                  {ex.tests.map((t) => (
                    <li key={t.claim}>
                      <p>{t.claim}</p>
                      <span>
                        Tested against <span className="fm-tag fm-tag--theirs">{t.against}</span>
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="ex-note">
                  Each explanation the figures contradict is ruled out, with the reason. If none survives, the answer says
                  so.
                </p>
              </div>

              <div className="ex-block">
                <h2 className="ex-h">What it can lead to</h2>
                <p className="ex-system">{ex.system}</p>
                <p className="fm-p">{ex.systemLine}</p>
              </div>

              <div className="ex-block">
                <h2 className="ex-h">What would show it worked</h2>
                <ul className="ex-measures">
                  {ex.measures.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </div>

              <div className="ex-go">
                <button type="button" className="fm-btn" onClick={() => start(ex.question)}>
                  Start a consultation with this question
                </button>
                <p className="fm-note">You can change the question into your own before it starts. {PRICE_LINE}</p>
              </div>
            </div>

            <div className="ex-visual">
              <ConceptScreens concepts={SCENES} selected={sel} />
              <p className="ex-visual-cap">The screens of {ex.system.toLowerCase()}, as the technical plan would set them out.</p>
            </div>
          </div>
        </section>

        <section className="ex-band">
          <div className="fm-wrap">
            <p className="ex-band-line">Not every answer is software.</p>
            <p className="ex-band-body">
              When the figures point to a change in price, schedule or staffing, the answer says so and nothing is built.
              A system is recommended only when the figures show it pays for itself.
            </p>
            <Link to="/approach" className="ex-band-link">
              How we test an answer
            </Link>
          </div>
        </section>

        <section className="fm-section">
          <div className="fm-wrap ex-own">
            <div>
              <h2 className="fm-h2">Your business is not one of these?</h2>
              <p className="fm-intro" style={{ marginTop: '1rem' }}>
                The method is the same for every business. Write the question in your own words and the consultation
                starts from it.
              </p>
            </div>
            <form
              className="fm-form"
              onSubmit={(e) => {
                e.preventDefault();
                start(own);
              }}
            >
              <div className="fm-field">
                <label htmlFor="ex-own">What would you like to work out?</label>
                <textarea
                  id="ex-own"
                  rows={4}
                  value={own}
                  onChange={(e) => setOwn(e.target.value)}
                  placeholder="Describe it as you would to an adviser."
                />
              </div>
              <div>
                <button type="submit" className="fm-btn">
                  Start a consultation
                </button>
                <p className="fm-note">{PRICE_LINE}</p>
              </div>
            </form>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
