import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function LandingManifesto() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const x = useTransform(scrollYProgress, [0, 1], ['-4%', '4%']);

  return (
    <section ref={ref} className="landing-section landing-section--dark relative py-20 sm:py-28 overflow-hidden">
      <div className="landing-section__grid" aria-hidden />
      <div className="landing-divider absolute top-0 inset-x-0" aria-hidden />
      <motion.div
        style={{ x }}
        className="absolute -top-16 -right-16 w-72 h-72 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none"
      />

      <div className="container-max relative px-4 sm:px-6 max-w-4xl mx-auto text-center">
        <motion.p
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.7, ease: easeOut }}
          className="text-2xl sm:text-4xl lg:text-[2.75rem] font-bold leading-[1.15] tracking-tight text-slate-200 mb-5"
        >
          You see tools you like.
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ delay: 0.1, duration: 0.7, ease: easeOut }}
          className="text-base sm:text-xl lg:text-2xl text-slate-400 leading-relaxed mb-6 max-w-2xl mx-auto"
        >
          Turning them into something useful for your business is the hard part.
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ delay: 0.2, duration: 0.7, ease: easeOut }}
          className="text-xl sm:text-3xl font-bold gradient-text-shimmer"
        >
          We make that part disappear.
        </motion.p>
      </div>
    </section>
  );
}
