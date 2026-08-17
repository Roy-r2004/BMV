import { Link } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import '../styles/about.css';

// Heroicons-24-outline paths, same convention as the other route pages.
const ICONS = {
  target:
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0 0v-3.75m0-10.5V3m9 9h-3.75M6.75 12H3m12.75 0a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z',
  code: 'M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25',
  cog: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  server:
    'M21.75 17.25v-.228a4.5 4.5 0 0 0-.12-1.03l-2.268-9.64a3.375 3.375 0 0 0-3.285-2.602H7.923a3.375 3.375 0 0 0-3.285 2.602l-2.268 9.64a4.5 4.5 0 0 0-.12 1.03v.228m19.5 0a3 3 0 0 1-3 3H5.25a3 3 0 0 1-3-3m19.5 0a3 3 0 0 0-3-3H5.25a3 3 0 0 0-3 3m16.5 0h.008v.008h-.008v-.008Zm-3 0h.008v.008h-.008v-.008Z',
  shield:
    'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  chart:
    'M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941',
  lock: 'M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z',
  layers:
    'M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3',
  users:
    'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z',
  search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
  bars: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
  nodes:
    'M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 0 1-.657.643 48.39 48.39 0 0 1-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 0 1-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 0 0-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 0 1-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 0 0 .657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 0 1-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 0 0 5.427-.63 48.05 48.05 0 0 0 .582-4.717.532.532 0 0 0-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 0 0 .658-.663 48.422 48.422 0 0 0-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 0 1-.61-.58v0Z',
  cloud:
    'M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z',
  hybrid:
    'M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5',
  arrow: 'M17 8l4 4m0 0l-4 4m4-4H3',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const TEAM_COLUMNS = [
  {
    icon: ICONS.target,
    title: 'Business',
    body: 'We identify where AI can actually create leverage.',
  },
  {
    icon: ICONS.code,
    title: 'Product',
    body: 'We turn the opportunity into software people can use.',
  },
  {
    icon: ICONS.cog,
    title: 'AI',
    body: 'We select and engineer the models, agents and intelligence behind it.',
  },
  {
    icon: ICONS.server,
    title: 'Infrastructure',
    body: 'Cloud, private or client-controlled deployment depending on the requirement.',
  },
] as const;

const BELIEFS = [
  {
    icon: ICONS.shield,
    title: "We don't start with AI.",
    body: "We start with the work. If a normal software system solves the problem better, that's what we should build.",
  },
  {
    icon: ICONS.chart,
    title: 'We prove before we scale.',
    body: 'A working system in the real environment teaches you more than months of workshops and decks.',
  },
  {
    icon: ICONS.lock,
    title: 'We build for ownership.',
    body: "The goal isn't to make a client permanently dependent on us. The software, knowledge and infrastructure should become part of their business.",
  },
] as const;

const BUILD_AREAS = [
  {
    icon: ICONS.layers,
    title: 'Operations',
    items: ['Workflow automation', 'Internal tools', 'Document processing'],
  },
  {
    icon: ICONS.users,
    title: 'Customer',
    items: ['Support systems', 'Sales intelligence', 'Personalization'],
  },
  {
    icon: ICONS.search,
    title: 'Knowledge',
    items: ['Enterprise search', 'RAG systems', 'Knowledge workflows'],
  },
  {
    icon: ICONS.bars,
    title: 'Decision making',
    items: ['Forecasting', 'Analysis', 'Recommendations'],
  },
  {
    icon: ICONS.nodes,
    title: 'AI systems',
    items: ['Agents', 'Model orchestration', 'Multi-step reasoning'],
  },
  {
    icon: ICONS.lock,
    title: 'Private AI',
    items: ['On-prem deployment', 'Open-weight models', 'Data residency'],
  },
] as const;

const DEPLOYMENT = [
  {
    icon: ICONS.cloud,
    title: 'Cloud',
    body: 'Fast to launch and scale. Great for experimentation and variable workloads.',
  },
  {
    icon: ICONS.lock,
    title: 'Private',
    body: 'Dedicated infrastructure for sensitive data, latency or control requirements.',
  },
  {
    icon: ICONS.hybrid,
    title: 'Hybrid',
    body: 'The right combination of cloud and private for the workload.',
  },
] as const;

const PROCESS = [
  { no: '01', title: 'Diagnose', body: 'We understand the business, the work and the real constraint.' },
  { no: '02', title: 'Prove', body: 'We build a working solution and measure it in the real world.' },
  { no: '03', title: 'Ship', body: 'We engineer the system for reliability, scale and security.' },
  { no: '04', title: 'Own', body: 'We hand it over and support your team to run it.' },
] as const;

export default function AboutPage() {
  return (
    <div className="about-page min-h-screen overflow-x-hidden bg-white">
      <SiteNav />

      {/* ── 1 · hero — what BMV actually is (dark) ─────────────────────── */}
      <section className="about-dark pt-28 sm:pt-32 pb-16 sm:pb-20">
        <div className="container-max px-4 sm:px-6 grid lg:grid-cols-[1.05fr_1fr] gap-12 lg:gap-16 items-center">
          <div>
            <p className="about-kicker about-kicker--cyan mb-5">About BMV</p>
            <h1 className="about-display text-4xl sm:text-5xl lg:text-[3.4rem] font-bold leading-[1.08] text-white">
              We build AI around the business.
              <br />
              Not the other way around.
            </h1>
            <p className="mt-6 text-slate-400 text-lg max-w-xl leading-relaxed">
              Most AI projects start with a model and search for somewhere to put it. We start
              inside the operation — the work, the bottlenecks, the economics — and build from
              there.
            </p>
            <p className="mt-6 text-slate-200 font-semibold">
              Strategy. Software. Models. Infrastructure.{' '}
              <span className="text-cyan-300">One team.</span>
            </p>
          </div>
          <img
            src="/private-ai-environment.png"
            alt="A business environment: data and applications connected to an AI model inside a controlled boundary"
            className="about-hero-image"
          />
        </div>
      </section>

      {/* ── 2 · manifesto (white, huge, no cards) ───────────────────────── */}
      <section className="py-20 sm:py-24 relative overflow-hidden">
        <div className="container-max px-4 sm:px-6 grid lg:grid-cols-[1fr_1.1fr] gap-12 items-center">
          <div>
            <h2 className="about-display text-4xl sm:text-5xl font-bold leading-[1.1] text-navy">
              AI is everywhere.
              <br />
              <span className="text-blue-600">Useful AI is not.</span>
            </h2>
            <p className="mt-7 text-slate-600 text-lg max-w-xl leading-relaxed">
              Companies are being sold agents, copilots, automations and transformation roadmaps
              before anyone has properly understood how their business actually works.
            </p>
            <p className="mt-6 text-slate-700 font-medium">We built BMV around a different idea:</p>
            <ul className="mt-4 space-y-3">
              {['Understand the operation first.', 'Prove the opportunity.', 'Then build what deserves to exist.'].map(
                (line) => (
                  <li key={line} className="flex items-center gap-4 text-navy font-semibold text-lg">
                    <span className="about-dash" aria-hidden="true" />
                    {line}
                  </li>
                ),
              )}
            </ul>
          </div>
          {/* the operation, as a schematic: the thing we understand first */}
          <div className="about-ops hidden lg:block" aria-hidden="true">
            <svg className="about-ops-lines" viewBox="0 0 560 400">
              <path d="M150 90 L150 150 Q150 170 170 170 L250 170" fill="none" />
              <path d="M430 90 L430 150 Q430 130 410 150 L340 178" fill="none" />
              <path d="M295 230 L295 300" fill="none" />
              <path d="M250 210 L150 210 Q130 210 130 230 L130 280" fill="none" strokeDasharray="4 4" />
              <path d="M340 210 L440 210 Q460 210 460 230 L460 280" fill="none" strokeDasharray="4 4" />
              {[
                [150, 90], [250, 170], [430, 90], [340, 178], [295, 300], [130, 280], [460, 280],
              ].map(([x, y]) => (
                <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />
              ))}
            </svg>
            {[
              { icon: 'users', label: 'Demand', style: { left: '6%', top: '4%' } },
              { icon: 'user', label: 'Customers', style: { right: '4%', top: '4%' } },
              { icon: 'target', label: 'Operations', style: { left: '44%', top: '34%' }, core: true },
              { icon: 'cube', label: 'Inventory', style: { left: '2%', top: '60%' } },
              { icon: 'truck', label: 'Fulfillment', style: { right: '0%', top: '60%' } },
              { icon: 'coin', label: 'Finance', style: { left: '42%', top: '76%' } },
            ].map((n) => (
              <div
                key={n.label}
                className={`about-ops-card${n.core ? ' about-ops-card--core' : ''}`}
                style={n.style}
              >
                <span className={`about-ops-icon about-ops-icon--${n.icon}`} />
                <div>
                  <p>{n.label}</p>
                  <span className="about-ops-skel" />
                  <span className="about-ops-skel about-ops-skel--short" />
                </div>
              </div>
            ))}
            <span className="about-ops-dots" style={{ left: '30%', top: '20%' }} />
            <span className="about-ops-dots" style={{ right: '12%', top: '44%' }} />
            <span className="about-ops-dots" style={{ left: '18%', top: '84%' }} />
          </div>
        </div>

        {/* curved divider with a traveling point */}
        <svg className="about-curve" viewBox="0 0 1200 60" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 10 Q600 60 1200 10" fill="none" />
        </svg>
        <span className="about-curve-dot" aria-hidden="true" />
      </section>

      {/* ── 3 · what we are — breadth (pale) ────────────────────────────── */}
      <section className="about-pale py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6">
          <p className="about-kicker text-center mb-3">What we are</p>
          <h2 className="about-display text-3xl sm:text-4xl font-bold text-navy text-center mb-12">
            One team from problem to production.
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-10 about-columns">
            {TEAM_COLUMNS.map((c) => (
              <div key={c.title} className="about-column">
                <span className="about-column-icon">
                  <Icon path={c.icon} className="w-5 h-5" />
                </span>
                <h3 className="font-bold text-navy mt-4 mb-2">{c.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{c.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-12 text-center text-slate-600 max-w-2xl mx-auto leading-relaxed">
            No handoff between strategy consultants, designers, AI engineers and implementation
            vendors.
            <br className="hidden sm:block" />
            <span className="text-navy font-medium">
              We stay with the problem from first diagnosis through production.
            </span>
          </p>
        </div>
      </section>

      {/* ── 4 · what we believe (dark) ──────────────────────────────────── */}
      <section className="about-dark py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6">
          <p className="about-kicker about-kicker--cyan mb-10">What we believe</p>
          <div className="grid lg:grid-cols-3 about-beliefs">
            {BELIEFS.map((b) => (
              <div key={b.title} className="about-belief">
                <Icon path={b.icon} className="w-7 h-7 text-slate-400 mb-5" />
                <h3 className="about-display text-xl font-bold text-white mb-3">{b.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed max-w-sm">{b.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 5 · what we build (white) ───────────────────────────────────── */}
      <section className="py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6 grid lg:grid-cols-[0.9fr_1.6fr] gap-12 items-start">
          <div>
            <p className="about-kicker mb-3">What we build</p>
            <h2 className="about-display text-3xl sm:text-4xl font-bold leading-tight text-navy">
              We build across
              <br />
              <span className="text-blue-600">the operation.</span>
            </h2>
            <p className="mt-5 text-slate-600 leading-relaxed max-w-sm">
              From internal operations to customer experiences, we build the systems that make work
              faster, decisions better and businesses stronger.
            </p>
            <Link
              to="/examples"
              className="mt-5 inline-flex items-center gap-2 text-blue-600 font-semibold text-sm hover:gap-3 transition-all"
            >
              See our work
              <Icon path={ICONS.arrow} className="w-4 h-4" />
            </Link>
          </div>
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {BUILD_AREAS.map((a) => (
              <div key={a.title} className="about-area">
                <div className="flex items-center gap-3 mb-3">
                  <Icon path={a.icon} className="w-5 h-5 text-slate-500" />
                  <h3 className="font-bold text-navy text-sm">{a.title}</h3>
                </div>
                <ul className="space-y-1.5">
                  {a.items.map((item) => (
                    <li key={item} className="text-[13px] text-slate-500 leading-snug">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 6 · the team (dark) — honest: no invented people or numbers ── */}
      <section className="about-dark py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6 max-w-3xl">
          <p className="about-kicker about-kicker--cyan mb-4">The team</p>
          <h2 className="about-display text-3xl sm:text-4xl font-bold text-white leading-tight">
            Built by people who ship.
          </h2>
          <p className="mt-5 text-slate-400 leading-relaxed max-w-xl">
            We're operators, engineers and problem solvers. A senior team, end to end — the people
            diagnosing the problem are the same people responsible for making the solution work.
          </p>
          <div className="mt-10 grid sm:grid-cols-3 gap-8">
            <div>
              <p className="about-display text-lg font-bold text-cyan-300">Full-stack</p>
              <p className="mt-1 text-sm text-slate-400">Business, product, AI and infrastructure</p>
            </div>
            <div>
              <p className="about-display text-lg font-bold text-cyan-300">No handoffs</p>
              <p className="mt-1 text-sm text-slate-400">Diagnosis through production, one team</p>
            </div>
            <div>
              <p className="about-display text-lg font-bold text-cyan-300">Outcome first</p>
              <p className="mt-1 text-sm text-slate-400">We measure success by value delivered</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── 7 · deployment bridge (white) ───────────────────────────────── */}
      <section className="py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6 grid lg:grid-cols-[0.9fr_1.4fr] gap-12 items-center">
          <div>
            <p className="about-kicker mb-3">Deployment that fits</p>
            <h2 className="about-display text-3xl sm:text-4xl font-bold leading-tight text-navy">
              Cloud when it makes sense.
              <br />
              <span className="text-blue-600">Private when it matters.</span>
            </h2>
            <p className="mt-5 text-slate-600 leading-relaxed max-w-sm">
              From leading model APIs to open-weight models running in infrastructure you control,
              we design deployment around the business requirement.
            </p>
            <Link
              to="/private-ai"
              className="mt-5 inline-flex items-center gap-2 text-blue-600 font-semibold text-sm hover:gap-3 transition-all"
            >
              Explore Private AI
              <Icon path={ICONS.arrow} className="w-4 h-4" />
            </Link>
          </div>
          <div className="grid sm:grid-cols-3 gap-4">
            {DEPLOYMENT.map((d) => (
              <div key={d.title} className="about-area">
                <Icon path={d.icon} className="w-6 h-6 text-slate-500 mb-3" />
                <h3 className="font-bold text-navy text-sm mb-2">{d.title}</h3>
                <p className="text-[13px] text-slate-500 leading-relaxed">{d.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 8 · process, once, thin (white) ─────────────────────────────── */}
      <section className="border-t border-slate-100 py-14">
        <div className="container-max px-4 sm:px-6">
          <p className="about-kicker mb-8">Our process</p>
          <div className="about-process">
            {PROCESS.map((p, i) => (
              <div key={p.no} className="about-process-step">
                <p>
                  <span className="text-blue-600 font-bold">{p.no}</span>{' '}
                  <span className="font-bold text-navy">{p.title}</span>
                </p>
                <p className="mt-1.5 text-[13px] text-slate-500 leading-snug max-w-[180px]">{p.body}</p>
                {i < PROCESS.length - 1 && (
                  <Icon path={ICONS.arrow} className="about-process-arrow" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 9 · final cta (dark) ────────────────────────────────────────── */}
      <section className="about-dark py-16 sm:py-20">
        <div className="container-max px-4 sm:px-6 flex flex-col lg:flex-row lg:items-center justify-between gap-10">
          <div className="max-w-xl">
            <h2 className="about-display text-3xl sm:text-4xl font-bold text-white leading-tight">
              Bring us the part of your business that should work better.
            </h2>
            <p className="mt-4 text-slate-400 leading-relaxed">
              We'll tell you what AI can change — and what isn't worth building.
            </p>
          </div>
          <div className="shrink-0 flex flex-col sm:flex-row lg:flex-col gap-3">
            <Link to="/demo" className="about-cta">
              Start with your business
              <Icon path={ICONS.arrow} className="w-4 h-4" />
            </Link>
            <Link to="/examples" className="about-ghost">
              See our work
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
