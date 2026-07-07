import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

const iconClass = 'w-5 h-5';

export const PRINCIPLES: { title: string; text: string; icon: ReactNode }[] = [
  {
    title: 'Business-first',
    text: 'Every feature maps to a real problem your customers or team face — not tech for tech\'s sake.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
  },
  {
    title: 'AI where it matters',
    text: 'We use AI for intelligence, automation, and personalization — not as a buzzword slapped on a form.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    ),
  },
  {
    title: 'Ship fast',
    text: 'From preview to working MVP in weeks, not months. Iterative, focused, launch-ready.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
  },
  {
    title: 'Original by design',
    text: 'References inspire the workflow — we never copy proprietary code, designs, or brand assets.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
];

export default function AboutPrinciples() {
  return (
    <section className="section-padding bg-white relative overflow-hidden">
      <div className="absolute top-0 right-0 w-1/2 h-1/2 hero-mesh opacity-30 pointer-events-none" />

      <div className="container-max relative">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-14 sm:mb-16"
        >
          <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">Principles</p>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-navy">How we work</h2>
        </motion.div>

        <div className="grid sm:grid-cols-2 gap-4 sm:gap-5">
          {PRINCIPLES.map((v, i) => (
            <motion.div
              key={v.title}
              initial={{ opacity: 0, y: 36 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * 0.08, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              whileHover={{ y: -4 }}
              className="about-gradient-ring about-glass rounded-2xl p-7 sm:p-8 h-full transition-shadow duration-500 hover:shadow-xl hover:shadow-blue-500/10"
            >
              <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center mb-5 shadow-md shadow-blue-500/25">
                {v.icon}
              </div>
              <h3 className="font-bold text-xl text-navy mb-2">{v.title}</h3>
              <p className="text-sm sm:text-base text-slate-600 leading-relaxed">{v.text}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
