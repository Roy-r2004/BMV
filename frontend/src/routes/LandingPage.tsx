/**
 * The landing page: the product itself, in one scroll story.
 *
 * A sticky 3D stage (productScene) sits behind ten chapters. On a wide screen
 * it fills the page behind the text; on a phone it is pinned to the top half
 * and the text scrolls beneath it, one step per screen. The layers come forward
 * one at a time (the question, the conversation, the test, the answer, the
 * package), then the blueprint and the technical plan flip past section by
 * section. After the story: a sample answer page, the terms, and the question.
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { CAPTIONS, CHAPTERS, mountProductScene } from '../components/home/productScene';
import { BUILD_LINE, CONSULTATION_FEE, PRICE_LINE } from '../data/offer';
import { COMPANY } from '../data/company';
import { CloseBand } from '../components/firm/FirmPage';
import { saveFrontDoor } from '../utils/frontDoor';
import { usePageMeta } from '../utils/pageMeta';
import '../styles/landing.css';

function Chapter({ state, deep = false, step, children }: { state: number; deep?: boolean; step?: string; children: React.ReactNode }) {
  return (
    <section className={`ls-chapter${deep ? ' ls-chapter--deep' : ''}`} data-state={state}>
      <div className="ls-wrap">
        <div className="ls-col">
          {step ? <p className="ls-step">{step}</p> : null}
          {children}
        </div>
      </div>
    </section>
  );
}

function Ask({ id }: { id: string }) {
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const start = () => {
    saveFrontDoor(text);
    navigate('/demo');
  };
  return (
    <form
      className="ls-ask"
      onSubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      <label htmlFor={id}>Describe what you need to decide or resolve</label>
      <textarea
        id={id}
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            start();
          }
        }}
        placeholder="For example: our evening classes are half empty and I am not sure whether to cut them or market them."
      />
      <div className="ls-ask-row">
        <span>{PRICE_LINE}</span>
        <button type="submit" className="ls-cta">Start a consultation</button>
      </div>
    </form>
  );
}

/**
 * The first screen's proof: one sentence from a sample answer, its three
 * figures labelled one after another. The one orchestrated moment on the page.
 */
function HeroProof() {
  return (
    <figure className="ls-proof" aria-label="A sentence from a sample answer">
      <blockquote>
        The evening classes run <b>4 in 10</b> <i className="ls-proof-tag fm-tag fm-tag--theirs">Yours</i> places
        empty. Filling them is worth <b>$4,730</b> <i className="ls-proof-tag fm-tag fm-tag--derived">Worked out</i> a
        month, of which <b>75%</b> <i className="ls-proof-tag fm-tag fm-tag--ours">Our estimate</i> is reachable.
      </blockquote>
      <figcaption>From a sample answer. Every figure says where it came from.</figcaption>
    </figure>
  );
}

/** Between the story and the sample: the firm's rule, on dark paper. */
function Statement() {
  return (
    <section className="ls-statement">
      <div className="ls-wrap">
        <p className="ls-statement-line ls-display">Every figure in the advice you pay for can be checked.</p>
        <dl className="ls-statement-labels">
          <div>
            <dt><span className="fm-tag fm-tag--theirs">Yours</span></dt>
            <dd>A figure you gave us, or one read from your files.</dd>
          </div>
          <div>
            <dt><span className="fm-tag fm-tag--derived">Worked out</span></dt>
            <dd>Calculated from your figures, with the calculation shown.</dd>
          </div>
          <div>
            <dt><span className="fm-tag fm-tag--ours">Our estimate</span></dt>
            <dd>A judgement where your figures were silent, with the reason.</dd>
          </div>
        </dl>
        <Link to="/approach" className="ls-statement-link">How we test an answer</Link>
      </div>
    </section>
  );
}

const TAG = { theirs: 'Yours', derived: 'Worked out', ours: 'Our estimate' } as const;

function Fig({ v, k }: { v: string; k: keyof typeof TAG }) {
  return (
    <span className={`ls-fig ls-fig--${k}`}>
      <b>{v}</b>
      <i>{TAG[k]}</i>
    </span>
  );
}

// The sample answer's figures, and where each came from. Invented studio, sample data.
const SAMPLE_FIGS = [
  {
    v: '4 in 10',
    k: 'theirs',
    line: 'evening places unsold, from your class register',
    trail:
      'Read from the class register you uploaded: over the last eight weeks, 10 of the 24 places in each evening class went unsold on an average night.',
  },
  {
    v: '$4,730',
    k: 'derived',
    line: 'a month, if every empty evening place were sold',
    trail: 'Worked out from your figures: 10 places × $22 a class (your price list) × 5 evenings × 4.3 weeks in a month.',
  },
  {
    v: '75%',
    k: 'ours',
    line: 'of that we treat as reachable, so about $3,500',
    trail:
      'Our estimate. Your morning classes run 85 to 92% full, so we assume the evenings can reach most of that, not all of it. If you think it is lower, say so and the answer is tested again.',
  },
] as const;

/** A finished answer page, for an invented studio. Every figure is sample data. */
function SampleAnswer() {
  const [pick, setPick] = useState(0);
  return (
    <section className="ls-section" id="example">
      <div className="ls-wrap">
        <div className="ls-section-head">
          <p className="ls-eyebrow">An example answer page</p>
          <h2 className="ls-display ls-h2">The first page of every file states the answer and what it rests on</h2>
          <p className="ls-body">
            This is the page a client reads first. The business is invented and every figure on it is sample data;
            the structure is the one every consultation produces. Select a figure to see where it came from.
          </p>
        </div>

        <article className="ls-sample" aria-label="Sample answer page">
          <header className="ls-sample-top">
            <span>Sample data</span>
            <span>Halo Reformer Studio, answer page</span>
          </header>
          <p className="ls-sample-q">Should the studio add a third evening class, or fix the two it already runs?</p>
          <h3 className="ls-display ls-sample-a">
            Fix the two evening classes first. They run four in ten places empty, and filling most of them is worth
            about $3,500 a month.
          </h3>
          <div className="ls-sample-figs" role="group" aria-label="The figures the answer rests on">
            {SAMPLE_FIGS.map((f, i) => (
              <button
                key={f.v}
                type="button"
                className={`ls-figbtn${i === pick ? ' is-on' : ''}`}
                aria-pressed={i === pick}
                aria-controls="ls-trail"
                onClick={() => setPick(i)}
              >
                <Fig v={f.v} k={f.k} />
                <span>{f.line}</span>
              </button>
            ))}
          </div>
          <div className="ls-trail" id="ls-trail" aria-live="polite">
            <p className="ls-trail-head">Where {SAMPLE_FIGS[pick].v} comes from</p>
            <p>{SAMPLE_FIGS[pick].trail}</p>
          </div>
          <dl className="ls-sample-facts">
            <div>
              <dt>What you believed</dt>
              <dd>Mornings were the weak slot.</dd>
            </div>
            <div>
              <dt>What the test showed</dt>
              <dd>Mornings run 85 to 92% full. The two evening classes run 55 to 60%.</dd>
            </div>
            <div>
              <dt>Monday</dt>
              <dd>Open a standby list for the 19:00 class and offer the free places to members first.</dd>
            </div>
            <div>
              <dt>What we would not do</dt>
              <dd>Add a third evening class before the two you run are full.</dd>
            </div>
          </dl>
          <p className="ls-sample-rests">
            This answer rests on four of your figures, one calculation and one estimate of ours. Each is labelled where
            it appears.
          </p>
        </article>
      </div>
    </section>
  );
}

/** After the story: the firm itself. Its services, what they cost, and who runs it. */
function FirmIntro() {
  return (
    <div className="fm-page fm-after-story">
      <section className="fm-section fm-section--mist">
        <div className="fm-wrap">
          <div className="fm-section-head fm-section-head--split">
            <h2 className="fm-h2">Three services, each starting from the decision in front of you</h2>
            <p className="fm-intro">{BUILD_LINE}</p>
          </div>
          <div className="fm-cols">
            <article className="fm-col">
              <h3>Consultation</h3>
              <p className="fm-col-price">{CONSULTATION_FEE}</p>
              <p>A tested answer to one question, with the blueprint, the technical plan, the roadmap and the presentation.</p>
              <Link to="/services#consultation" className="fm-link">What a consultation includes</Link>
            </article>
            <article className="fm-col">
              <h3>System build</h3>
              <p className="fm-col-price">Quoted after the scope is agreed</p>
              <p>We build the system the technical plan describes, in the order it sets, and hand it over to your team.</p>
              <Link to="/services#build" className="fm-link">How a build works</Link>
            </article>
            <article className="fm-col">
              <h3>Private AI</h3>
              <p className="fm-col-price">Quoted after the workload is assessed</p>
              <p>Open-weight models on infrastructure you control, for data that must stay inside your business.</p>
              <Link to="/private-ai" className="fm-link">How private AI works</Link>
            </article>
          </div>
        </div>
      </section>

      <section className="fm-section">
        <div className="fm-wrap">
          <div className="fm-person">
            <img src={COMPANY.founderPhoto} alt={COMPANY.founder} width={240} height={240} />
            <div>
              <p className="fm-kicker">The firm</p>
              <h2 className="fm-h2">{COMPANY.name} is an AI consultancy registered in Dubai</h2>
              <p className="fm-p" style={{ marginTop: '1.25rem' }}>
                It was founded by <b>{COMPANY.founder}</b> on one rule: every figure in the advice a client pays for can
                be checked.
              </p>
              <div className="fm-actions">
                <Link to="/about" className="fm-btn-line">About the firm</Link>
                <Link to="/approach" className="fm-btn-line">Our approach</Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function LandingPage() {
  usePageMeta(
    'An AI consultancy that tests its answers against your figures',
    'Build My Version is an AI consultancy. Describe the problem or the decision; we test every explanation against your own figures and deliver the answer, the reasoning and the plan.',
  );
  const storyRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState(0);

  useEffect(() => {
    const story = storyRef.current, stage = stageRef.current, labels = labelsRef.current;
    if (!story || !stage || !labels) return;
    return mountProductScene({ story, stage, labels, onState: setState });
  }, []);

  const goTo = (i: number) => {
    const el = storyRef.current?.querySelector(`[data-state="${i}"]`);
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // a document chapter starts at its first page; narrow screens read every chapter from its top
    const top = el?.classList.contains('ls-chapter--deep') || window.innerWidth < 1024;
    el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: top ? 'start' : 'center' });
  };

  return (
    <div className="ls-page min-h-screen">
      <SiteNav />

      <div className="ls-story" ref={storyRef}>
        <div className="ls-stage" ref={stageRef}>
          <div className="ls-scrim" />
          <div className="ls-labels" ref={labelsRef} aria-hidden="true" />
          <nav className="ls-index" aria-label="Sections on this page">
            {CHAPTERS.map((name, i) => (
              <button
                key={name}
                type="button"
                className={i === state ? 'is-on' : undefined}
                aria-current={i === state ? 'step' : undefined}
                onClick={() => goTo(i)}
              >
                <span>{name}</span>
                <i aria-hidden="true" />
              </button>
            ))}
          </nav>
          <p className="ls-caption">{CAPTIONS[state]}</p>
        </div>

        <Chapter state={0}>
          <p className="ls-eyebrow">AI consultancy</p>
          <h1 className="ls-display ls-h1">Business decisions, tested against your own figures</h1>
          <p className="ls-lede">
            Describe the problem, the decision or the venture in your own words. We test every explanation against your
            figures and deliver the answer, the reasoning and the plan. If the answer is not software, we say so before
            anything is built.
          </p>
          <div className="ls-go">
            <Link to="/demo" className="ls-cta">Start a consultation</Link>
            <button type="button" className="ls-ghost" onClick={() => goTo(1)}>
              See how a consultation works
            </button>
          </div>
          <p className="ls-price">{PRICE_LINE}</p>
          <HeroProof />
        </Chapter>

        <Chapter state={1} step="1. The question">
          <h2 className="ls-display ls-h2">A consultation begins with one question, in your own words</h2>
          <p className="ls-body">
            State the problem, the decision or the venture you are weighing. There is no form to complete first. Every
            question that follows depends on your answer to the one before it.
          </p>
        </Chapter>

        <Chapter state={2} step="2. The facts">
          <h2 className="ls-display ls-h2">We ask only what the answer depends on</h2>
          <p className="ls-body">
            Questions come one at a time. You can upload a spreadsheet or an export, and the figures are read directly
            from it. Where you do not know a number, you can say so: we never fill it in for you.
          </p>
          <ul className="ls-points">
            <li><span><b>Every figure carries its source:</b> yours, worked out from yours, our estimate, or a cited reference.</span></li>
            <li><span><b>“I don’t know” is a valid answer.</b> A gap is recorded as a gap.</span></li>
          </ul>
        </Chapter>

        <Chapter state={3} step="3. The test">
          <h2 className="ls-display ls-h2">Every explanation is tested, including your own</h2>
          <p className="ls-body">
            We set out every cause consistent with what you have told us and test each against your numbers. The
            strongest goes to two reviewers whose task is to disprove it.
          </p>
          <ul className="ls-points">
            <li><span><b>Ruled out,</b> with the reason, when your figures contradict it.</span></li>
            <li><span><b>Kept,</b> only when it survives both reviewers.</span></li>
          </ul>
        </Chapter>

        <Chapter state={4} step="4. The answer">
          <h2 className="ls-display ls-h2">You receive the answer on one page, with its evidence</h2>
          <p className="ls-body">
            The page states the question, the answer in two lines, the figures it rests on, what to do first and what
            we would not do. <b>Nothing is built until you have read it and decided.</b>
          </p>
          <ul className="ls-points">
            <li><span><b>You can challenge the answer.</b> Your objection is tested the same way.</span></li>
            <li><span><b>We prepare the work;</b> every decision stays yours.</span></li>
          </ul>
        </Chapter>

        <Chapter state={5} step="5. The package">
          <h2 className="ls-display ls-h2">Six files, each opening with the same answer</h2>
          <ul className="ls-points">
            <li><span><b>The blueprint,</b> with the recommendation register: each action, its owner, its timing and the range it is worth. The ranges add up to the headline figure.</span></li>
            <li><span><b>The technical plan</b> and <b>the operations manual.</b></span></li>
            <li><span><b>The roadmap,</b> as long as the plan requires, with owners and measures.</span></li>
            <li><span><b>The system, screen by screen,</b> when the answer is to build software.</span></li>
            <li><span><b>The presentation deck,</b> with the same titles and figures as the documents.</span></li>
          </ul>
        </Chapter>

        <Chapter state={6} deep step="The blueprint">
          <h2 className="ls-display ls-h2">The blueprint sets out each decision with the figures behind it</h2>
          <p className="ls-body">
            The recommended decision and the reasoning, the financial case worked from your own figures, the customer
            journey, each part of the system, who does what, what to do first, how progress is measured and what could
            cause the plan to fail.
          </p>
          <div className="ls-stats">
            <div><b>Page one</b><span>of every file is the answer</span></div>
            <div><b>Every figure</b><span>labelled with its source</span></div>
            <div><b>Every page</b><span>titled with what it found</span></div>
          </div>
        </Chapter>

        <Chapter state={7} deep step="The technical plan">
          <h2 className="ls-display ls-h2">A technical plan your own team can build from</h2>
          <ul className="ls-points">
            <li><span><b>How the system works,</b> end to end, explained in plain language first.</span></li>
            <li><span><b>Each module:</b> its features, its data and its screens.</span></li>
            <li><span><b>Each AI agent:</b> what it decides alone, the tools it uses and its limits.</span></li>
            <li><span><b>Integrations and data protection.</b></span></li>
            <li><span><b>The build order,</b> with the checks that show each part is complete.</span></li>
          </ul>
          <p className="ls-body">{BUILD_LINE}</p>
        </Chapter>

        <Chapter state={8} step="Who we work with">
          <h2 className="ls-display ls-h2">Owners of businesses that are running, or about to open</h2>
          <p className="ls-body">
            The questions differ by sector and stage; the method does not. Each system we design is built around one
            business.
          </p>
          <div className="ls-kinds">
            {['Clinics', 'Retail', 'Studios', 'Restaurants', 'Logistics', 'Services', 'Professional firms', 'New ventures'].map((k) => (
              <span key={k}>{k}</span>
            ))}
          </div>
        </Chapter>

        <Chapter state={9}>
          <h2 className="ls-display ls-h2">What would you like to work out?</h2>
          <p className="ls-body">Describe it as you would to an adviser. The consultation starts from your words.</p>
          <Ask id="ls-ask" />
        </Chapter>
      </div>

      <Statement />

      <SampleAnswer />

      <FirmIntro />

      <CloseBand
        title="Start with the decision in front of you"
        body="A consultation begins with your question, in your own words, and ends with an answer you can check."
      />
      <SiteFooter />
    </div>
  );
}
