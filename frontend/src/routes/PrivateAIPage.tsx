/**
 * Private AI, as shots over the light field: the model inside a boundary the
 * business owns, why companies choose it, the four steps of a deployment,
 * cloud against private (the visitor switches and watches where each request
 * goes), and the honest fit. The enquiry opens the visitor's email app with
 * the questions the firm needs answered.
 */
import { useState } from 'react';
import { consultingEmailUrl } from '../api/client';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { usePageMeta } from '../utils/pageMeta';

const CONTACT_SUBJECT = 'Private AI deployment';
const CONTACT_BODY =
  "Hi,\n\nI'd like to discuss a private AI deployment.\n\nMy business: \nWhat the AI needs to do: \nData it touches: \n";

const WHY = [
  { title: 'Data stays private', body: 'Sensitive information can remain inside infrastructure controlled by your business.' },
  { title: 'Control the model', body: 'Choose and customize open-weight models around your actual workload.' },
  { title: 'Predictable economics', body: 'For sustained workloads, dedicated infrastructure can replace variable API costs.' },
  { title: 'No platform lock-in', body: 'You own the deployment and can continue operating it independently.' },
] as const;

const HOW = [
  {
    title: 'We understand the workload.',
    body: 'We identify what the AI needs to do, what data it touches, latency requirements, integrations, security requirements, and expected usage.',
  },
  {
    title: 'We design the stack.',
    body: 'We select the model, inference architecture, hardware requirements, storage, security boundaries, and integrations.',
  },
  { title: 'We deploy it into your environment.', body: 'The system runs on dedicated infrastructure controlled by your business.' },
  {
    title: 'We integrate it with the business.',
    body: 'We connect it to your internal software, workflows, databases, permissions, and human review.',
  },
] as const;

type Mode = 'cloud' | 'private';
const ROWS: Record<Mode, readonly string[]> = {
  cloud: ['Fastest to launch', 'Great for experimentation', 'Usage-based pricing', 'Third-party infrastructure'],
  private: ['Dedicated deployment', 'Greater infrastructure control', 'Predictable high-volume economics', 'Designed for sensitive workloads'],
};
const MODE_READ: Record<Mode, string> = {
  cloud: 'Cloud: each request leaves your environment and runs on a provider’s servers.',
  private: 'Private: requests go from your application to the model and back without leaving your boundary.',
};

export default function PrivateAIPage() {
  usePageMeta('Private AI', 'Private AI on infrastructure you own and control, for when data, compliance, cost or latency justify it.');
  const [mode, setMode] = useState<Mode>('private');
  const email = consultingEmailUrl(CONTACT_SUBJECT, CONTACT_BODY);

  return (
    <>
      <Shot shape="vault" title="Your AI" first>
        <p className="film-mark">Private AI</p>
        <Rise as="h1" className="film-h">
          Private AI on infrastructure *your business owns* and controls.
        </Rise>
        <p className="film-body">
          For businesses that need tighter control over sensitive data, we deploy private AI systems on dedicated
          infrastructure you own and control.
        </p>
        <div className="film-actions">
          <a href={email} className="film-pill">
            Discuss a private deployment
          </a>
        </div>
        <p className="film-sub">You own the deployment, and you can run it without us.</p>
      </Shot>

      <Shot shape="vaultdots" title="Why private" wide>
        <p className="film-mark">01 · Why private</p>
        <Rise className="film-h2">Why companies choose *private AI.*</Rise>
        <ul className="film-grid2">
          {WHY.map((w) => (
            <li key={w.title}>
              <b>{w.title}</b>
              <span>{w.body}</span>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot shape="timeline4" title="How it works" id="how-it-works" wide>
        <p className="film-mark">02 · How it works</p>
        <Rise className="film-h2">Four steps, *into your environment.*</Rise>
        <ul className="film-rows">
          {HOW.map((h, i) => (
            <li key={h.title}>
              <b>0{i + 1}</b>
              <div>
                <strong>{h.title}</strong>
                <span>{h.body}</span>
              </div>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot shape={mode === 'cloud' ? 'cloudflow' : 'privateflow'} title="Cloud or private">
        <p className="film-mark">03 · Cloud AI vs private AI</p>
        <Rise className="film-h2">Watch where *each request goes.*</Rise>
        <div className="film-seg" role="group" aria-label="Deployment to show">
          {(['cloud', 'private'] as const).map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}>
              {m === 'cloud' ? 'Cloud AI' : 'Private AI'}
            </button>
          ))}
        </div>
        <p className="film-body" aria-live="polite">
          {MODE_READ[mode]}
        </p>
        <ul className="film-bullets">
          {ROWS[mode].map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p className="film-body">
          <strong>Owning the infrastructure changes the cost structure.</strong> Rather than permanently paying an AI
          provider a margin on every request, suitable workloads can run on infrastructure you own. Ongoing costs come from
          infrastructure operation, electricity, maintenance, and the support arrangement you choose.
        </p>
        <p className="film-sub">You choose the hardware and control the environment. We design, deploy and integrate the system.</p>
      </Shot>

      <Shot shape="loose" title="Honest fit">
        <p className="film-mark">04 · Honest fit</p>
        <Rise className="film-h2">The right choice for some workloads, *not all of them.*</Rise>
        <p className="film-body">
          Private AI makes the most sense when data sensitivity, compliance, high sustained usage, latency, or infrastructure
          control justify it. For other projects, cloud models may be faster and more economical.
        </p>
        <p className="film-sub">We recommend the deployment the requirement calls for.</p>
      </Shot>

      <Shot shape="vault" title="Talk to us">
        <p className="film-mark">05 · Talk to us</p>
        <Rise className="film-h2">Tell us what the AI needs to do, *and on what data.*</Rise>
        <p className="film-body">
          Tell us what you're trying to run, what data it touches, and what constraints you have. We will tell you whether
          private AI makes sense for it, and what it would take to deploy.
        </p>
        <div className="film-actions">
          <a href={email} className="film-pill">
            Discuss a private AI deployment
          </a>
        </div>
        <p className="film-sub">No obligation. Just a technical conversation.</p>
      </Shot>
    </>
  );
}
