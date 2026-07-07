import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';

const lines = [
  'You see tools you love.',
  'Turning them into something useful for your business is the hard part.',
  'We make that part disappear.',
];

export default function AboutManifesto() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const x = useTransform(scrollYProgress, [0, 1], ['-8%', '8%']);

  return (
    <section ref={ref} className="relative py-28 sm:py-36 overflow-hidden bg-navy text-white">
      <div className="absolute inset-0 cinematic-grid opacity-[0.07] pointer-events-none invert" />
      <motion.div
        style={{ x }}
        className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-blue-500/20 blur-3xl pointer-events-none"
      />

      <div className="container-max relative px-4 sm:px-6">
        {lines.map((line, i) => (
          <motion.p
            key={line}
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ delay: i * 0.15, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className={`font-bold leading-[1.15] tracking-tight ${
              i === 0
                ? 'text-2xl sm:text-4xl lg:text-5xl text-blue-200/90 mb-6'
                : i === 1
                  ? 'text-xl sm:text-3xl lg:text-4xl text-white/70 mb-8 max-w-4xl'
                  : 'text-2xl sm:text-4xl lg:text-5xl gradient-text-shimmer'
            }`}
          >
            {line}
          </motion.p>
        ))}
      </div>
    </section>
  );
}
