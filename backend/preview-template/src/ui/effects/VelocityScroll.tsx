import * as React from 'react';

import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useScroll,
  useSpring,
  useTransform,
  useVelocity,
} from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface VelocityScrollProps {
  children: React.ReactNode;
  /** Marquee speed in percent of one copy per second; sign sets direction. */
  baseVelocity?: number;
  className?: string;
}

const wrap = (min: number, max: number, v: number) => {
  const range = max - min;
  return ((((v - min) % range) + range) % range) + min;
};

/**
 * Kinetic big-type marquee whose speed and direction follow scroll velocity —
 * the section-divider treatment for loud retail/playful pages.
 * Adapted from Magic UI `scroll-based-velocity` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: one component instead of the upstream
 * container/row/context family, four measured copies instead of
 * ResizeObserver plumbing, and reduced motion renders a single static row —
 * a complete page, no marquee. Type/color stay with the caller's tokens.
 */
export function VelocityScroll({ children, baseVelocity = 4, className }: VelocityScrollProps) {
  const safe = useMotionSafe();
  const baseX = useMotionValue(0);
  const { scrollY } = useScroll();
  const scrollVelocity = useVelocity(scrollY);
  const smoothVelocity = useSpring(scrollVelocity, { damping: 50, stiffness: 400 });
  const velocityFactor = useTransform(smoothVelocity, (v) => {
    const sign = v < 0 ? -1 : 1;
    return sign * Math.min(5, (Math.abs(v) / 1000) * 5);
  });
  const directionRef = React.useRef(baseVelocity >= 0 ? 1 : -1);
  const x = useTransform(baseX, (v) => `${wrap(-25, 0, v)}%`);

  useAnimationFrame((_, delta) => {
    if (!safe) return;
    const factor = velocityFactor.get();
    if (factor < 0) directionRef.current = -1;
    else if (factor > 0) directionRef.current = 1;
    let moveBy = directionRef.current * Math.abs(baseVelocity) * (delta / 1000);
    moveBy += moveBy * Math.abs(factor);
    baseX.set(baseX.get() + moveBy);
  });

  if (!safe) {
    return (
      <div className={cn('w-full overflow-hidden whitespace-nowrap', className)}>
        <span className="inline-block">{children}</span>
      </div>
    );
  }
  return (
    <div className={cn('w-full overflow-hidden whitespace-nowrap', className)}>
      <motion.div className="inline-flex will-change-transform" style={{ x }}>
        {Array.from({ length: 4 }, (_, i) => (
          <span key={i} className="inline-block pr-[0.6em]" aria-hidden={i > 0 || undefined}>
            {children}
          </span>
        ))}
      </motion.div>
    </div>
  );
}
