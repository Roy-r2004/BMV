import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';

const easeOut = [0.22, 1, 0.36, 1] as const;

const headline = ['We\'re building', 'the company that makes', 'custom software', 'accessible.'];

export default function AboutHero() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 120]);
  const opacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);
  const scale = useTransform(scrollYProgress, [0, 0.8], [1, 0.96]);

  return (
    <section ref={ref} className="about-cinematic-hero relative flex items-center overflow-hidden pt-16 hero-surface">
      <div className="absolute inset-0 hero-mesh pointer-events-none" />
      <div className="absolute inset-0 cinematic-grid opacity-70 pointer-events-none" />
      <div className="hero-blob w-[640px] h-[380px] bg-blue-400/30 -top-32 -right-32" />
      <div className="hero-blob w-[520px] h-[320px] bg-cyan-400/25 -bottom-40 -left-32" />
      <div className="hero-blob w-[280px] h-[280px] bg-indigo-400/20 top-1/4 left-1/6" />

      <div className="hero-orb w-3 h-3 bg-cyan-400/70 top-[20%] right-[15%] shadow-lg shadow-cyan-400/40" />
      <div className="hero-orb w-2 h-2 bg-blue-500/60 top-[55%] left-[10%]" style={{ animationDelay: '1.5s' }} />
      <div className="hero-orb w-2.5 h-2.5 bg-indigo-400/50 bottom-[30%] right-[28%]" style={{ animationDelay: '3s' }} />

      <motion.div style={{ y, opacity, scale }} className="container-max relative z-10 px-4 sm:px-6 w-full py-12 min-h-[calc(100dvh-4rem)] flex flex-col justify-center">
        <motion.span
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: easeOut }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full about-glass text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.2em] mb-6 shadow-sm"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
          About Build My Version
        </motion.span>

        <h1 className="max-w-4xl">
          {headline.map((line, i) => (
            <motion.span
              key={line}
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.12, duration: 0.7, ease: easeOut }}
              className={`block font-bold leading-[1.08] tracking-tight ${
                i === 2
                  ? 'text-[2rem] sm:text-5xl lg:text-[3.5rem] gradient-text-shimmer my-1'
                  : 'text-[1.65rem] sm:text-4xl lg:text-[2.75rem] text-navy'
              }`}
            >
              {line}
            </motion.span>
          ))}
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.65, duration: 0.65, ease: easeOut }}
          className="mt-6 text-base sm:text-lg text-slate-600 max-w-xl leading-relaxed"
        >
          An AI product design platform — and the company we&apos;re growing around it.
          Our team turns tools you admire into custom versions built for your business.
        </motion.p>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.1, duration: 0.8 }}
          className="absolute bottom-6 sm:bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-slate-400 pointer-events-none"
        >
          <span className="text-[10px] uppercase tracking-[0.25em] font-medium">Scroll</span>
          <div className="about-scroll-hint w-5 h-8 rounded-full border-2 border-slate-300/80 flex justify-center pt-1.5">
            <div className="w-1 h-1.5 rounded-full bg-blue-500" />
          </div>
        </motion.div>
      </motion.div>
    </section>
  );
}
