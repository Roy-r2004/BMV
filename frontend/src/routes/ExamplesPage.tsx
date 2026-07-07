import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import CinematicCTA from '../components/CinematicCTA';
import ExampleCard from '../components/ExampleCard';
import ExamplesHero from '../components/examples/ExamplesHero';
import ExamplesManifesto from '../components/examples/ExamplesManifesto';
import { EXAMPLE_OUTPUTS, INDUSTRIES } from '../data/examples';

export default function ExamplesPage() {
  const [filter, setFilter] = useState('All');
  const featured = EXAMPLE_OUTPUTS[0];
  const filtered = EXAMPLE_OUTPUTS.filter(
    (e) => filter === 'All' || e.industry === filter
  ).filter((e) => e.id !== featured.id);

  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />
      <ExamplesHero />
      <ExamplesManifesto />

      <section className="section-padding bg-white relative">
        <div className="absolute inset-0 hero-mesh opacity-30 pointer-events-none" />
        <div className="container-max relative">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-8"
          >
            <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">Spotlight</p>
            <h2 className="text-2xl sm:text-3xl font-bold text-navy">Featured concept</h2>
          </motion.div>

          <ExampleCard example={featured} featured />

          <div className="mt-16 mb-10">
            <motion.p
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              className="text-center text-xs font-bold text-blue-600 uppercase tracking-[0.2em] mb-5"
            >
              Filter by industry
            </motion.p>
            <div className="flex flex-wrap gap-2 justify-center">
              {INDUSTRIES.map((ind) => (
                <button
                  key={ind}
                  type="button"
                  onClick={() => setFilter(ind)}
                  className={`px-4 py-2.5 rounded-full text-sm font-medium border transition-all duration-300 ${
                    filter === ind
                      ? 'border-blue-500 bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-lg shadow-blue-500/25 scale-[1.03]'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:bg-blue-50 about-glass'
                  }`}
                >
                  {ind}
                </button>
              ))}
            </div>
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={filter}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
              className="grid md:grid-cols-2 lg:grid-cols-3 gap-5"
            >
              {filtered.map((ex, i) => (
                <ExampleCard key={ex.id} example={ex} index={i} />
              ))}
            </motion.div>
          </AnimatePresence>

          {filtered.length === 0 && (
            <p className="text-center text-slate-500 py-12">No examples in this category yet.</p>
          )}
        </div>
      </section>

      <CinematicCTA
        eyebrow="Your concept"
        title="Want your own version?"
        subtitle="Share a tool you like and get a custom MVP blueprint with visual demo — free, in minutes."
      />
      <SiteFooter />
    </div>
  );
}
