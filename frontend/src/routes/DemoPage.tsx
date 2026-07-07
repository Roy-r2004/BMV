import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import CinematicCTA from '../components/CinematicCTA';
import DemoCard from '../components/demo/DemoCard';
import GlowButton from '../components/GlowButton';
import { listDemos } from '../api/demos';
import type { DemoListItem } from '../types/demo';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function DemoPage() {
  const [demos, setDemos] = useState<DemoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await listDemos();
        if (active) setDemos(data.demos);
      } catch {
        if (active) setError('Could not load live demos.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const featured = demos[0];
  const rest = demos.slice(1);

  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />

      <section className="about-cinematic-hero relative flex items-center overflow-hidden pt-16 hero-surface">
        <div className="absolute inset-0 hero-mesh pointer-events-none" />
        <div className="absolute inset-0 cinematic-grid opacity-70 pointer-events-none" />
        <div className="hero-blob w-[600px] h-[360px] bg-blue-400/28 -top-28 -right-28" />
        <div className="hero-blob w-[480px] h-[300px] bg-cyan-400/22 -bottom-36 -left-28" />

        <div className="container-max relative z-10 px-4 sm:px-6 w-full py-12 min-h-[calc(100dvh-4rem)] flex flex-col justify-center text-center">
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
            Live generated products
          </motion.span>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: easeOut }}
            className="text-4xl sm:text-5xl lg:text-6xl font-bold text-navy tracking-tight mb-5"
          >
            Real demos, built by AI
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.12, ease: easeOut }}
            className="text-slate-600 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed mb-8"
          >
            Every completed submission appears here automatically. Open any demo to browse the interactive product.
            Create your own version to get the AI refine chatbot and unlimited revisions.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: easeOut }}
          >
            <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-block">
              Create yours
            </GlowButton>
          </motion.div>
        </div>
      </section>

      <section className="section-padding bg-slate-50 relative">
        <div className="absolute inset-0 hero-mesh opacity-30 pointer-events-none" />
        <div className="container-max relative">
          {loading && (
            <div className="flex flex-col items-center justify-center py-24 text-slate-500">
              <div className="w-12 h-12 border-2 border-indigo-200 border-t-indigo-500 rounded-full animate-spin mb-4" />
              Loading live demos…
            </div>
          )}

          {error && (
            <p className="text-center text-red-500 py-16">{error}</p>
          )}

          {!loading && !error && demos.length === 0 && (
            <div className="text-center py-20">
              <p className="text-slate-600 mb-6">No live demos yet — be the first to generate one.</p>
              <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-block">
                Create my version
              </GlowButton>
            </div>
          )}

          {!loading && !error && featured && (
            <>
              <div className="mb-10">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400 mb-4">Latest demo</p>
                <DemoCard demo={featured} featured />
              </div>

              {rest.length > 0 && (
                <>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400 mb-4">
                    All demos ({demos.length})
                  </p>
                  <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                    {rest.map((demo, i) => (
                      <DemoCard key={demo.id} demo={demo} index={i} />
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </section>

      <CinematicCTA
        eyebrow="Your turn"
        title="Want your own live product?"
        subtitle="Share a tool you like and get a custom MVP with interactive demo — free, in minutes."
      />
      <SiteFooter />
    </div>
  );
}
