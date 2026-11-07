/**
 * The Examples page. A visitor picks the example closest to theirs (an idea
 * first, or a business already running), reads the question its owner brings
 * us, what the consultation would test and against which figures, and what we
 * would build; the light spells out that system's name. Then they can start a
 * consultation with that question already written, ready to change into their
 * own. The examples illustrate the method; they are not clients.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { EXAMPLES, STAGES } from '../data/examples';
import { PRICE_LINE } from '../data/offer';
import { saveFrontDoor } from '../utils/frontDoor';
import { usePageMeta } from '../utils/pageMeta';

const SOURCE_NAME = { theirs: 'Yours', cited: 'Cited' } as const;

export default function SolutionsPage() {
  usePageMeta(
    'Examples',
    'Eight examples, from a first idea to a running business: the question each brings, what a consultation tests, and what we build.',
  );
  const navigate = useNavigate();
  const [sel, setSel] = useState(0);
  const [own, setOwn] = useState('');
  const ex = EXAMPLES[sel];

  const start = (text: string) => {
    saveFrontDoor(text);
    navigate('/demo');
  };

  return (
    <>
      <Shot shape="screens" title="Examples" first>
        <p className="film-mark">Examples</p>
        <Rise as="h1" className="film-h">
          From a first idea to a running business: *what we test, and what we build.*
        </Rise>
        <p className="film-body">
          Choose the example closest to yours. You will see the question its owner brings us, what we would test before
          anything is built, and what we would then build for them. These are illustrations of the method, not client
          results.
        </p>
      </Shot>

      <Shot shape="words" words={ex.system} title="The question" wide>
        <p className="film-mark">Pick an example</p>
        <div className="film-ex-groups" role="tablist" aria-label="Examples">
          {STAGES.map((g) => (
            <div key={g.stage} className="film-ex-group" role="presentation">
              <p>{g.label}</p>
              <div className="film-ex-list" role="presentation">
                {EXAMPLES.map((e, i) =>
                  e.stage === g.stage ? (
                    <button
                      key={e.id}
                      type="button"
                      role="tab"
                      id={`ex-tab-${e.id}`}
                      aria-selected={i === sel}
                      aria-controls="ex-file"
                      onClick={() => setSel(i)}
                    >
                      {e.business}
                    </button>
                  ) : null,
                )}
              </div>
            </div>
          ))}
        </div>
        <article className="film-card" id="ex-file" role="tabpanel" aria-labelledby={`ex-tab-${ex.id}`} aria-live="polite">
          <p className="film-note">{ex.stage === 'idea' ? 'The idea, in its owner’s words' : 'The owner’s question'}</p>
          <p className="film-quote">“{ex.question}”</p>
          <p className="film-sub">What the consultation tests</p>
          <ul className="film-tests">
            {ex.tests.map((t) => (
              <li key={t.claim}>
                <p>{t.claim}</p>
                <span>
                  Tested against {t.against}
                  <span className={`film-chip film-chip--${t.source}`}>{SOURCE_NAME[t.source]}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="film-sub">Each explanation the figures contradict is ruled out, with the reason. If none survives, the answer says so.</p>
        </article>
      </Shot>

      <Shot shape="screens" title="What we build" wide>
        <p className="film-mark">What we build</p>
        <h2 className="film-h2">{ex.system}</h2>
        <p className="film-body">{ex.systemLine}</p>
        <ul className="film-grid2">
          {ex.screens.map((s, i) => (
            <li key={s}>
              <small>Screen 0{i + 1}</small>
              <b>{s}</b>
            </li>
          ))}
        </ul>
        <p className="film-sub">What would show it worked</p>
        <ul className="film-bullets">
          {ex.measures.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
        <div className="film-actions">
          <button type="button" className="film-pill" onClick={() => start(ex.question)}>
            Start a consultation with this question
          </button>
        </div>
        <p className="film-sub">You can change the question into your own before it starts. {PRICE_LINE}</p>
      </Shot>

      <Shot shape="loose" title="Not every answer is software">
        <p className="film-mark">Not every answer is software</p>
        <Rise className="film-h2">A system is recommended only *when it pays for itself.*</Rise>
        <p className="film-body">
          When the figures point to a change in price, schedule or staffing, the answer says so and nothing is built.
        </p>
        <div className="film-actions">
          <Link to="/approach" className="film-link">
            How we test an answer
          </Link>
        </div>
      </Shot>

      <Shot shape="seed" title="Your own idea">
        <p className="film-mark">Your idea is not one of these?</p>
        <Rise className="film-h2">The method is the same for *every idea.*</Rise>
        <p className="film-body">Write it in your own words and the consultation starts from it.</p>
        <form
          className="film-form"
          onSubmit={(e) => {
            e.preventDefault();
            start(own);
          }}
        >
          <div className="film-field">
            <label htmlFor="ex-own">What would you like to work out?</label>
            <textarea id="ex-own" rows={3} value={own} onChange={(e) => setOwn(e.target.value)} placeholder="Describe it as you would to an adviser." />
          </div>
          <div className="film-actions">
            <button type="submit" className="film-pill">
              Start a consultation
            </button>
            <span className="film-sub">{PRICE_LINE}</span>
          </div>
        </form>
      </Shot>
    </>
  );
}
