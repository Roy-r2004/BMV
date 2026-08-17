import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { whatsappUrl } from '../api/client';
import '../styles/private-ai.css';

// Heroicons-24-outline paths.
const ICONS = {
  lock: 'M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z',
  cube: 'M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9',
  chart:
    'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
  shield:
    'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
  stack:
    'M8.25 3v1.5M15.75 3v1.5M8.25 19.5V21M15.75 19.5V21M3 8.25H1.5M3 12H1.5M3 15.75H1.5M22.5 8.25H21M22.5 12H21M22.5 15.75H21M6.75 19.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v10.5a2.25 2.25 0 0 0 2.25 2.25Zm3-9h4.5v4.5h-4.5V9.75Z',
  server:
    'M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 3.75v3.75m-16.5-3.75v3.75',
  puzzle:
    'M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 0 1-.657.643 48.39 48.39 0 0 1-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 0 1-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 0 0-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 0 1-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 0 0 .657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 0 1-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 0 0 5.427-.63 48.05 48.05 0 0 0 .582-4.717.532.532 0 0 0-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 0 0 .658-.663 48.422 48.422 0 0 0-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 0 1-.61-.58v0Z',
  chevronDown: 'm19.5 8.25-7.5 7.5-7.5-7.5',
  bolt: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  check: 'M4.5 12.75l6 6 9-13.5',
  users:
    'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z',
  code: 'M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const WHY_CARDS = [
  {
    icon: ICONS.lock,
    title: 'Data stays private',
    body: 'Sensitive information can remain inside infrastructure controlled by your business.',
  },
  {
    icon: ICONS.cube,
    title: 'Control the model',
    body: 'Choose and customize open-weight models around your actual workload.',
  },
  {
    icon: ICONS.chart,
    title: 'Predictable economics',
    body: 'For sustained workloads, dedicated infrastructure can replace variable API costs.',
  },
  {
    icon: ICONS.shield,
    title: 'No platform lock-in',
    body: 'You own the deployment and can continue operating it independently.',
  },
] as const;

const HOW_STEPS = [
  {
    icon: ICONS.search,
    title: 'We understand the workload',
    body: 'We identify what the AI needs to do, what data it touches, latency requirements, integrations, security requirements, and expected usage.',
  },
  {
    icon: ICONS.stack,
    title: 'We design the stack',
    body: 'We select the model, inference architecture, hardware requirements, storage, security boundaries, and integrations.',
  },
  {
    icon: ICONS.server,
    title: 'We deploy it into your environment',
    body: 'The system runs on dedicated infrastructure controlled by your business.',
  },
  {
    icon: ICONS.puzzle,
    title: 'We integrate it with the business',
    body: 'We connect it to your internal software, workflows, databases, permissions, and human review.',
  },
] as const;

const CLOUD_ROWS = ['Fastest to launch', 'Great for experimentation', 'Usage-based pricing', 'Third-party infrastructure'];
const PRIVATE_ROWS = [
  'Dedicated deployment',
  'Greater infrastructure control',
  'Predictable high-volume economics',
  'Designed for sensitive workloads',
];

const CONTACT_MESSAGE = "Hi, I'd like to discuss a private AI deployment.";

/** Team / application / private model / data — the same "who talks to what"
 *  shape as the hero diagram, closer up and inside the client's boundary. */
function IntegrationDiagram() {
  return (
    <div className="pai-flow">
      <div className="pai-flow-node">
        <Icon path={ICONS.users} className="pai-flow-icon" />
        <p>Your team</p>
      </div>
      <span className="pai-flow-arrow" aria-hidden="true">
        ⟷
      </span>
      <div className="pai-flow-node">
        <Icon path={ICONS.code} className="pai-flow-icon" />
        <p>Your application</p>
      </div>
      <span className="pai-flow-arrow" aria-hidden="true">
        ⟷
      </span>
      <div className="pai-flow-node pai-flow-node--core">
        <Icon path={ICONS.cube} className="pai-flow-icon" />
        <p>Private AI model</p>
        <span className="pai-flow-node-tag">
          <Icon path={ICONS.lock} className="w-3 h-3" />
          Your environment / security boundary
        </span>
      </div>
      <span className="pai-flow-arrow" aria-hidden="true">
        ⟷
      </span>
      <div className="pai-flow-node">
        <Icon path={ICONS.server} className="pai-flow-icon" />
        <p>Your data</p>
      </div>
    </div>
  );
}

export default function PrivateAIPage() {
  return (
    <div className="pai-page">
      <SiteNav />
      <div className="pai-grid-field" aria-hidden="true" />

      <main className="relative z-10">
        {/* ── hero ──────────────────────────────────────────────────────── */}
        <section className="pai-section pt-32 sm:pt-36 pb-16">
          <div className="container-max max-w-6xl grid lg:grid-cols-[0.8fr_1.2fr] gap-10 lg:gap-12 items-center">
            <div>
              <span className="pai-pill mb-4 lg:hidden">
                <Icon path={ICONS.lock} className="w-3.5 h-3.5" />
                Your data. Under your control.
              </span>
              <p className="pai-kicker mb-5">Private AI</p>
              <h1 className="pai-display text-5xl sm:text-6xl font-bold leading-[1.05] text-white">
                Your AI.
                <br />
                Your data.
                <br />
                Your infrastructure.
              </h1>
              <p className="mt-6 text-slate-400 text-lg max-w-lg leading-relaxed">
                For businesses that need tighter control over sensitive data, we deploy private AI
                systems on dedicated infrastructure you own and control.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <a href={whatsappUrl(CONTACT_MESSAGE)} target="_blank" rel="noopener noreferrer" className="pai-cta">
                  Explore a private deployment
                  <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />
                </a>
                <a href="#how-it-works" className="pai-ghost-btn">
                  How it works
                  <Icon path={ICONS.chevronDown} className="w-3.5 h-3.5" />
                </a>
              </div>
              <p className="mt-6 flex items-center gap-2 text-sm text-slate-500">
                <Icon path={ICONS.lock} className="w-4 h-4" />
                No forced cloud dependency. No per-token lock-in.
              </p>
            </div>

            {/* Conceptual illustration of the CLIENT's environment — every
                label on it names infrastructure the client owns and
                controls, never a BMV facility. */}
            <img
              src="/private-ai-environment.png"
              alt="Your environment: your data and applications connected to a private AI model running on infrastructure you own, inside a security boundary"
              className="pai-hero-image"
            />
          </div>
        </section>

        {/* ── why companies choose private ai ─────────────────────────────── */}
        <section className="pai-section py-16 border-t border-white/5">
          <div className="container-max max-w-6xl">
            <p className="pai-kicker mb-8">Why companies choose private AI</p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {WHY_CARDS.map((c) => (
                <div className="pai-card" key={c.title}>
                  <span className="pai-card-icon">
                    <Icon path={c.icon} className="w-4.5 h-4.5" />
                  </span>
                  <h3>{c.title}</h3>
                  <p>{c.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── how it works ─────────────────────────────────────────────── */}
        <section className="pai-section py-16 border-t border-white/5" id="how-it-works">
          <div className="container-max max-w-6xl">
            <p className="pai-kicker mb-10">How it works</p>
            <div className="pai-steps">
              {HOW_STEPS.map((s, i) => (
                <div className="pai-step" key={s.title}>
                  <div className="pai-step-head">
                    <span className="pai-step-no">{String(i + 1).padStart(2, '0')}</span>
                    <Icon path={s.icon} className="pai-step-icon" />
                  </div>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                  {i < HOW_STEPS.length - 1 && (
                    <span className="pai-step-connector" aria-hidden="true">
                      →
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div className="mt-14">
              <IntegrationDiagram />
            </div>
          </div>
        </section>

        {/* ── cloud vs private ─────────────────────────────────────────── */}
        <section className="pai-section py-16 border-t border-white/5">
          <div className="container-max max-w-6xl grid lg:grid-cols-2 gap-12 items-start">
            <div>
              <p className="pai-kicker mb-8">Cloud AI vs private AI</p>
              <div className="pai-compare">
                <div className="pai-compare-col">
                  <div className="pai-compare-head">
                    <Icon path="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z" className="w-4.5 h-4.5" />
                    <h3>Cloud AI</h3>
                  </div>
                  <ul>
                    {CLOUD_ROWS.map((r) => (
                      <li key={r}>
                        <Icon path={ICONS.check} className="w-3.5 h-3.5" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
                <span className="pai-compare-vs">VS</span>
                <div className="pai-compare-col pai-compare-col--core">
                  <div className="pai-compare-head">
                    <Icon path={ICONS.server} className="w-4.5 h-4.5" />
                    <h3>Private AI</h3>
                  </div>
                  <ul>
                    {PRIVATE_ROWS.map((r) => (
                      <li key={r}>
                        <Icon path={ICONS.check} className="w-3.5 h-3.5" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <div>
              <p className="pai-kicker mb-4">
                Own the infrastructure.
                <br />
                Pay for the compute you actually use.
              </p>
              <p className="text-slate-400 leading-relaxed">
                Rather than permanently paying an AI provider a margin on every request, suitable
                workloads can run on infrastructure you own. Ongoing costs come from infrastructure
                operation, electricity, maintenance, and the support arrangement you choose.
              </p>
              <div className="pai-quote mt-6">
                <Icon path={ICONS.bolt} className="w-5 h-5" />
                <p>You decide the hardware. You control the environment. We architect, deploy, and integrate it.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── honest framing ───────────────────────────────────────────── */}
        <section className="pai-section py-16 border-t border-white/5">
          <div className="container-max max-w-6xl grid lg:grid-cols-2 gap-12 items-start">
            <div>
              <p className="pai-kicker mb-4">Not every workload should be local</p>
              <p className="text-slate-300 leading-relaxed">
                Private AI makes the most sense when data sensitivity, compliance, high sustained
                usage, latency, or infrastructure control justify it.
              </p>
              <p className="mt-3 text-slate-500 leading-relaxed">
                For other projects, cloud models may be faster and more economical.
              </p>
            </div>
            <div className="pai-quote pai-quote--shield">
              <Icon path={ICONS.shield} className="w-5 h-5" />
              <p>We design around the business requirement — not around one deployment ideology.</p>
            </div>
          </div>
        </section>

        {/* ── bottom cta ────────────────────────────────────────────────── */}
        <section className="pai-section py-16 border-t border-white/5 pb-24">
          <div className="container-max max-w-6xl">
            <div className="pai-panel flex flex-col lg:flex-row lg:items-center justify-between gap-8 p-8 sm:p-10">
              <div className="max-w-xl">
                <h2 className="pai-display text-2xl sm:text-3xl font-bold text-white mb-3">
                  Need AI that stays under your control?
                </h2>
                <p className="text-slate-400 leading-relaxed">
                  Tell us what you're trying to run, what data it touches, and what constraints you
                  have. We'll tell you whether private AI actually makes sense and what it would
                  take to deploy.
                </p>
              </div>
              <div className="shrink-0 flex flex-col items-start lg:items-end gap-3">
                <a href={whatsappUrl(CONTACT_MESSAGE)} target="_blank" rel="noopener noreferrer" className="pai-cta">
                  Discuss a private AI deployment
                  <Icon path="M17 8l4 4m0 0l-4 4m4-4H3" className="w-4 h-4" />
                </a>
                <p className="flex items-center gap-2 text-sm text-slate-500">
                  <Icon path={ICONS.lock} className="w-4 h-4" />
                  No obligation. Just a technical conversation.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
