/**
 * The landing page: the product itself, in one scroll story.
 *
 * A sticky 3D stage (productScene) sits behind ten chapters. On a wide screen
 * it fills the page behind the text; on a phone it is pinned to the top half
 * and the text scrolls beneath it, one step per screen. The layers come forward
 * one at a time (the question, the conversation, the test, the answer, the
 * package), then the blueprint and the technical plan flip their own pages
 * while each is on screen. After the story: the firm's rule, its services and
 * the people behind its method, and the question.
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { CAPTIONS, mountProductScene } from '../components/home/productScene';
import { BUILD_LINE, CONSULTATION_FEE, PRICE_LINE } from '../data/offer';
import { CloseBand } from '../components/firm/FirmPage';
import Team from '../components/firm/Team';
import { usePageMeta } from '../utils/pageMeta';
import '../styles/landing.css';

/** The method, one step at a time. `state` is the product scene's state for the step. */
const STEPS: { state: number; tab: string; title: string; body: React.ReactNode }[] = [
  {
    state: 1,
    tab: 'Your idea',
    title: 'A consultation begins with your idea, in your own words',
    body: (
      <p className="ls-body">
        Describe the idea, or the problem or decision your business faces. There is no form to complete first. Every
        question that follows depends on your answer to the one before it.
      </p>
    ),
  },
  {
    state: 2,
    tab: 'The facts',
    title: 'We ask only what the answer depends on',
    body: (
      <p className="ls-body">
        Questions come one at a time. You can upload a spreadsheet or an export, and the figures are read directly from
        it. Where you do not know a number, say so: <b>we estimate it and label the estimate as ours.</b>
      </p>
    ),
  },
  {
    state: 3,
    tab: 'The test',
    title: 'Every explanation is tested, including your own',
    body: (
      <p className="ls-body">
        We set out every cause consistent with what you have told us and test each against your numbers. One your
        figures contradict is ruled out, with the reason. The strongest goes to <b>two reviewers whose task is to
        disprove it</b>, and is kept only if it survives both.
      </p>
    ),
  },
  {
    state: 4,
    tab: 'The answer',
    title: 'You receive the answer on one page, with its evidence',
    body: (
      <p className="ls-body">
        The question, the answer in two lines, the figures it rests on, what to do first and what we would not do. You
        can challenge it, and your objection is tested the same way. <b>Nothing is built until you have decided.</b>
      </p>
    ),
  },
  {
    state: 5,
    tab: 'The package',
    title: 'Six files, each opening with the same answer',
    body: (
      <p className="ls-body">
        The blueprint, the technical plan, the operations manual, the roadmap, the presentation and, when the answer is
        software, the system screen by screen. <Link to="/services#consultation">What each file contains</Link>
      </p>
    ),
  },
  {
    state: 6,
    tab: 'The blueprint',
    title: 'Each decision, with the figures behind it',
    body: (
      <p className="ls-body">
        The decision and the reasoning, the financial case worked from your figures, who does what, what to do first,
        how progress is measured and what could cause the plan to fail. <b>Every page is titled with what it found.</b>
      </p>
    ),
  },
  {
    state: 7,
    tab: 'The technical plan',
    title: 'A plan your own team can build from',
    body: (
      <p className="ls-body">
        How the system works end to end, each module and AI agent, the integrations, data protection and the build
        order, written so that any team could build from it.
      </p>
    ),
  },
  {
    state: 8,
    tab: 'The build',
    title: 'We build it for you, launch it and hand it over',
    body: (
      <p className="ls-body">
        When the answer is a system, we build it: the website, the app, the bookings and payments, the AI. It is quoted
        once the scope is agreed, and handed over with the operations manual. <b>The plan is yours either way.</b>{' '}
        <Link to="/solutions">See what we build for an idea</Link>
      </p>
    ),
  },
];

/** After the story: the firm's rule, on dark paper. */
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

/** After the story: the firm itself. Its services, what they cost, and who runs it. */
function FirmIntro() {
  return (
    <div className="fm-page fm-after-story">
      <section className="fm-section fm-section--mist">
        <div className="fm-wrap">
          <div className="fm-section-head fm-section-head--split">
            <h2 className="fm-h2">We test the idea, plan it and build it</h2>
            <p className="fm-intro">{BUILD_LINE}</p>
          </div>
          <div className="fm-cols">
            <article className="fm-col">
              <h3>Consultation</h3>
              <p className="fm-col-price">{CONSULTATION_FEE}</p>
              <p>Whether the idea's numbers work, and the full plan: the blueprint, the technical plan, the roadmap and the presentation.</p>
              <Link to="/services#consultation" className="fm-link">What a consultation includes</Link>
            </article>
            <article className="fm-col">
              <h3>We build it for you</h3>
              <p className="fm-col-price">Quoted after the scope is agreed</p>
              <p>The website, the app, the bookings and payments and the AI, built to the plan, launched and handed over.</p>
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

      <Team compact />
    </div>
  );
}

export default function LandingPage() {
  usePageMeta(
    'Your idea, tested and built into a working business',
    'Build My Version is an AI consultancy. Bring an idea or a running business: we test whether the numbers work, write the plan and build what it needs to run.',
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

  const [step, setStep] = useState(1);
  const walkRef = useRef<HTMLElement>(null);
  const toWalk = () => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    walkRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  };
  const at = STEPS.findIndex((x) => x.state === step);

  return (
    <div className="ls-page min-h-screen">
      <SiteNav />

      <div className="ls-story" ref={storyRef}>
        <div className="ls-stage" ref={stageRef}>
          <div className="ls-scrim" />
          <div className="ls-labels" ref={labelsRef} aria-hidden="true" />
          <p className="ls-caption">{CAPTIONS[state]}</p>
        </div>

        <section className="ls-chapter" data-state={0}>
          <div className="ls-wrap">
            <div className="ls-col">
              <p className="ls-eyebrow">AI consultancy</p>
              <h1 className="ls-display ls-h1">Your idea, tested and built into a working business</h1>
              <p className="ls-lede">
                Describe the idea in your own words. We test whether its numbers work, write the plan, and build what
                it needs to run: the website, the app, the bookings and payments, and the AI. If you already run a
                business, we do the same for the decision in front of you.
              </p>
              <div className="ls-go">
                <Link to="/demo" className="ls-cta">Start a consultation</Link>
                <button type="button" className="ls-ghost" onClick={toWalk}>
                  See how a consultation works
                </button>
              </div>
              <p className="ls-price">{PRICE_LINE}</p>
            </div>
          </div>
        </section>

        {/* One screen for the whole method: the reader opens a step, and the
            product behind the text moves to it (data-state follows the step). */}
        <section className="ls-chapter ls-walk" data-state={step} id="how" ref={walkRef}>
          <div className="ls-wrap">
            <div className="ls-col">
              <p className="ls-eyebrow">How a consultation works</p>
              <ol className="ls-steps">
                {STEPS.map((x, i) => {
                  const on = x.state === step;
                  return (
                    <li key={x.state} className={on ? 'is-on' : undefined}>
                      <button
                        type="button"
                        aria-expanded={on}
                        aria-controls={`ls-step-${x.state}`}
                        onClick={() => setStep(x.state)}
                      >
                        <span className="ls-step-no">{i + 1}</span>
                        {x.tab}
                      </button>
                      {on ? (
                        <div className="ls-step-body" id={`ls-step-${x.state}`}>
                          <h2 className="ls-display ls-h3">{x.title}</h2>
                          {x.body}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
              <div className="ls-walk-nav">
                {at < STEPS.length - 1 ? (
                  <button type="button" className="ls-ghost" onClick={() => setStep(STEPS[at + 1].state)}>
                    Next: {STEPS[at + 1].tab.toLowerCase()}
                  </button>
                ) : (
                  <Link to="/demo" className="ls-cta">Start a consultation</Link>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      <Statement />

      <FirmIntro />

      <CloseBand
        title="Start with the decision in front of you"
        body="A consultation begins with your question, in your own words, and ends with an answer you can check."
      />
      <SiteFooter />
    </div>
  );
}
