/**
 * The firm, as shots: what it is, the order it works in, its four disciplines
 * and principles, the six areas it designs systems for, how an engagement
 * runs, where the AI is deployed, and the consultants and engineers behind
 * the method. Only facts the firm has confirmed: no names, photos, headcount
 * or former employers. The ids `team` and `process` are linked from other pages.
 */
import { Link } from 'react-router-dom';
import { CloseBand } from '../components/firm/FirmPage';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { COMPANY } from '../data/company';
import { usePageMeta } from '../utils/pageMeta';

const DISCIPLINES = [
  { title: 'Business', body: 'Where AI creates value in this business, and where it does not.' },
  { title: 'Product', body: 'Software the people in the business will actually use.' },
  { title: 'AI', body: 'The models and agents behind it, with their limits stated.' },
  { title: 'Infrastructure', body: 'Cloud, private or your own environment, as the requirement dictates.' },
] as const;

const PRINCIPLES = [
  { title: 'We start with the work, not the technology.', body: 'If ordinary software solves the problem better, we recommend ordinary software.' },
  { title: 'We prove before we scale.', body: 'A working system measured in the real business teaches more than months of workshops.' },
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

export default function AboutPage() {
  usePageMeta(
    'About',
    `${COMPANY.name} is an AI consultancy registered in Dubai. Its method was written by consultants and built by engineers. We start with the business and choose the technology last.`,
  );

  return (
    <>
      <Shot shape="ring" title="The firm" first>
        <p className="film-mark">About the firm</p>
        <Rise as="h1" className="film-h">
          An AI consultancy that turns ideas into *working businesses.*
        </Rise>
        <p className="film-body">
          We begin with the idea or the business in front of us: how it will earn, what it will cost and what has to work.
          Then we build what it needs, choosing the technology last and only where it pays for itself.
        </p>
        <div className="film-actions">
          <Link to="/demo" className="film-pill">
            Start a consultation
          </Link>
          <Link to="/about#team" className="film-pill film-pill--ghost">
            Who built the method
          </Link>
        </div>
        <p className="film-sub">
          {COMPANY.name} is registered in Dubai, United Arab Emirates. Its method was written by consultants and built by
          engineers.
        </p>
      </Shot>

      <Shot shape="loose" title="Useful AI">
        <p className="film-mark">01 · A different order</p>
        <Rise className="film-h2">Most of what is sold as AI *does not change how a business performs.*</Rise>
        <p className="film-body">
          Agents, copilots and transformation roadmaps are often sold before anyone has studied how the business works. We
          work in a different order.
        </p>
        <ul className="film-rows">
          <li>
            <b>01</b>
            <span>Understand the operation.</span>
          </li>
          <li>
            <b>02</b>
            <span>Prove the opportunity against the figures.</span>
          </li>
          <li>
            <b>03</b>
            <span>Build only what the figures justify.</span>
          </li>
        </ul>
      </Shot>

      <Shot shape="four" title="Four disciplines" wide>
        <p className="film-mark">02 · Four disciplines</p>
        <Rise className="film-h2">Business, product, AI and infrastructure *in one engagement.*</Rise>
        <ul className="film-grid2">
          {DISCIPLINES.map((d) => (
            <li key={d.title}>
              <b>{d.title}</b>
              <span>{d.body}</span>
            </li>
          ))}
        </ul>
        <p className="film-sub">The engagement that diagnoses the problem carries it through to production. Nothing is handed to another firm in between.</p>
      </Shot>

      <Shot shape="trio" title="Principles" wide>
        <p className="film-mark">03 · Principles</p>
        <Rise className="film-h2">The principles *we hold to.*</Rise>
        <ul className="film-rows">
          {PRINCIPLES.map((p, i) => (
            <li key={p.title}>
              <b>0{i + 1}</b>
              <div>
                <strong>{p.title}</strong>
                <span>{p.body}</span>
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot shape="hexa" title="What we build" wide>
        <p className="film-mark">04 · What we build</p>
        <Rise className="film-h2">We design systems across *six areas of a business.*</Rise>
        <ul className="film-grid2">
          {BUILD_AREAS.map((a) => (
            <li key={a.title}>
              <b>{a.title}</b>
              <span>{a.items}</span>
            </li>
          ))}
        </ul>
        <div className="film-actions">
          <Link to="/solutions" className="film-link">
            See example systems
          </Link>
        </div>
      </Shot>

      <Shot shape="solid" title="Engagements" id="process" wide>
        <p className="film-mark">05 · How an engagement runs</p>
        <Rise className="film-h2">Loose at diagnosis. *Solid by the time you own it.*</Rise>
        <ul className="film-rows">
          {ENGAGEMENT.map((p) => (
            <li key={p.title}>
              <b>{p.title}</b>
              <span>{p.body}</span>
            </li>
          ))}
        </ul>
        <div className="film-actions">
          <Link to="/approach" className="film-link">
            Read how a consultation is run
          </Link>
        </div>
      </Shot>

      <Shot shape="privateflow" title="Deployment" wide>
        <p className="film-mark">06 · Deployment</p>
        <Rise className="film-h2">Cloud when it suits the workload, *private when the data requires it.*</Rise>
        <p className="film-body">
          From leading model providers to open-weight models running in infrastructure you control, we design the
          deployment around the requirement.
        </p>
        <ul className="film-rows">
          {DEPLOYMENT.map((d) => (
            <li key={d.title}>
              <b>{d.title}</b>
              <span>{d.body}</span>
            </li>
          ))}
        </ul>
        <div className="film-actions">
          <Link to="/private-ai" className="film-link">
            How private AI works
          </Link>
        </div>
      </Shot>

      <Shot shape="four" title="The people" id="team" wide>
        <p className="film-mark">07 · Who built the method</p>
        <Rise className="film-h2">Built by *consultants and engineers.*</Rise>
        <p className="film-body">
          The method behind every consultation was written by consultants and built into software by engineers. Each rule
          in it comes from engagement experience: what a business’s own figures can prove, where an estimate misleads, and
          which recommendations hold up once a business acts on them.
        </p>
        <ul className="film-rows">
          {ROLES.map((r) => (
            <li key={r.title}>
              <b>{r.title}</b>
              <span>{r.body}</span>
            </li>
          ))}
        </ul>
        <dl className="film-facts">
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
      </Shot>

      <CloseBand
        title="Bring us the idea, or the part of the business that *should work better.*"
        body="We will tell you whether its numbers work, what is worth building, and then build it."
      />
    </>
  );
}
