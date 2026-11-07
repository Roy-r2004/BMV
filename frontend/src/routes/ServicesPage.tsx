import { Link } from 'react-router-dom';
import { CloseBand, FirmPage, PageHero, Section } from '../components/firm/FirmPage';
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
    <FirmPage>
      <PageHero
        kicker="Services"
        title="From an idea to a working business, in three services"
        lede="Bring an idea and we test it, plan it and build it for you. Bring a business that already runs and we do the same for the decision in front of it. If your data must stay inside your business, we run the AI there."
        actions={
          <>
            <Link to="/demo" className="fm-btn">
              Start a consultation
            </Link>
            <Link to="/solutions" className="fm-btn-line">
              See what we build
            </Link>
          </>
        }
      />

      <section className="fm-section">
        <div className="fm-wrap">
          <div className="fm-cols">
            <article className="fm-col" id="consultation">
              <h3>Consultation</h3>
              <p className="fm-col-price">{CONSULTATION_FEE}</p>
              <p>
                You describe the idea, or the problem or decision your business faces. We ask what the answer depends
                on, test it against your figures and published ones, and deliver the answer with six files.
              </p>
              <ul>
                <li>Every figure labelled with its source</li>
                <li>The strongest explanation tested by two reviewers</li>
                <li>Your objections tested the same way</li>
              </ul>
              <Link to="/approach" className="fm-link">
                How a consultation is run
              </Link>
            </article>

            <article className="fm-col" id="build">
              <h3>We build it for you</h3>
              <p className="fm-col-price">Quoted after the scope is agreed</p>
              <p>
                We build what the plan describes, in the order it sets, with the checks that show each part is
                complete, then launch it and hand it over.
              </p>
              <ul>
                <li>Websites, apps, bookings and payments</li>
                <li>AI assistants, agents and automation</li>
                <li>Launched and handed over with the operations manual</li>
              </ul>
              <Link to="/solutions" className="fm-link">
                See example systems
              </Link>
            </article>

            <article className="fm-col" id="private-ai">
              <h3>Private AI</h3>
              <p className="fm-col-price">Quoted after the workload is assessed</p>
              <p>
                For data that must stay inside your business, we run open-weight models on infrastructure you control and
                connect them to your own systems.
              </p>
              <ul>
                <li>Model, hardware and security designed per workload</li>
                <li>Deployed in your environment</li>
                <li>Operated by you, without platform lock-in</li>
              </ul>
              <Link to="/private-ai" className="fm-link">
                How private AI works
              </Link>
            </article>
          </div>
        </div>
      </section>

      <Section
        mist
        split
        title="What a consultation delivers"
        intro="Six files, each opening with the same answer. Every page is titled with what it found, so a reader who stops after the titles still has the argument."
      >
        <ul className="fm-rows">
          {PACKAGE.map((p) => (
            <li key={p.title}>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </li>
          ))}
        </ul>
        <p className="fm-p" style={{ marginTop: '1.5rem' }}>
          When the answer is to build software, the package also shows <b>the system, screen by screen</b>, before a line
          of it is written.
        </p>
      </Section>

      <Section split title="How fees work" intro={BUILD_LINE}>
        <dl className="fm-facts">
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
      </Section>

      <Section mist split title="Questions clients ask before starting">
        <ul className="fm-rows">
          {QUESTIONS.map((x) => (
            <li key={x.q}>
              <h3>{x.q}</h3>
              <p>{x.a}</p>
            </li>
          ))}
        </ul>
      </Section>

      <CloseBand />
    </FirmPage>
  );
}
