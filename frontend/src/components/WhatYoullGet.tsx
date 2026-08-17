import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

const ICONS = {
  target:
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0 0v-3.75m0-10.5V3m9 9h-3.75M6.75 12H3m12.75 0a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z',
  nodes:
    'M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5',
  doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
  monitor:
    'M9 17.25v1.007a3 3 0 0 1-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0 1 15 18.257V17.25m6-12V15a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 15V5.25m18 0A2.25 2.25 0 0 0 18.75 3H5.25A2.25 2.25 0 0 0 3 5.25m18 0V12a2.25 2.25 0 0 1-2.25 2.25H5.25A2.25 2.25 0 0 1 3 12V5.25',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const CARDS = [
  {
    icon: ICONS.target,
    title: 'Deep business analysis',
    body: 'We understand your operations, tools, data and goals.',
  },
  {
    icon: ICONS.nodes,
    title: 'High-impact opportunities',
    body: 'We identify, prioritize and size the AI & automation opportunities.',
  },
  {
    icon: ICONS.doc,
    title: 'Your custom plan',
    body: 'See the recommended solution, approach and build order.',
  },
  {
    // "Visual", not the reference's "Interactive" — the preview is real
    // product screens and documents, not a clickable prototype (yet).
    icon: ICONS.monitor,
    title: 'Visual system preview',
    body: 'Explore a visual preview of the system we would build for you.',
  },
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
          className="font-display text-2xl sm:text-3xl font-bold text-navy mb-10"
        >
          Clarity. Direction. A plan you can act on.
        </motion.h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {CARDS.map((c, i) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.08 + i * 0.07 }}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_14px_34px_-26px_rgba(15,23,42,0.35)]"
            >
              <span className="inline-flex w-12 h-12 items-center justify-center rounded-xl bg-blue-600/10 border border-blue-600/15 text-blue-600 mb-4">
                <Icon path={c.icon} className="w-6 h-6" />
              </span>
              <h3 className="font-bold text-navy mb-2">{c.title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed mb-4">{c.body}</p>
              <Link
                to="/demo"
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600 hover:gap-2.5 transition-all"
              >
                Learn more <span aria-hidden>→</span>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
