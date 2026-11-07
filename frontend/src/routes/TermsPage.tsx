import { Link } from 'react-router-dom';
import { FirmPage, PageHero } from '../components/firm/FirmPage';
import { COMPANY } from '../data/company';
import { BUILD_LINE, CONSULTATION_FEE } from '../data/offer';
import { usePageMeta } from '../utils/pageMeta';

// Written from what the service actually does. A lawyer must review this text
// before the site goes live; until then it is the firm's plain statement.
const UPDATED = '7 November 2026';

export default function TermsPage() {
  usePageMeta('Terms of engagement', `The terms on which ${COMPANY.name} provides a consultation.`);

  return (
    <FirmPage>
      <PageHero
        kicker="Legal"
        title="Terms of engagement"
        lede={`The terms on which we provide a consultation. Last updated ${UPDATED}.`}
      />
      <section className="fm-section">
        <div className="fm-wrap fm-prose">
          <h2>The consultation</h2>
          <p>
            A consultation is {CONSULTATION_FEE}. It starts with your question and ends with the answer and six files:
            the answer page, the blueprint, the technical plan, the operations manual, the roadmap and the presentation.
            The method is described on our <Link to="/approach">approach page</Link>.
          </p>

          <h2>Your information</h2>
          <p>
            The answer rests on the figures you give us. Every figure is labelled with its source, and every estimate of
            ours is marked as an estimate. Where your figures cannot support an answer, we say so instead of giving one.
          </p>

          <h2>The nature of the advice</h2>
          <p>
            We prepare the analysis and the plan; every decision stays yours. A consultation is business advice. It is
            not legal, tax, medical or regulated financial advice, and it does not replace a licensed professional where
            one is required.
          </p>

          <h2>Your files</h2>
          <p>The files we deliver are yours to use in your business. {BUILD_LINE}</p>

          <h2>Builds and private AI</h2>
          <p>
            A system build or a private AI deployment is agreed separately, with its own scope and quote, before any work
            starts.
          </p>

          <h2>Questions</h2>
          <p>
            Write to <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>. {COMPANY.name} is{' '}
            registered in Dubai, United Arab Emirates.
          </p>
        </div>
      </section>
    </FirmPage>
  );
}
