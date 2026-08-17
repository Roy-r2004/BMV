import { motion } from 'framer-motion';

const ICONS = {
  users:
    'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z',
  map: 'M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3',
  bars: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
  target:
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0 0v-3.75m0-10.5V3m9 9h-3.75M6.75 12H3m12.75 0a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z',
  search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
  bulb: 'M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18',
  code: 'M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25',
  rocket:
    'M15.59 14.37a6 6 0 0 1-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 0 0 6.16-12.12A14.98 14.98 0 0 0 9.631 8.41m5.96 5.96a14.926 14.926 0 0 1-5.841 2.58m-.119-8.54a6 6 0 0 0-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 0 0-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 0 1-2.448-2.448 14.9 14.9 0 0 1 .06-.312m-2.24 2.39a4.493 4.493 0 0 0-1.757 4.306 4.493 4.493 0 0 0 4.306-1.758M16.5 9a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z',
  doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
  check: 'M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

function CardShell({
  no,
  title,
  body,
  leave,
  tinted,
  delay,
  children,
}: {
  no: string;
  title: string;
  body: string;
  leave: string;
  tinted?: boolean;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay, duration: 0.5 }}
      className={`flex flex-col rounded-2xl border p-6 ${
        tinted
          ? 'border-blue-100 bg-gradient-to-b from-blue-50/70 to-white'
          : 'border-slate-200 bg-white'
      } shadow-[0_16px_40px_-30px_rgba(15,23,42,0.4)]`}
    >
      <div className="flex items-center gap-3 mb-3">
        <span className="w-9 h-9 rounded-full border border-blue-200 bg-white text-blue-600 font-bold text-sm flex items-center justify-center">
          {no}
        </span>
        <h3 className="font-bold text-navy text-[17px]">{title}</h3>
      </div>
      <p className="text-sm text-slate-600 leading-relaxed mb-5">{body}</p>
      <div className="flex-1">{children}</div>
      <div className="mt-5 pt-4 border-t border-slate-200/70 flex items-start gap-2.5">
        <Icon path={ICONS.check} className="w-4.5 h-4.5 w-[18px] h-[18px] shrink-0 text-blue-600 mt-0.5" />
        <p className="text-[13px] text-slate-600 leading-snug">
          <strong className="text-navy">You leave with:</strong> {leave}
        </p>
      </div>
    </motion.div>
  );
}

const DISCOVER_FLOW = [
  { icon: ICONS.users, label: 'Discover', sub: 'Stakeholders & goals' },
  { icon: ICONS.map, label: 'Map', sub: 'Processes & data' },
  { icon: ICONS.bars, label: 'Assess', sub: 'Tools & workflows' },
  { icon: ICONS.target, label: 'Define', sub: 'Constraints & success' },
] as const;

// Illustrative sketch labels — deliberately generic capabilities, not a
// fake analysis of anyone's business.
const OPP_DOTS = [
  { n: 1, x: 78, y: 22, r: 9, label: 'Instant replies' },
  { n: 2, x: 34, y: 34, r: 7, label: 'Follow-up automation' },
  { n: 3, x: 70, y: 62, r: 8, label: 'Smart scheduling' },
  { n: 4, x: 22, y: 74, r: 6, label: 'Reporting' },
  { n: 5, x: 42, y: 82, r: 6, label: 'Knowledge assistant' },
] as const;

const PLAN_PHASES = [
  { icon: ICONS.search, label: 'Diagnose' },
  { icon: ICONS.bulb, label: 'Prototype' },
  { icon: ICONS.code, label: 'Integrate' },
  { icon: ICONS.rocket, label: 'Launch' },
] as const;

export default function WhatYoullGet() {
  return (
    <section id="how-it-works" className="bg-slate-50 py-16 sm:py-20">
      <div className="container-max px-4 sm:px-6">
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-600 mb-3"
        >
          What you'll get
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.05 }}
          className="font-display text-2xl sm:text-4xl font-bold text-navy mb-10"
        >
          Clarity. Direction. A plan you can act on.
        </motion.h2>

        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-5 items-stretch">
          {/* 01 — deep business analysis */}
          <CardShell
            no="01"
            title="Deep business analysis"
            body="We understand your operations, tools, data and goals."
            leave="a clear understanding of your business and challenges."
            tinted
            delay={0.05}
          >
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="grid grid-cols-4 gap-1.5">
                {DISCOVER_FLOW.map((s, i) => (
                  <div key={s.label} className="relative flex flex-col items-center text-center">
                    {i > 0 && (
                      <span className="absolute -left-2 top-4 text-slate-300 text-[10px]" aria-hidden>
                        →
                      </span>
                    )}
                    <span className="w-9 h-9 rounded-full border border-blue-200 bg-blue-50/60 text-blue-600 flex items-center justify-center mb-1.5">
                      <Icon path={s.icon} className="w-4 h-4" />
                    </span>
                    <p className="text-[11px] font-bold text-navy">{s.label}</p>
                    <p className="text-[9.5px] text-slate-500 leading-tight mt-0.5">{s.sub}</p>
                  </div>
                ))}
              </div>
            </div>
          </CardShell>

          {/* 02 — high-impact opportunities */}
          <CardShell
            no="02"
            title="High-impact opportunities"
            body="We identify, prioritize and size the AI & automation opportunities."
            leave="prioritized opportunities with impact, effort and value."
            tinted
            delay={0.12}
          >
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <svg viewBox="0 0 100 92" className="w-full h-28" aria-hidden="true">
                <path d="M12 4v78h84" fill="none" stroke="#cbd5e1" strokeWidth="1" />
                <path d="M12 43h84M54 4v78" fill="none" stroke="#e2e8f0" strokeWidth="0.8" strokeDasharray="2 2" />
                {OPP_DOTS.map((d) => (
                  <g key={d.n}>
                    <circle cx={d.x} cy={d.y} r={d.r} fill={d.n === 1 ? '#2563eb' : 'rgba(37,99,235,0.18)'} />
                    <text x={d.x} y={d.y + 2.6} textAnchor="middle" fontSize="7" fontWeight="700" fill={d.n === 1 ? '#fff' : '#2563eb'}>
                      {d.n}
                    </text>
                  </g>
                ))}
                <text x="4" y="10" fontSize="6" fill="#94a3b8" transform="rotate(-90 8 46)" textAnchor="middle" />
              </svg>
              <div className="flex justify-between text-[9px] text-slate-400 px-1 -mt-1">
                <span>Impact ↑</span>
                <span>Effort →</span>
              </div>
              <ul className="mt-3 space-y-1.5">
                {OPP_DOTS.map((d) => (
                  <li key={d.n} className="flex items-center gap-2 text-[11px] text-slate-600">
                    <span className={`w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center ${d.n === 1 ? 'bg-blue-600 text-white' : 'bg-blue-100 text-blue-700'}`}>
                      {d.n}
                    </span>
                    {d.label}
                  </li>
                ))}
              </ul>
            </div>
          </CardShell>

          {/* 03 — your custom plan */}
          <CardShell
            no="03"
            title="Your custom plan"
            body="See the recommended solution, approach and build order."
            leave="a clear plan and recommendations you can act on."
            tinted
            delay={0.19}
          >
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="relative grid grid-cols-4 gap-1.5">
                <span className="absolute left-6 right-6 top-[18px] h-px bg-slate-200" aria-hidden />
                {PLAN_PHASES.map((p, i) => (
                  <div key={p.label} className="relative flex flex-col items-center text-center">
                    <span className="w-9 h-9 rounded-full border border-blue-200 bg-white text-blue-600 flex items-center justify-center mb-1.5 relative z-10">
                      <Icon path={p.icon} className="w-4 h-4" />
                    </span>
                    <p className="text-[11px] font-bold text-navy">{p.label}</p>
                    <p className="text-[9.5px] text-slate-500 mt-0.5">Phase {i + 1}</p>
                  </div>
                ))}
              </div>
              {/* Honest note: our plan covers scope/order/team/tools and how
                  it pays — it deliberately never invents ROI figures or
                  calendar durations, so neither does this card. */}
              <div className="mt-4 rounded-lg bg-blue-50/70 border border-blue-100 px-3 py-2.5 flex items-start gap-2">
                <Icon path={ICONS.doc} className="w-4 h-4 shrink-0 text-blue-600 mt-0.5" />
                <p className="text-[11px] text-slate-600 leading-snug">
                  Includes scope, build order, team shape, tools — and how it makes money.
                </p>
              </div>
            </div>
          </CardShell>

          {/* 04 — visual system preview */}
          <CardShell
            no="04"
            title="Visual system preview"
            body="Explore a visual preview of the system we would build for you."
            leave="a preview of the solution tailored to your business."
            delay={0.26}
          >
            {/* dashboard sketch — pure skeleton, no fabricated metrics */}
            <div className="rounded-xl border border-slate-200 overflow-hidden">
              <div className="flex">
                <div className="w-8 bg-[#0a1428] p-1.5 space-y-2">
                  {[0, 1, 2, 3].map((i) => (
                    <span key={i} className="block w-4 h-4 rounded bg-white/10 mx-auto" />
                  ))}
                </div>
                <div className="flex-1 p-3 bg-white">
                  <span className="block h-2 w-24 rounded bg-slate-300 mb-2.5" />
                  <div className="grid grid-cols-4 gap-1.5 mb-2.5">
                    {[0, 1, 2, 3].map((i) => (
                      <span key={i} className="block rounded border border-slate-200 p-1.5">
                        <span className="block h-1.5 w-6 rounded bg-slate-200 mb-1" />
                        <span className="block h-2.5 w-8 rounded bg-blue-200" />
                      </span>
                    ))}
                  </div>
                  <div className="grid grid-cols-[1.5fr_1fr] gap-1.5">
                    <svg viewBox="0 0 100 36" className="w-full rounded border border-slate-200 p-1" aria-hidden>
                      <path d="M4 30 20 24 34 27 50 16 66 20 82 8 96 12" fill="none" stroke="#60a5fa" strokeWidth="1.6" />
                    </svg>
                    <div className="rounded border border-slate-200 p-1.5 space-y-1.5">
                      {['bg-rose-300', 'bg-amber-300', 'bg-emerald-300'].map((c) => (
                        <span key={c} className="flex items-center gap-1">
                          <i className={`w-1.5 h-1.5 rounded-full ${c}`} />
                          <i className="h-1.5 flex-1 rounded bg-slate-200" />
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </CardShell>
        </div>
      </div>
    </section>
  );
}
