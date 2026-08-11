import * as React from 'react';
import { motion, useReducedMotion, type Transition, type Variants } from 'motion/react';

import { motionIdentity } from '../../lib/motion-identity';
import { cn } from '../lib/cn';
import { AnimeReveal, AnimeStagger, AnimeStaggerItem } from './AnimeChrome';

/**
 * 3.10 wiring: the recipe's motion identity drives every variant below. The
 * accessor's fallback equals the kit's legacy constants (ease [0.22,1,0.36,1],
 * 90ms, 18px), and each value scales as a ratio off that base — so a bare or
 * unknown recipe renders exactly the pre-3.10 motion, while the six authored
 * families each move at their own temperament.
 */
const identity = motionIdentity();
const easeOut: Transition['ease'] = identity.ease;
const travel = (Number.parseFloat(identity.travel) || 18) / 18;
const tempo = Math.min(1.4, Math.max(0.45, identity.staggerMs / 90));

export function useMotionSafe(): boolean {
  const reduced = useReducedMotion();
  return !reduced;
}

export const heroEntrance: Variants = {
  hidden: { opacity: 0, y: 26 * travel, filter: 'blur(8px)' },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: {
      duration: 0.85 * tempo,
      delay: 0.05 + i * (identity.staggerMs / 750),
      ease: easeOut,
    },
  }),
};

export const sectionReveal: Variants = {
  hidden: { opacity: 0, y: 32 * travel },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7 * tempo, ease: easeOut },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: identity.staggerMs / 1000, delayChildren: 0.08 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 18 * travel, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.5 * tempo, ease: easeOut },
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
