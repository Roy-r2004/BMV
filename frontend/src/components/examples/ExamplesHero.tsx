import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';

const easeOut = [0.22, 1, 0.36, 1] as const;
const lines = ['Example', 'outputs', 'that inspire.'];

export default function ExamplesHero() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 100]);
  const opacity = useTransform(scrollYProgress, [0, 0.65], [1, 0]);

  return (
    <section ref={ref} className="about-cinematic-hero relative flex items-center overflow-hidden pt-16 hero-surface">
      <div className="absolute inset-0 hero-mesh pointer-events-none" />
      <div className="absolute inset-0 cinematic-grid opacity-70 pointer-events-none" />
      <div className="hero-blob w-[600px] h-[360px] bg-blue-400/28 -top-28 -right-28" />
      <div className="hero-blob w-[480px] h-[300px] bg-cyan-400/22 -bottom-36 -left-28" />
      <div className="hero-orb w-3 h-3 bg-cyan-400/60 top-[18%] right-[20%]" />
      <div className="hero-orb w-2 h-2 bg-blue-500/50 bottom-[35%] left-[10%]" style={{ animationDelay: '1.8s' }} />

      <motion.div
        style={{ y, opacity }}
        className="container-max relative z-10 px-4 sm:px-6 w-full py-12 min-h-[calc(100dvh-4rem)] flex flex-col justify-center text-center"
      >
        <motion.span
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: easeOut }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full about-glass text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.2em] mb-6 mx-auto shadow-sm"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
          Real concept types
        </motion.span>

        <h1 className="mb-6">
          {lines.map((line, i) => (
            <motion.span
              key={line}
              initial={{ opacity: 0, y: 36 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 + i * 0.1, duration: 0.7, ease: easeOut }}
              className={`block font-bold leading-[1.08] tracking-tight ${
                i === 1
                  ? 'text-[2.25rem] sm:text-5xl lg:text-[3.75rem] gradient-text-shimmer'
                  : i === 2
                    ? 'text-xl sm:text-2xl lg:text-3xl text-slate-500 font-semibold mt-2'
                    : 'text-[1.75rem] sm:text-4xl lg:text-[2.5rem] text-navy'
              }`}
            >
              {line}
            </motion.span>
          ))}
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45, duration: 0.65, ease: easeOut }}
          className="text-slate-600 max-w-2xl mx-auto text-base sm:text-lg leading-relaxed"
        >
          Custom business versions our AI generates — from competitive intelligence to booking systems,
          inspired by production systems our team has shipped.
        </motion.p>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9 }}
          className="mt-10 flex flex-wrap justify-center gap-3"
        >
          {['6 concept types', '88% top fit score', 'Visual demo included'].map((t) => (
            <span key={t} className="px-3 py-1.5 rounded-full text-xs font-medium text-slate-600 about-glass">
              {t}
            </span>
          ))}
        </motion.div>
      </motion.div>
    </section>
  );
}
