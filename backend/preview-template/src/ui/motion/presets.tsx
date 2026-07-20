import * as React from 'react';
import { motion, useReducedMotion, type Transition, type Variants } from 'motion/react';

import { cn } from '../lib/cn';
import { AnimeReveal, AnimeStagger, AnimeStaggerItem } from './AnimeChrome';

const easeOut: Transition['ease'] = [0.22, 1, 0.36, 1];

export function useMotionSafe(): boolean {
  const reduced = useReducedMotion();
  return !reduced;
}

export const heroEntrance: Variants = {
  hidden: { opacity: 0, y: 22, filter: 'blur(6px)' },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.8, delay: 0.06 + i * 0.11, ease: easeOut },
  }),
};

export const sectionReveal: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.65, ease: easeOut },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.09, delayChildren: 0.08 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 18, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.5, ease: easeOut },
  },
};

export const pageFade: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.35, ease: easeOut },
  },
};

const hoverLiftTransition: Transition = { type: 'spring', stiffness: 380, damping: 28 };

type PresetProps = {
  children?: React.ReactNode;
  className?: string;
  role?: string;
};

export function MotionPage({ className, children }: PresetProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div className={className} initial="hidden" animate="visible" variants={pageFade}>
      {children}
    </motion.div>
  );
}

export function MotionReveal({ className, children }: PresetProps) {
  // Page-level section reveals use anime.js for Manus-grade choreography.
  return <AnimeReveal className={className}>{children}</AnimeReveal>;
}

export function MotionStagger({ className, children, role }: PresetProps) {
  return (
    <AnimeStagger className={className} role={role}>
      {children}
    </AnimeStagger>
  );
}

export function MotionStaggerItem({ className, children, role }: PresetProps) {
  return (
    <AnimeStaggerItem className={className} role={role}>
      {children}
    </AnimeStaggerItem>
  );
}

export function MotionHeroItem({ className, children, index = 0 }: PresetProps & { index?: number }) {
  const safe = useMotionSafe();
  if (!safe) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div className={className} custom={index} initial="hidden" animate="visible" variants={heroEntrance}>
      {children}
    </motion.div>
  );
}

export function MotionHover({ className, children }: PresetProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div
      className={cn(className)}
      whileHover={{ y: -4, scale: 1.01 }}
      transition={hoverLiftTransition}
    >
      {children}
    </motion.div>
  );
}

export function MotionScaleIn({ className, children }: PresetProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, scale: 0.94 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.55, ease: easeOut }}
    >
      {children}
    </motion.div>
  );
}
