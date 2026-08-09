import * as React from 'react';

import { motion, useScroll } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface ScrollProgressProps {
  className?: string;
}

/**
 * Reading-progress hairline pinned to the top of the viewport — the
 * long-page treatment for editorial stories and product deep-dives.
 * Adapted from Magic UI `scroll-progress` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: the fixed violet/pink/peach hex gradient became
 * brand→accent tokens; native scroll drives it (no smoothing dependency);
 * reduced motion renders nothing — the bar is a flourish, the scrollbar
 * already tells the truth.
 */
export function ScrollProgress({ className }: ScrollProgressProps) {
  const safe = useMotionSafe();
  const { scrollYProgress } = useScroll();

  if (!safe) return null;
  return (
    <motion.div
      aria-hidden
      className={cn('fixed inset-x-0 top-0 z-50 h-[2px] origin-left', className)}
      style={{
        scaleX: scrollYProgress,
        background: 'linear-gradient(to right, var(--color-brand), var(--color-accent))',
      }}
    />
  );
}
