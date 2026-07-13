import * as React from 'react';
import { motion, useReducedMotion, type Transition, type Variants } from 'motion/react';

import { cn } from '../lib/cn';

const easeOut: Transition['ease'] = [0.22, 1, 0.36, 1];

export function useMotionSafe(): boolean {
  const reduced = useReducedMotion();
  return !reduced;
}

export const heroEntrance: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, delay: 0.08 + i * 0.1, ease: easeOut },
  }),
};

export const sectionReveal: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, ease: easeOut },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.06 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: easeOut },
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
  const safe = useMotionSafe();
  if (!safe) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.22 }}
      variants={sectionReveal}
    >
      {children}
    </motion.div>
  );
}

export function MotionStagger({ className, children, role }: PresetProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return (
      <div className={className} role={role}>
        {children}
      </div>
    );
  }
  return (
    <motion.div
      className={className}
      role={role}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.18 }}
      variants={staggerContainer}
    >
      {children}
    </motion.div>
  );
}

export function MotionStaggerItem({ className, children, role }: PresetProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return (
      <div className={className} role={role}>
        {children}
      </div>
    );
  }
  return (
    <motion.div className={className} role={role} variants={staggerItem}>
      {children}
    </motion.div>
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
    <motion.div className={cn(className)} whileHover={{ y: -3 }} transition={hoverLiftTransition}>
      {children}
    </motion.div>
  );
}
