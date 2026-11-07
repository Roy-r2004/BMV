import { FirmPage, PageHero } from '../components/firm/FirmPage';
import { COMPANY } from '../data/company';
import { usePageMeta } from '../utils/pageMeta';

// Written from what the service actually does. A lawyer must review this text
// before the site goes live; until then it is the firm's plain statement.
const UPDATED = '7 November 2026';

export default function PrivacyPage() {
  usePageMeta('Privacy notice', `How ${COMPANY.name} handles the information you give it.`);
  const mail = <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>;

  return (
    <FirmPage>
      <PageHero kicker="Legal" title="Privacy notice" lede={`How we handle the information you give us. Last updated ${UPDATED}.`} />
      <section className="film-prose">
        <div>
          <h2>Who we are</h2>
          <p>
            {COMPANY.name} ({COMPANY.short}) is an AI consultancy, registered in Dubai, United Arab Emirates. For anything in
            this notice, write to us at {mail}.
          </p>

          <h2>What we collect</h2>
          <ul>
            <li>Your name and email address, when you create an account.</li>
            <li>What you tell us during a consultation, including the files you upload and the figures in them.</li>
            <li>Messages you send to us, by email or through the guide on this site.</li>
            <li>The technical records needed to run and secure the service, such as server logs.</li>
          </ul>
          <p>
            We keep your sign-in in your browser's storage so that you stay signed in. We do not use advertising or
            tracking cookies.
          </p>

          <h2>How we use it</h2>
          <ul>
            <li>To run your consultation and produce your answer and files.</li>
            <li>To reply to you and to deliver the services you ask for.</li>
            <li>To operate, secure and improve the service.</li>
          </ul>

          <h2>AI providers</h2>
          <p>
            A consultation is processed by AI models from third-party providers, which we use through their services.
            We send them what the consultation needs to answer your question, and nothing else.
          </p>

          <h2>Sharing</h2>
          <p>
            We do not sell your information. If you create a share link for your results, anyone with that link can view
            them until you withdraw it.
          </p>

          <h2>Your choices</h2>
          <p>
            You can ask us for a copy of the information we hold about you, ask us to correct it, or ask us to delete a
            consultation or your account. Write to {mail}.
          </p>

          <h2>Changes to this notice</h2>
          <p>When we change this notice, we update the date at the top of this page.</p>
        </div>
      </section>
    </FirmPage>
  );
}
