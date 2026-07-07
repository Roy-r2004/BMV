import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';

const PROPS = [
  {
    title: 'Free AI preview',
    detail: 'Custom MVP blueprint + visual demo',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.75" aria-hidden>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    title: 'Minutes, not weeks',
    detail: 'AI studies your business & reference fast',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.75" aria-hidden>
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: 'We build it for you',
    detail: 'From preview to working product',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.75" aria-hidden>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function LandingHighlights() {
  return (
    <section className="consultancy-band relative overflow-hidden">
      <div className="consultancy-band__bg" aria-hidden />
      <div className="consultancy-band__grid" aria-hidden />

      <div className="container-max relative px-4 sm:px-6 py-16 sm:py-20 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
          <div>
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, ease }}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/8 border border-cyan-400/25 text-cyan-300 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.18em] mb-6"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              AI consultancy for your business
            </motion.p>

            <motion.h2
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.06, duration: 0.55, ease }}
              className="text-2xl sm:text-3xl lg:text-[2.35rem] font-bold text-white leading-[1.15] tracking-tight"
            >
              Your free consultancy preview
              <span className="block mt-2 text-base sm:text-lg font-medium text-slate-400">
                Show us a tool you like — we&apos;ll scope your custom product.
              </span>
            </motion.h2>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.12, duration: 0.55, ease }}
              className="mt-5 text-sm sm:text-base text-slate-400 leading-relaxed max-w-xl"
            >
              Share any app, dashboard, or workflow you admire. Our AI studies your business and the
              reference, then delivers a custom MVP blueprint and visual preview — in minutes.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.18, duration: 0.55, ease }}
              className="mt-7 flex flex-wrap gap-3"
            >
              <Link
                to="/submit"
                className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white text-sm font-semibold shadow-lg shadow-blue-900/30 hover:shadow-cyan-500/25 transition-shadow"
              >
                Get your free preview
              </Link>
              <Link
                to="/demo"
                className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl border border-white/20 text-slate-200 text-sm font-medium hover:bg-white/5 transition-colors"
              >
                See live demos
              </Link>
            </motion.div>
          </div>

          <div className="flex flex-col gap-3">
            {PROPS.map((p, i) => (
              <motion.div
                key={p.title}
                initial={{ opacity: 0, x: 20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.1 + i * 0.08, duration: 0.5, ease }}
                className="consultancy-prop"
              >
                <div className="consultancy-prop__icon">{p.icon}</div>
                <div className="min-w-0">
                  <p className="consultancy-prop__title">{p.title}</p>
                  <p className="consultancy-prop__detail">{p.detail}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
