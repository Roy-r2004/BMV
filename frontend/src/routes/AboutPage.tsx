import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import OperationField from '../components/about/OperationField';
import '../styles/about.css';

// One scroll story: every chapter below is also a shape in OperationField,
// matched by `data-state`. Keep CHAPTERS, CAPTIONS and the sections in step.
const CHAPTERS = [
  'Around the business',
  'Useful AI',
  'One team',
  'What we believe',
  'What we build',
  'Process',
  'Deployment',
  'Start',
] as const;

// What the picture shows in each chapter, in one line.
const CAPTIONS = [
  'Your operation sits in the middle. The AI is the ring around it.',
  'Most of what gets sold as AI is noise. A small part does real work.',
  'Four disciplines on one spine. Nobody hands the problem off.',
  'The work itself, before any model is chosen.',
  'Six areas of the business we build in.',
  'Loose at diagnosis. Solid by the time you own it.',
  'Three ways to run it, chosen per workload.',
  'Bring us the part that should work better.',
] as const;

const TEAM = [
  { title: 'Business', body: 'We identify where AI can actually create leverage.' },
  { title: 'Product', body: 'We turn the opportunity into software people can use.' },
  { title: 'AI', body: 'We select and engineer the models, agents and intelligence behind it.' },
  { title: 'Infrastructure', body: 'Cloud, private or client-controlled deployment, depending on the requirement.' },
] as const;

const FACTS = [
  { title: 'Full-stack', body: 'Business, product, AI and infrastructure' },
  { title: 'No handoffs', body: 'Diagnosis through production, one team' },
  { title: 'Outcome first', body: 'Success is measured by value delivered' },
] as const;

const BELIEFS = [
  {
    title: "We don't start with AI.",
    body: "We start with the work. If a normal software system solves the problem better, that's what we should build.",
  },
  {
    title: 'We prove before we scale.',
    body: 'A working system in the real environment teaches you more than months of workshops and decks.',
  },
  {
    title: 'We build for ownership.',
    body: 'The software, knowledge and infrastructure should become part of your business, not a permanent dependency on us.',
  },
] as const;

const BUILD_AREAS = [
  { title: 'Operations', items: 'Workflow automation, internal tools, document processing' },
  { title: 'Customer', items: 'Support systems, sales intelligence, personalization' },
  { title: 'Knowledge', items: 'Enterprise search, RAG systems, knowledge workflows' },
  { title: 'Decision making', items: 'Forecasting, analysis, recommendations' },
  { title: 'AI systems', items: 'Agents, model orchestration, multi-step reasoning' },
  { title: 'Private AI', items: 'On-prem deployment, open-weight models, data residency' },
] as const;

const PROCESS = [
  { no: '01', title: 'Diagnose', body: 'We understand the business, the work and the real constraint.' },
  { no: '02', title: 'Prove', body: 'We build a working solution and measure it in the real world.' },
  { no: '03', title: 'Ship', body: 'We engineer the system for reliability, scale and security.' },
  { no: '04', title: 'Own', body: 'We hand it over and support your team to run it.' },
] as const;

const DEPLOYMENT = [
  { title: 'Cloud', body: 'Fast to launch and scale. Good for experimentation and variable workloads.' },
  { title: 'Private', body: 'Dedicated infrastructure for sensitive data, latency or control requirements.' },
  { title: 'Hybrid', body: 'The right combination of cloud and private for the workload.' },
] as const;

function Arrow() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
    </svg>
  );
}

function Chapter({ state, id, children }: { state: number; id?: string; children: React.ReactNode }) {
  return (
    <section className="about-chapter" data-state={state} id={id}>
      <div className="container-max px-4 sm:px-6 w-full">
        <div className="about-col">{children}</div>
      </div>
    </section>
  );
}

export default function AboutPage() {
  const storyRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState(0);

  const goTo = (i: number) => {
    const el = storyRef.current?.querySelector(`[data-state="${i}"]`);
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Narrow screens read a chapter from its top (picture above, panel below).
    el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: window.innerWidth < 1024 ? 'start' : 'center' });
  };

  return (
    <div className="about-page min-h-screen overflow-x-clip">
      <SiteNav />

      <div className="about-story" ref={storyRef}>
        <OperationField storyRef={storyRef} onState={setState}>
          <nav className="about-index" aria-label="Sections on this page">
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
          <p className="about-caption">{CAPTIONS[state]}</p>
        </OperationField>

        <Chapter state={0}>
          <h1 className="about-display about-h1">
            We build AI around the business.
            <span className="about-h1-quiet">Not the other way around.</span>
          </h1>
          <p className="about-lede">
            Most AI projects start with a model and look for somewhere to put it. We start inside the operation: the
            work, the bottlenecks, the economics. Then we build from there.
          </p>
          <p className="about-firm">Strategy, software, models and infrastructure, from one team.</p>
          <div className="about-actions">
            <Link to="/demo" className="about-cta">
              Start with your business
              <Arrow />
            </Link>
            <button type="button" className="about-ghost" onClick={() => goTo(5)}>
              How an engagement runs
            </button>
          </div>
        </Chapter>

        <Chapter state={1}>
          <h2 className="about-display about-h2">AI is everywhere. Useful AI is not.</h2>
          <p className="about-body">
            Companies are being sold agents, copilots, automations and transformation roadmaps before anyone has
            properly understood how their business works.
          </p>
          <p className="about-body">We built BMV around a different order:</p>
          <ol className="about-order">
            <li>Understand the operation first.</li>
            <li>Prove the opportunity.</li>
            <li>Then build what deserves to exist.</li>
          </ol>
        </Chapter>

        <Chapter state={2}>
          <h2 className="about-display about-h2">One team from problem to production.</h2>
          <dl className="about-defs">
            {TEAM.map((t) => (
              <div key={t.title}>
                <dt>{t.title}</dt>
                <dd>{t.body}</dd>
              </div>
            ))}
          </dl>
          <p className="about-body">
            No handoff between strategy consultants, designers, AI engineers and implementation vendors. The people
            diagnosing the problem are the same people responsible for making the solution work.
          </p>
          <div className="about-facts">
            {FACTS.map((f) => (
              <div key={f.title}>
                <b>{f.title}</b>
                <span>{f.body}</span>
              </div>
            ))}
          </div>
        </Chapter>

        <Chapter state={3}>
          <h2 className="about-display about-h2">What we believe</h2>
          <ul className="about-beliefs">
            {BELIEFS.map((b) => (
              <li key={b.title}>
                <h3 className="about-display">{b.title}</h3>
                <p>{b.body}</p>
              </li>
            ))}
          </ul>
        </Chapter>

        <Chapter state={4}>
          <h2 className="about-display about-h2">We build across the operation.</h2>
          <p className="about-body">
            From internal operations to customer experiences, the systems that make work faster, decisions better and
            businesses stronger.
          </p>
          <div className="about-areas">
            {BUILD_AREAS.map((a) => (
              <div key={a.title}>
                <h3 className="about-display">{a.title}</h3>
                <p>{a.items}</p>
              </div>
            ))}
          </div>
          <Link to="/solutions" className="about-link">
            Explore solutions
            <Arrow />
          </Link>
        </Chapter>

        <Chapter state={5} id="process">
          <h2 className="about-display about-h2">How an engagement runs</h2>
          <ol className="about-process">
            {PROCESS.map((p) => (
              <li key={p.no}>
                <b className="about-display">{p.no}</b>
                <div>
                  <h3 className="about-display">{p.title}</h3>
                  <p>{p.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Chapter>

        <Chapter state={6}>
          <h2 className="about-display about-h2">Cloud when it makes sense. Private when it matters.</h2>
          <p className="about-body">
            From leading model APIs to open-weight models running in infrastructure you control, we design deployment
            around the business requirement.
          </p>
          <dl className="about-defs">
            {DEPLOYMENT.map((d) => (
              <div key={d.title}>
                <dt>{d.title}</dt>
                <dd>{d.body}</dd>
              </div>
            ))}
          </dl>
          <Link to="/private-ai" className="about-link">
            Explore Private AI
            <Arrow />
          </Link>
        </Chapter>

        <Chapter state={7}>
          <h2 className="about-display about-h2">Bring us the part of your business that should work better.</h2>
          <p className="about-lede">We'll tell you what AI can change, and what isn't worth building.</p>
          <div className="about-actions">
            <Link to="/demo" className="about-cta">
              Start with your business
              <Arrow />
            </Link>
            <Link to="/solutions" className="about-ghost">
              Explore solutions
            </Link>
          </div>
        </Chapter>
      </div>

      <SiteFooter />
    </div>
  );
}
