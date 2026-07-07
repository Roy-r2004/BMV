import { motion, useInView } from 'framer-motion';
import { useRef, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  className?: string;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
}

const offsets = {
  up: { y: 30, x: 0 },
  down: { y: -30, x: 0 },
  left: { y: 0, x: 30 },
  right: { y: 0, x: -30 },
};

export default function AnimatedSection({
  children,
  className = '',
  delay = 0,
  direction = 'up',
}: Props) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-40px' });
  const offset = offsets[direction];

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, x: offset.x, y: offset.y }}
      animate={inView ? { opacity: 1, x: 0, y: 0 } : {}}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  subtitle,
  tone = 'light',
  className = '',
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  tone?: 'light' | 'dark';
  className?: string;
}) {
  const isDark = tone === 'dark';
  return (
    <div className={`text-center mb-12 ${className}`}>
      {eyebrow && (
        <p
          className={`font-medium mb-2 tracking-[0.15em] uppercase text-xs ${
            isDark ? 'text-cyan-400/90' : 'text-blue-600'
          }`}
        >
          {eyebrow}
        </p>
      )}
      <h2 className={`text-3xl sm:text-4xl font-bold mb-3 tracking-tight ${isDark ? 'text-white' : 'text-navy'}`}>
        {title}
      </h2>
      {subtitle && (
        <p className={`max-w-2xl mx-auto text-base leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
