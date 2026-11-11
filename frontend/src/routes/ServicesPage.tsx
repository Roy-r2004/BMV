/**
 * The services, as shots: the three services together, then each in turn,
 * what a consultation delivers, how fees work and the questions clients ask
 * before starting. The ids `consultation`, `build` and `private-ai` are the
 * anchors the footer and other pages link to.
 */
import { Link } from 'react-router-dom';
import { CloseBand } from '../components/firm/FirmPage';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { BUILD_LINE, CONSULTATION_FEE } from '../data/offer';
import { usePageMeta } from '../utils/pageMeta';

const PACKAGE = [
  {
    title: 'The answer page',
    body: 'The question, the answer in two lines, the figures it rests on, what to do first and what we would not do.',
  },
  {
    title: 'The blueprint',
    body: 'The decision and the reasoning, the financial case worked from your figures, and the recommendation register: each action with its owner, its timing and the range it is worth.',
  },
  {
    title: 'The technical plan',
    body: 'How the system works end to end, each module and AI agent, the integrations, data protection and the build order.',
  },
  {
    title: 'The operations manual',
    body: 'Who does what once the change is made, and how the work runs day to day.',
  },
  {
    title: 'The roadmap',
    body: 'As long as the plan requires, with an owner and a measure for every stage.',
  },
  {
    title: 'The presentation',
    body: 'A deck with the same titles and figures as the documents, ready for a partner, a lender or your team.',
  },
] as const;

const QUESTIONS = [
  {
    q: 'What if my figures cannot support an answer?',
    a: 'We say so on the answer page, and we name the figure that would settle it. We do not fill a gap with a guess presented as fact.',
  },
  {
    q: 'Do I need to prepare anything?',
    a: 'No. The consultation asks for what it needs, one question at a time. A spreadsheet or an export from your systems helps: the figures are read directly from it.',
  },
  {
    q: 'What if the answer is not software?',
    a: 'Then the answer says so, before anything is built. Some questions are settled by a change in pricing, staffing or schedule.',
  },
  {
    q: 'Can I disagree with the answer?',
    a: 'Yes. Write your objection and it is tested against your figures the same way the answer was.',
  },
  {
    q: 'Who keeps the files?',
    a: 'You do. The plan is yours whether you build with us, with your own team or with another firm.',
  },
] as const;

export default function ServicesPage() {
  usePageMeta(
    'Services',
    `A consultation is ${CONSULTATION_FEE} and ends with the answer and six files. System builds and private AI deployments are quoted after the scope is agreed.`,
  );

  return (
    <>
      <Shot title="Three services" first>
        <p className="film-mark">Services</p>
        <Rise as="h1" className="film-h">
          From an idea to a working business, *in three services.*
        </Rise>
        <p className="film-body">
          Bring an idea and we test it, plan it and build it for you. Bring a business that already runs and we do the
          same for the decision in front of it. If your data must stay inside your business, we run the AI there.
        </p>
        <div className="film-svc">
          <div>
            <b>Consultation</b>
            <span className="p big">{CONSULTATION_FEE}</span>
          </div>
          <div>
            <b>We build it for you</b>
            <span className="p">Quoted after the scope is agreed</span>
          </div>
          <div>
            <b>Private AI</b>
            <span className="p">Quoted after the workload is assessed</span>
          </div>
        </div>
        <div className="film-actions">
          <Link to="/demo" className="film-pill">
            Start a consultation
          </Link>
          <Link to="/solutions" className="film-pill film-pill--ghost">
            See what we build
          </Link>
        </div>
      </Shot>

      <Shot tone="dark" title="Consultation" id="consultation">
        <p className="film-mark">01 · Consultation · {CONSULTATION_FEE}</p>
        <Rise className="film-h2">Whether the idea's numbers work, *and the full plan.*</Rise>
        <p className="film-body">
          You describe the idea, or the problem or decision your business faces. We ask what the answer depends on, test it
          against your figures and published ones, and deliver the answer with six files.
        </p>
        <ul className="film-bullets">
          <li>Every figure labelled with its source</li>
          <li>The strongest explanation tested by two reviewers</li>
          <li>Your objections tested the same way</li>
        </ul>
        <div className="film-actions">
          <Link to="/demo" className="film-pill">
            Start a consultation
          </Link>
          <Link to="/approach" className="film-link">
            How a consultation is run
          </Link>
        </div>
      </Shot>

      <Shot tone="dark" title="The build" id="build">
        <p className="film-mark">02 · Quoted after the scope is agreed</p>
        <Rise className="film-h2">We build it *for you.*</Rise>
        <p className="film-body">
          We build what the plan describes, in the order it sets, with the checks that show each part is complete, then
          launch it and hand it over.
        </p>
        <ul className="film-bullets">
          <li>Websites, apps, bookings and payments</li>
          <li>AI assistants, agents and automation</li>
          <li>Launched and handed over with the operations manual</li>
        </ul>
        <div className="film-actions">
          <Link to="/solutions" className="film-link">
            See example systems
          </Link>
        </div>
      </Shot>

      <Shot tone="dark" title="Private AI" id="private-ai">
        <p className="film-mark">03 · Quoted after the workload is assessed</p>
        <Rise className="film-h2">Private AI, *inside your walls.*</Rise>
        <p className="film-body">
          For data that must stay inside your business, we run open-weight models on infrastructure you control and connect
          them to your own systems.
        </p>
        <ul className="film-bullets">
          <li>Model, hardware and security designed per workload</li>
          <li>Deployed in your environment</li>
          <li>Operated by you, without platform lock-in</li>
        </ul>
        <div className="film-actions">
          <Link to="/private-ai" className="film-link">
            How private AI works
          </Link>
        </div>
      </Shot>

      <Shot title="What you receive" wide>
        <p className="film-mark">04 · What a consultation delivers</p>
        <Rise className="film-h2">Six files, each opening with *the same answer.*</Rise>
        <p className="film-body">
          Every page is titled with what it found, so a reader who stops after the titles still has the argument.
        </p>
        <ul className="film-rows">
          {PACKAGE.map((p, i) => (
            <li key={p.title}>
              <b>0{i + 1}</b>
              <div>
                <strong>{p.title}</strong>
                <span>{p.body}</span>
              </div>
            </li>
          ))}
        </ul>
        <p className="film-sub">When the answer is to build software, the package also shows the system, screen by screen, before a line of it is written.</p>
      </Shot>

      <Shot title="Fees">
        <p className="film-mark">05 · How fees work</p>
        <Rise className="film-h2">One price to start. *The rest is quoted.*</Rise>
        <p className="film-body">{BUILD_LINE}</p>
        <dl className="film-facts">
          <div>
            <dt>Consultation</dt>
            <dd>{CONSULTATION_FEE}, for the answer and all six files</dd>
          </div>
          <div>
            <dt>System build</dt>
            <dd>Quoted after we agree the scope with you</dd>
          </div>
          <div>
            <dt>Private AI</dt>
            <dd>Quoted after we assess the workload and the environment</dd>
          </div>
        </dl>
      </Shot>

      <Shot title="Questions" wide>
        <p className="film-mark">06 · Questions clients ask before starting</p>
        <Rise className="film-h2">Before you *start.*</Rise>
        <ul className="film-rows">
          {QUESTIONS.map((x, i) => (
            <li key={x.q}>
              <b>Q.0{i + 1}</b>
              <div>
                <strong>{x.q}</strong>
                <span>{x.a}</span>
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <CloseBand />
    </>
  );
}
