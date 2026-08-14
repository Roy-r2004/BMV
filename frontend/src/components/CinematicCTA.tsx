import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';

const TRUST = ['AI consultancy', 'Find what to automate', 'We build it'];

interface Props {
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  primaryLabel?: string;
  primaryTo?: string;
  secondaryLabel?: string;
  secondaryTo?: string;
}

export default function CinematicCTA({
  eyebrow = 'AI consultancy',
  title = 'Ready to find what your business should automate?',
  subtitle = 'Tell us how you work. We map the AI opportunities, show a free preview, then our team builds the real product.',
  primaryLabel = 'Find my AI fit',
  primaryTo = '/demo',
  secondaryLabel = 'Browse examples',
  secondaryTo = '/examples',
}: Props) {
  return (
    <section className="landing-cta-band relative py-20 sm:py-28 overflow-hidden text-white">
      <div className="landing-section__grid" aria-hidden />
      <div className="landing-divider absolute top-0 inset-x-0" aria-hidden />

      <div className="container-max relative px-4 sm:px-6 text-center max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/20 text-cyan-100 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.2em] mb-6">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-300 opacity-50" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-200" />
            </span>
            {eyebrow}
          </span>

          <h2 className="text-3xl sm:text-4xl lg:text-[2.85rem] font-bold mb-5 leading-[1.12] tracking-tight">
            {title}
          </h2>

          <p className="text-slate-300 text-base sm:text-lg mb-8 leading-relaxed max-w-xl mx-auto">
            {subtitle}
          </p>

          <div className="flex flex-wrap justify-center gap-2 mb-10">
            {TRUST.map((t) => (
              <span
                key={t}
                className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium text-white/90 bg-white/10 border border-white/15"
              >
                {t}
              </span>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row gap-3 justify-center items-stretch sm:items-center w-full sm:w-auto">
            <Link
              to={primaryTo}
              className="inline-flex items-center justify-center w-full sm:w-auto sm:min-w-[220px] px-8 py-3.5 rounded-xl bg-white text-blue-600 font-bold text-base shadow-lg hover:shadow-xl sm:hover:-translate-y-0.5 transition-all duration-300 min-h-12"
            >
              {primaryLabel}
            </Link>
            <Link
              to={secondaryTo}
              className="inline-flex items-center justify-center w-full sm:w-auto sm:min-w-[200px] px-8 py-3.5 rounded-xl border border-white/35 text-white font-semibold hover:bg-white/10 transition-all duration-300 text-sm sm:text-base min-h-12"
            >
              {secondaryLabel}
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
