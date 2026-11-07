import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { CloseBand } from '../components/firm/FirmPage';
import Team from '../components/firm/Team';
import OperationField from '../components/about/OperationField';
import { COMPANY } from '../data/company';
import '../styles/about.css';

import { usePageMeta } from '../utils/pageMeta';
// One scroll story: every chapter below is also a shape in OperationField,
// matched by `data-state`. Keep CHAPTERS, CAPTIONS and the sections in step.
// After the story, the firm itself: the people behind the method, and its facts.
const CHAPTERS = [
  'The firm',
  'Useful AI',
  'Four disciplines',
  'Principles',
  'What we build',
  'Engagements',
  'Deployment',
  'Start',
] as const;

// What the picture shows in each chapter, in one line.
const CAPTIONS = [
  'The operation sits in the middle. The AI is the ring around it.',
  'Most of what is sold as AI is noise. A small part does real work.',
  'Four disciplines on one spine, in one engagement.',
  'The work comes before any model is chosen.',
  'Six areas of a business we design systems for.',
  'Loose at diagnosis. Solid by the time you own it.',
  'Three ways to run it, chosen per workload.',
  'The part of the business that should work better.',
] as const;

const DISCIPLINES = [
  { title: 'Business', body: 'Where AI creates value in this business, and where it does not.' },
  { title: 'Product', body: 'Software the people in the business will actually use.' },
  { title: 'AI', body: 'The models and agents behind it, with their limits stated.' },
  { title: 'Infrastructure', body: 'Cloud, private or your own environment, as the requirement dictates.' },
] as const;

const PRINCIPLES = [
  {
    title: 'We start with the work, not the technology.',
    body: 'If ordinary software solves the problem better, we recommend ordinary software.',
  },
  {
    title: 'We prove before we scale.',
    body: 'A working system measured in the real business teaches more than months of workshops.',
  },
  {
    title: 'We build for ownership.',
    body: 'The software, the knowledge and the infrastructure become part of your business, not a dependency on us.',
  },
] as const;

const BUILD_AREAS = [
  { title: 'Operations', items: 'Workflow automation, internal tools, document processing' },
  { title: 'Customer', items: 'Support systems, sales intelligence, personalisation' },
  { title: 'Knowledge', items: 'Search across your own documents, knowledge workflows' },
  { title: 'Decision making', items: 'Forecasting, analysis, recommendations' },
  { title: 'AI systems', items: 'Agents that carry a task from start to finish' },
  { title: 'Private AI', items: 'Open-weight models, on-premises deployment, data residency' },
] as const;

const ENGAGEMENT = [
  { title: 'Diagnose', body: 'The consultation: your question, your figures and a tested answer.' },
  { title: 'Prove', body: 'A working version, measured in the real business.' },
  { title: 'Build', body: 'The full system, engineered for reliability and security.' },
  { title: 'Hand over', body: 'Your team runs it, with the operations manual.' },
] as const;

const DEPLOYMENT = [
  { title: 'Cloud', body: 'Fast to launch and to scale. Suited to variable workloads and early versions.' },
  { title: 'Private', body: 'Dedicated infrastructure for sensitive data, latency or control requirements.' },
  { title: 'Hybrid', body: 'Cloud and private together, each used for the workload it suits.' },
] as const;

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
  usePageMeta(
    'About',
    `${COMPANY.name} is an AI consultancy registered in Dubai. Its method was written by consultants and built by engineers. We start with the business and choose the technology last.`,
  );
  const storyRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState(0);

  const goTo = (i: number) => {
    const el = storyRef.current?.querySelector(`[data-state="${i}"]`);
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: window.innerWidth < 1024 ? 'start' : 'center' });
  };
  const toTeam = () => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.getElementById('team')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
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
          <p className="about-kicker">About the firm</p>
          <h1 className="about-display about-h1">An AI consultancy that starts inside the business</h1>
          <p className="about-lede">
            We begin with the work, the bottlenecks and the economics of the business in front of us. The technology is
            chosen last, and only where it pays for itself.
          </p>
          <p className="about-firm">
            {COMPANY.name} is registered in Dubai, United Arab Emirates. Its method was written by consultants and built by engineers.
          </p>
          <div className="about-actions">
            <Link to="/demo" className="about-cta">
              Start a consultation
            </Link>
            <button type="button" className="about-ghost" onClick={toTeam}>
              Who built the method
            </button>
          </div>
        </Chapter>

        <Chapter state={1}>
          <h2 className="about-display about-h2">Most of what is sold as AI does not change how a business performs</h2>
          <p className="about-body">
            Agents, copilots and transformation roadmaps are often sold before anyone has studied how the business
            works. We work in a different order.
          </p>
          <ol className="about-order">
            <li>Understand the operation.</li>
            <li>Prove the opportunity against the figures.</li>
            <li>Build only what the figures justify.</li>
          </ol>
        </Chapter>

        <Chapter state={2}>
          <h2 className="about-display about-h2">Business, product, AI and infrastructure in one engagement</h2>
          <dl className="about-defs">
            {DISCIPLINES.map((t) => (
              <div key={t.title}>
                <dt>{t.title}</dt>
                <dd>{t.body}</dd>
              </div>
            ))}
          </dl>
          <p className="about-body">
            The engagement that diagnoses the problem carries it through to production. Nothing is handed to another
            firm in between.
          </p>
        </Chapter>

        <Chapter state={3}>
          <h2 className="about-display about-h2">The principles we hold to</h2>
          <ul className="about-beliefs">
            {PRINCIPLES.map((b) => (
              <li key={b.title}>
                <h3 className="about-display">{b.title}</h3>
                <p>{b.body}</p>
              </li>
            ))}
          </ul>
        </Chapter>

        <Chapter state={4}>
          <h2 className="about-display about-h2">We design systems across six areas of a business</h2>
          <p className="about-body">
            From internal operations to the customer's experience: the systems that make work faster and decisions
            better.
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
            See example systems
          </Link>
        </Chapter>

        <Chapter state={5} id="process">
          <h2 className="about-display about-h2">How an engagement runs</h2>
          <ol className="about-process">
            {ENGAGEMENT.map((p, i) => (
              <li key={p.title}>
                <b className="about-display">{i + 1}</b>
                <div>
                  <h3 className="about-display">{p.title}</h3>
                  <p>{p.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <Link to="/approach" className="about-link">
            Read how a consultation is run
          </Link>
        </Chapter>

        <Chapter state={6}>
          <h2 className="about-display about-h2">Cloud when it suits the workload, private when the data requires it</h2>
          <p className="about-body">
            From leading model providers to open-weight models running in infrastructure you control, we design the
            deployment around the requirement.
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
            How private AI works
          </Link>
        </Chapter>

        <Chapter state={7}>
          <h2 className="about-display about-h2">Bring us the part of the business that should work better</h2>
          <p className="about-lede">We will tell you what AI can change, and what is not worth building.</p>
          <div className="about-actions">
            <Link to="/demo" className="about-cta">
              Start a consultation
            </Link>
            <Link to="/services" className="about-ghost">
              See our services
            </Link>
          </div>
        </Chapter>
      </div>

      <div className="fm-page fm-after-story">
        <Team />

        <section className="fm-section fm-section--mist">
          <div className="fm-wrap">
            <div className="fm-section-head fm-section-head--split">
              <h2 className="fm-h2">The firm</h2>
              <dl className="fm-facts">
                <div>
                  <dt>Name</dt>
                  <dd>
                    {COMPANY.name} ({COMPANY.short})
                  </dd>
                </div>
                <div>
                  <dt>Registered</dt>
                  <dd>Dubai, United Arab Emirates</dd>
                </div>
                <div>
                  <dt>Services</dt>
                  <dd>
                    <Link to="/services">Consultation, system builds and private AI</Link>
                  </dd>
                </div>
                <div>
                  <dt>Contact</dt>
                  <dd>
                    <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      </div>

      <CloseBand />
      <SiteFooter />
    </div>
  );
}
