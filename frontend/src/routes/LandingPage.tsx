/**
 * The landing page: the product itself, in one scroll story.
 *
 * A sticky 3D stage (productScene) sits behind ten chapters. The product's six
 * layers come forward one at a time (the question, the conversation, the test,
 * the answer, the package, the system), then the blueprint and the technical
 * plan flip past section by section, because their depth is the point. No
 * customer example: the software is what's on show. The question box waits at
 * the end, after the visitor has seen what it leads to.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { CAPTIONS, CHAPTERS, mountProductScene } from '../components/home/productScene';
import { saveFrontDoor } from '../utils/frontDoor';
import '../styles/landing.css';

function Chapter({ state, deep = false, children }: { state: number; deep?: boolean; children: React.ReactNode }) {
  return (
    <section className={`ls-chapter${deep ? ' ls-chapter--deep' : ''}`} data-state={state}>
      <div className="ls-wrap">
        <div className="ls-col">{children}</div>
      </div>
    </section>
  );
}

function Ask() {
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
      <label htmlFor="ls-ask">What are you trying to work out?</label>
      <textarea
        id="ls-ask"
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            start();
          }
        }}
        placeholder="A problem that's costing you, a decision you're stuck on, or something you want to start."
      />
      <div className="ls-ask-row">
        <span>No card. No sales call.</span>
        <button type="submit" className="ls-cta">Start the conversation</button>
      </div>
    </form>
  );
}

export default function LandingPage() {
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
          <h1 className="ls-display ls-h1">
            A consultancy that fits in your browser.
            <span className="ls-quiet">And tells you the truth.</span>
          </h1>
          <p className="ls-lede">
            It finds what's really holding your business back, or tests the one you're about to open. Then it designs
            the system that fixes it, down to a full blueprint and a technical plan any team can build from. If the fix
            isn't software, it says so first.
          </p>
          <div className="ls-go">
            <button type="button" className="ls-ghost" onClick={() => goTo(1)}>
              See how it works
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 5v14M6 13l6 6 6-6" />
              </svg>
            </button>
            <span>Free. About 15 minutes, when you're ready.</span>
          </div>
        </Chapter>

        <Chapter state={1}>
          <h2 className="ls-display ls-h2">
            It starts with one question.
            <span className="ls-quiet">Not a form.</span>
          </h2>
          <p className="ls-body">
            Say what you're trying to work out, the way you'd say it across a table. A problem, a decision, or something
            you want to start. That's the whole front door.
          </p>
        </Chapter>

        <Chapter state={2}>
          <h2 className="ls-display ls-h2">Then it asks what matters.</h2>
          <p className="ls-body">
            One question at a time, each one following your last answer. Your figures build up beside you as you talk,
            and you can drop in a spreadsheet or an export so it reads the numbers itself.
          </p>
          <ul className="ls-points">
            <li><span><b>Every figure is yours.</b> Nothing is estimated or filled in for you.</span></li>
            <li><span><b>A blank beats a guess.</b> "I don't know" is always an answer.</span></li>
          </ul>
        </Chapter>

        <Chapter state={3}>
          <h2 className="ls-display ls-h2">
            It tests every explanation.
            <span className="ls-quiet">Including yours.</span>
          </h2>
          <p className="ls-body">
            It writes out every cause that fits, tests each one against your own numbers, and hands the strongest to two
            reviewers whose only job is to break it. You watch it happen, live.
          </p>
          <ul className="ls-points">
            <li><span><b>Struck out</b> when your figures rule it out.</span></li>
            <li><span><b>Circled</b> when it survives the reviewers.</span></li>
          </ul>
        </Chapter>

        <Chapter state={4}>
          <h2 className="ls-display ls-h2">Then it tells you the truth.</h2>
          <p className="ls-body">
            The finding in two lines, the evidence in your own numbers, and what fixing it is worth, with the working
            shown. <b>Nothing is built until you've read it.</b>
          </p>
          <ul className="ls-points">
            <li><span><b>Pilot it</b> on Monday, with no software at all.</span></li>
            <li><span><b>Build it,</b> and get the full package in about ten minutes.</span></li>
            <li><span><b>Push back,</b> and it thinks again with what you told it.</span></li>
          </ul>
        </Chapter>

        <Chapter state={5}>
          <h2 className="ls-display ls-h2">
            And designs the system.
            <span className="ls-quiet">Everything, in one package.</span>
          </h2>
          <ul className="ls-points">
            <li><span><b>Your product screens,</b> drawn for your business and checked twice.</span></li>
            <li><span><b>The blueprint and technical plan,</b> in full. More on both next.</span></li>
            <li><span><b>An AI team,</b> with exactly what each one decides alone.</span></li>
            <li><span><b>The operations manual and a Monday plan,</b> so work starts before the code does.</span></li>
          </ul>
        </Chapter>

        <Chapter state={6} deep>
          <h2 className="ls-display ls-h2">
            A blueprint, not a slide deck.
            <span className="ls-quiet">Every decision, with the numbers behind it.</span>
          </h2>
          <p className="ls-body">
            The whole business on paper, written for you: the decision it recommends and why, the financial case worked
            out from your own figures, the customer journey, every module of the product, who does what with humans and
            AI on one chart, what to build first, the scoreboard, and what could make it fail.
          </p>
          <div className="ls-stats">
            <div><b>19</b><span>sections, from the decision to three ways forward</span></div>
            <div><b>Every figure</b><span>traced to one you gave, or marked as ours</span></div>
            <div><b>Honest</b><span>about what could make it fail</span></div>
          </div>
        </Chapter>

        <Chapter state={7} deep>
          <h2 className="ls-display ls-h2">
            A technical plan any team can build from.
            <span className="ls-quiet">Down to the data model.</span>
          </h2>
          <ul className="ls-points">
            <li><span><b>How the system works,</b> end to end, in plain language first.</span></li>
            <li><span><b>Every module:</b> its features, its data model, its screens.</span></li>
            <li><span><b>Every AI agent:</b> what it decides alone, its tools, its guardrails.</span></li>
            <li><span><b>The APIs and integrations,</b> and how your information stays safe.</span></li>
            <li><span><b>The build order,</b> and the checks that say each part is done.</span></li>
          </ul>
          <p className="ls-body">
            Build it with us, with your own team, or with anyone else. <b>The plan is yours either way.</b>
          </p>
        </Chapter>

        <Chapter state={8}>
          <h2 className="ls-display ls-h2">
            For any business.
            <span className="ls-quiet">Running, or about to open.</span>
          </h2>
          <p className="ls-body">
            The questions change with what you do and how far along you are. The rigour doesn't. Every system it designs
            is built around one business: yours.
          </p>
          <div className="ls-kinds">
            {['Clinics', 'Shops', 'Studios', 'Restaurants', 'Logistics', 'Services', 'Professional firms', 'Something new'].map((k) => (
              <span key={k}>{k}</span>
            ))}
          </div>
        </Chapter>

        <Chapter state={9}>
          <h2 className="ls-display ls-h2">
            Free to find out.
            <span className="ls-quiet">Quoted only if you build.</span>
          </h2>
          <div className="ls-stats">
            <div><b>15 min</b><span>to an honest answer</span></div>
            <div><b>$0</b><span>for the answer and the whole package</span></div>
            <div><b>You</b><span>decide whether anything gets built</span></div>
          </div>
          <Ask />
        </Chapter>
      </div>

      <SiteFooter />
    </div>
  );
}
