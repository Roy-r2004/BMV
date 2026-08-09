import * as React from 'react';

import { motion, useAnimationFrame, useMotionValue, useTransform } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface MarqueeProps {
  children: React.ReactNode;
  /** Seconds for one copy of the content to travel past. */
  duration?: number;
  reverse?: boolean;
  pauseOnHover?: boolean;
  /** Gap between items and between repeated copies (any CSS length). */
  gap?: string;
  className?: string;
}

const COPIES = 4;

const wrap = (min: number, max: number, v: number) => {
  const range = max - min;
  return ((((v - min) % range) + range) % range) + min;
};

/**
 * Constant-velocity rail for logo strips, product ribbons, and gallery
 * bands — VelocityScroll's steady sibling: same wrap math, no scroll
 * coupling.
 * Adapted from Magic UI `marquee` (MIT) — see PROVENANCE.json. Rewritten
 * for the kit: upstream's Tailwind-config `animate-marquee` keyframes became
 * a motion-driven frame loop (no new CSS), pause-on-hover is a ref the loop
 * reads instead of `animation-play-state`, the vertical mode was dropped
 * (no kit consumer), and reduced motion renders one static row — a complete
 * strip, no crawl.
 */
export function Marquee({
  children,
  duration = 40,
  reverse = false,
  pauseOnHover = false,
  gap = '1.5rem',
  className,
}: MarqueeProps) {
  const safe = useMotionSafe();
  const baseX = useMotionValue(0);
  const pausedRef = React.useRef(false);
  const x = useTransform(baseX, (v) => `${wrap(-100 / COPIES, 0, v)}%`);

  useAnimationFrame((_, delta) => {
    if (!safe || pausedRef.current) return;
    const step = (100 / COPIES / Math.max(1, duration)) * (delta / 1000);
    baseX.set(baseX.get() + (reverse ? step : -step));
  });

  if (!safe) {
    return (
      <div className={cn('w-full overflow-hidden', className)}>
        <div className="flex w-max items-center" style={{ gap }}>
          {children}
        </div>
      </div>
    );
  }
  return (
    <div
      className={cn('w-full overflow-hidden', className)}
      onPointerEnter={() => {
        if (pauseOnHover) pausedRef.current = true;
      }}
      onPointerLeave={() => {
        pausedRef.current = false;
      }}
    >
      <motion.div className="flex w-max items-center will-change-transform" style={{ x, gap }}>
        {Array.from({ length: COPIES }, (_, i) => (
          <div
            key={i}
            aria-hidden={i > 0 || undefined}
            className="flex shrink-0 items-center"
            style={{ gap }}
          >
            {children}
          </div>
        ))}
      </motion.div>
    </div>
  );
}
