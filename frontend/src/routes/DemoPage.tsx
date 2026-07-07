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
const heroLines = ['Not mockups.', 'Live products.', 'Built in minutes.'];

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
    <div className="min-h-screen bg-[#060a14] overflow-x-hidden">
      <SiteNav />

      <section className="demo-hero relative overflow-hidden pt-16">
        <div className="absolute inset-0 demo-hero__mesh pointer-events-none" />
        <div className="absolute inset-0 cinematic-grid opacity-30 pointer-events-none" />
        <div className="hero-blob w-[700px] h-[400px] bg-blue-500/20 -top-40 -right-32" />
        <div className="hero-blob w-[500px] h-[320px] bg-cyan-500/15 -bottom-48 -left-32" />
        <div className="hero-orb w-3 h-3 bg-cyan-400/50 top-[22%] right-[18%]" />
        <div className="hero-orb w-2 h-2 bg-blue-400/40 bottom-[30%] left-[12%]" style={{ animationDelay: '2s' }} />

        <div className="container-max relative z-10 px-4 sm:px-6 py-16 sm:py-24 min-h-[min(88vh,720px)] flex flex-col justify-center">
          <motion.span
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: easeOut }}
            className="demo-hero__eyebrow"
          >
            <span className="demo-hero__pulse" />
            {demos.length > 0 ? `${demos.length} live product${demos.length === 1 ? '' : 's'}` : 'AI-generated gallery'}
          </motion.span>

          <h1 className="demo-hero__headline">
            {heroLines.map((line, i) => (
              <motion.span
                key={line}
                initial={{ opacity: 0, y: 32 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 + i * 0.1, duration: 0.75, ease: easeOut }}
                className={`demo-hero__line ${i === 1 ? 'demo-hero__line--accent' : ''}`}
              >
                {line}
              </motion.span>
            ))}
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.38, duration: 0.6, ease: easeOut }}
            className="demo-hero__sub"
          >
            Every completed submission becomes a real, interactive app — not a slide deck.
            Open any build below and explore it like a shipped product.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.5, ease: easeOut }}
            className="mt-10"
          >
            <GlowButton to="/submit" className="text-sm px-7 py-3.5 !inline-block">
              Create yours — free
            </GlowButton>
          </motion.div>
        </div>

        <div className="demo-hero__fade" aria-hidden />
      </section>

      <section className="demo-gallery relative">
        <div className="absolute inset-0 demo-gallery__bg-grid pointer-events-none" />
        <div className="container-max relative px-4 sm:px-6 py-16 sm:py-24">
          {loading && (
            <div className="flex flex-col items-center justify-center py-32 text-slate-400">
              <div className="w-12 h-12 border-2 border-white/10 border-t-cyan-400 rounded-full animate-spin mb-4" />
              Loading live products…
            </div>
          )}

          {error && <p className="text-center text-red-400 py-20">{error}</p>}

          {!loading && !error && demos.length === 0 && (
            <div className="text-center py-24">
              <p className="text-slate-400 mb-8 text-lg">No live products yet — yours could be first.</p>
              <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-block">
                Create my version
              </GlowButton>
            </div>
          )}

          {!loading && !error && featured && (
            <div className="demo-gallery__stack">
              <motion.div
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                className="demo-gallery__section-label"
              >
                <span className="demo-gallery__label-num">01</span>
                <span>Spotlight</span>
              </motion.div>
              <DemoCard demo={featured} featured />

              {rest.length > 0 && (
                <>
                  <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    className="demo-gallery__section-label demo-gallery__section-label--mt"
                  >
                    <span className="demo-gallery__label-num">02</span>
                    <span>All builds ({demos.length})</span>
                  </motion.div>
                  <div className="demo-gallery__grid">
                    {rest.map((demo, i) => (
                      <DemoCard key={demo.id} demo={demo} index={i} />
                    ))}
                  </div>
                </>
              )}
            </div>
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
