import { motion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import GlowButton from '../components/GlowButton';
import SolutionCard from '../components/solutions/SolutionCard';
import { INDUSTRY_SOLUTIONS } from '../data/solutions';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function SolutionsPage() {
  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />

      <section className="about-cinematic-hero relative flex items-center overflow-hidden pt-16 hero-surface">
        <div className="absolute inset-0 hero-mesh pointer-events-none" />
        <div className="absolute inset-0 cinematic-grid opacity-70 pointer-events-none" />
        <div className="hero-blob w-[600px] h-[360px] bg-blue-400/28 -top-28 -right-28" />
        <div className="hero-blob w-[480px] h-[300px] bg-cyan-400/22 -bottom-36 -left-28" />

        <div className="container-max relative z-10 px-4 sm:px-6 w-full py-10 sm:py-12 min-h-0 sm:min-h-[calc(100dvh-4rem)] flex flex-col justify-center text-center">
          <motion.span
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: easeOut }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full about-glass text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.2em] mb-6 mx-auto shadow-sm"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            Our software, industry by industry
          </motion.span>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: easeOut }}
            className="text-4xl sm:text-5xl lg:text-6xl font-bold text-navy tracking-tight mb-5"
          >
            One platform.<br className="hidden sm:block" /> A solution for every industry.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.12, ease: easeOut }}
            className="text-slate-600 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed mb-8"
          >
            Ready-made software for every kind of business — from clinics to barbershops to real estate.
            Pick your industry below to see what's included, then we'll customize and integrate it for you.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: easeOut }}
            className="flex flex-wrap justify-center gap-3"
          >
            <GlowButton to="/demo" className="text-sm px-6 py-3 !inline-block">
              Get this software
            </GlowButton>
          </motion.div>
        </div>
      </section>

      <section className="section-padding bg-slate-50 relative">
        <div className="absolute inset-0 hero-mesh opacity-30 pointer-events-none" />
        <div className="container-max relative">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-10 text-center max-w-2xl mx-auto"
          >
            <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">Our software</p>
            <h2 className="text-2xl sm:text-3xl font-bold text-navy mb-3">
              A solution for every industry
            </h2>
            <p className="text-slate-600 leading-relaxed">
              Each card is software we already have. Click any industry to see the full package —
              what's included, features, and demo — then tell us how to set it up for your business.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {INDUSTRY_SOLUTIONS.map((solution, i) => (
              <SolutionCard key={solution.id} solution={solution} index={i} />
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-14 text-center"
          >
            <p className="text-slate-500 mb-4">Don't see your industry?</p>
            <GlowButton to="/demo" className="text-sm px-6 py-3 !inline-block">
              Tell us about your business
            </GlowButton>
          </motion.div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
