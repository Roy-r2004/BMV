import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface ShimmerButtonProps extends React.ComponentPropsWithoutRef<'button'> {
  children?: React.ReactNode;
  /** Seconds for one shimmer pass. */
  shimmerDuration?: number;
  className?: string;
}

/**
 * The hero-CTA button: a light pass sweeps the surface on a loop — reserved
 * for the one action a marketing page actually wants clicked.
 * Adapted from Magic UI `shimmer-button` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: NOT grafted into core/Button — ops surfaces keep a
 * chrome-free Button by the restraint rule, and this composes only where a
 * marketing page reaches for it. Upstream's config keyframes
 * (shimmer-slide + spin-around) and container queries became one
 * motion-driven sweep; black/white hardcodes became brand/card tokens;
 * radius rides --radius-ui. Reduced motion renders the resting button —
 * still the same size, color, and label.
 */
export function ShimmerButton({
  children,
  shimmerDuration = 3,
  className,
  ...props
}: ShimmerButtonProps) {
  const safe = useMotionSafe();
  return (
    <button
      className={cn(
        'group relative isolate cursor-pointer overflow-hidden rounded-[var(--radius-ui)]',
        'bg-[var(--color-brand)] px-6 py-3 font-medium text-[var(--color-card)]',
        'border border-[color-mix(in_srgb,var(--color-card)_14%,transparent)]',
        'shadow-[inset_0_-8px_10px_color-mix(in_srgb,var(--color-card)_12%,transparent)]',
        'transform-gpu transition-all duration-300 ease-in-out active:translate-y-px',
        'hover:shadow-[inset_0_-6px_10px_color-mix(in_srgb,var(--color-card)_25%,transparent)]',
        className,
      )}
      {...props}
    >
      {safe && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 -z-10 w-1/3 -skew-x-12"
          style={{
            background:
              'linear-gradient(90deg, transparent, color-mix(in srgb, var(--color-card) 30%, transparent), transparent)',
          }}
          initial={{ left: '-40%' }}
          animate={{ left: '110%' }}
          transition={{
            duration: shimmerDuration * 0.45,
            ease: 'linear',
            repeat: Infinity,
            repeatDelay: shimmerDuration * 0.55,
          }}
        />
      )}
      {children}
    </button>
  );
}
