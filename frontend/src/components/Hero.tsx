import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

// Heroicons-24-outline paths.
const ICONS = {
  building:
    'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
  search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
  cpu: 'M8.25 3v1.5M15.75 3v1.5M8.25 19.5V21M15.75 19.5V21M3 8.25H1.5M3 12H1.5M3 15.75H1.5M22.5 8.25H21M22.5 12H21M22.5 15.75H21M6.75 19.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v10.5a2.25 2.25 0 0 0 2.25 2.25Zm3-9h4.5v4.5h-4.5V9.75Z',
  bolt: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  check: 'M4.5 12.75l6 6 9-13.5',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const STEPS = [
  {
    icon: ICONS.building,
    title: 'Your business',
    body: 'We learn how your business operates',
    sub: 'Data, tools, people, workflows',
    hot: false,
  },
  {
    icon: ICONS.search,
    title: 'BMV analyzes',
    body: 'We find where AI creates the most value',
    sub: 'Automation, augmentation or new systems',
    hot: false,
  },
  {
    icon: ICONS.cpu,
    title: 'AI plan',
    body: 'We design the right solution for your context',
    sub: 'Prioritized opportunities and expected impact',
    hot: true,
  },
  {
    icon: ICONS.bolt,
    title: 'Your version',
    body: 'You get a preview of the system we would build',
    sub: 'Visual preview + implementation plan',
    hot: true,
  },
] as const;

// What a run genuinely produces — never invented ROI figures. The reference
// mockup carried "$1.2M+ savings / 2-3x ROI"; this pipeline deliberately
// never fabricates currency or percentage outcomes, so the strip states
// real deliverables instead.
const PRODUCES = [
  { num: '~4 min', label: 'From intake to plan' },
  { num: '3+', label: 'Product screens' },
  { num: '4', label: 'Documents & deck' },
  { num: '100%', label: 'Human oversight' },
] as const;

export default function Hero() {
  return (
    <section className="relative overflow-hidden bg-[#050d1f] text-white">
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.35]"
        style={{
          background:
            'radial-gradient(900px 480px at 75% 0%, rgba(37,99,235,0.35), transparent 60%), radial-gradient(700px 420px at 10% 80%, rgba(34,211,238,0.16), transparent 60%)',
        }}
      />
      <div className="container-max relative px-4 sm:px-6 pt-24 sm:pt-28 pb-20 grid lg:grid-cols-[0.85fr_1.15fr] gap-12 lg:gap-10 items-center">
        {/* ── copy ── */}
        <div>
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-[11px] font-bold uppercase tracking-[0.3em] text-blue-400 mb-5"
          >
            AI strategy + build
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.06, duration: 0.6 }}
            className="font-display text-5xl sm:text-6xl lg:text-[4.4rem] font-extrabold leading-[0.98] tracking-tight"
          >
            Build My
            <br />
            <span className="bg-gradient-to-r from-blue-500 via-blue-400 to-cyan-400 bg-clip-text text-transparent">
              Version.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.14, duration: 0.55 }}
            className="mt-6 text-xl sm:text-2xl font-bold text-slate-100 leading-snug max-w-md"
          >
            We find the AI &amp; automation your business actually needs.
          </motion.p>
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.55 }}
            className="mt-4 text-slate-400 leading-relaxed max-w-md"
          >
            We analyze how your business works, identify high-impact opportunities, and build a
            custom plan — with a preview of the system we would build for you.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.28, duration: 0.55 }}
            className="mt-8 flex flex-wrap items-center gap-5"
          >
            <Link
              to="/demo"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 px-6 py-3.5 font-bold text-white shadow-lg shadow-blue-600/30 hover:shadow-blue-500/40 hover:-translate-y-0.5 transition-all"
            >
              See my AI opportunity
              <span aria-hidden>→</span>
            </Link>
            <span className="flex items-center gap-2.5 text-sm text-slate-300">
              <span className="w-6 h-6 rounded-full border-2 border-cyan-400 text-cyan-400 flex items-center justify-center">
                <Icon path={ICONS.check} className="w-3.5 h-3.5" />
              </span>
              No commitment.
              <br className="sm:hidden" /> Just clarity.
            </span>
          </motion.div>
        </div>

        {/* ── the live-preview mockup ── */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.7 }}
          className="rounded-2xl border border-white/10 bg-[#0a1428] shadow-[0_40px_100px_-40px_rgba(37,99,235,0.5)] overflow-hidden"
        >
          {/* browser chrome */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
            <span className="flex gap-1.5">
              <i className="w-2.5 h-2.5 rounded-full bg-red-400" />
              <i className="w-2.5 h-2.5 rounded-full bg-amber-400" />
              <i className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
            </span>
            <span className="flex-1 max-w-md rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs text-slate-400">
              buildmyversion.com/preview
            </span>
            <span className="ml-auto text-[10px] font-bold tracking-[0.2em] text-cyan-400">
              LIVE PREVIEW
            </span>
          </div>
          {/* app nav */}
          <div className="flex items-center gap-5 px-5 py-3 border-b border-white/5 text-sm">
            <img src="/logo.png" alt="" className="w-7 h-7 rounded-full" />
            {['Overview', 'Analysis', 'AI Opportunities', 'Your Version'].map((t, i) => (
              <span
                key={t}
                className={
                  i === 0
                    ? 'text-white font-semibold border-b-2 border-cyan-400 pb-0.5'
                    : 'text-slate-500 hidden sm:inline'
                }
              >
                {t}
              </span>
            ))}
          </div>

          <div className="p-5">
            <p className="font-bold text-lg mb-4">Your AI opportunity</p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {STEPS.map((s) => (
                <div
                  key={s.title}
                  className={`rounded-xl border p-3.5 ${
                    s.hot
                      ? 'border-cyan-400/50 bg-cyan-400/[0.04] shadow-[0_0_30px_-12px_rgba(34,211,238,0.5)]'
                      : 'border-white/10 bg-white/[0.02]'
                  }`}
                >
                  <span
                    className={`inline-flex w-8 h-8 items-center justify-center rounded-lg border mb-2.5 ${
                      s.hot ? 'border-cyan-400/40 text-cyan-300' : 'border-white/15 text-slate-300'
                    }`}
                  >
                    <Icon path={s.icon} className="w-4 h-4" />
                  </span>
                  <p className="text-[10px] font-bold tracking-[0.14em] uppercase text-slate-200">
                    {s.title}
                  </p>
                  <p className="mt-1.5 text-[11px] text-slate-400 leading-snug">{s.body}</p>
                  <p className="mt-2 text-[10px] text-slate-500 leading-snug">{s.sub}</p>
                </div>
              ))}
            </div>

            {/* wave art */}
            <svg viewBox="0 0 600 70" className="w-full h-14 mt-2" aria-hidden="true">
              {[
                'M0 55 C120 20 210 62 300 40 S 480 10 600 34',
                'M0 62 C140 34 230 68 320 48 S 500 22 600 44',
                'M0 48 C100 12 240 55 340 32 S 470 4 600 26',
              ].map((d, i) => (
                <path
                  key={i}
                  d={d}
                  fill="none"
                  stroke={`rgba(56,189,248,${0.5 - i * 0.15})`}
                  strokeWidth="1.2"
                />
              ))}
              {[80, 190, 300, 420, 530].map((x, i) => (
                <circle key={x} cx={x} cy={[50, 40, 38, 26, 33][i]} r="2" fill="#38bdf8" />
              ))}
            </svg>

            {/* what a run produces — real deliverables, never invented ROI */}
            <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3.5">
              <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-slate-500 mb-2.5">
                What a run produces
              </p>
              <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
                {PRODUCES.map((m) => (
                  <div key={m.label}>
                    <p className="font-display text-xl font-extrabold text-cyan-300">{m.num}</p>
                    <p className="text-[11px] text-slate-500">{m.label}</p>
                  </div>
                ))}
                <Link
                  to="/demo"
                  className="ml-auto inline-flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors px-4 py-2.5 text-sm font-bold"
                >
                  View your preview <span aria-hidden>→</span>
                </Link>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* scroll cue */}
      <div className="relative pb-8 flex flex-col items-center gap-3">
        <span className="w-6 h-10 rounded-full border-2 border-slate-600 flex justify-center pt-1.5">
          <motion.i
            animate={{ y: [0, 6, 0] }}
            transition={{ duration: 1.6, repeat: Infinity }}
            className="w-1 h-2 rounded-full bg-cyan-400"
          />
        </span>
        <p className="text-[10px] font-bold tracking-[0.3em] uppercase text-slate-500">
          Explore what's inside
        </p>
      </div>
    </section>
  );
}
