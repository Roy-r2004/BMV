import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface RippleProps {
  className?: string;
  /** Diameter of the innermost circle, in px. */
  mainCircleSize?: number;
  /** Opacity of the innermost circle; each ring fades from here. */
  mainCircleOpacity?: number;
  numCircles?: number;
}

/**
 * Concentric soft ripple background behind a hero or CTA band.
 * Adapted from Magic UI `ripple` (MIT) — see PROVENANCE.json.
 * Rewritten onto tokens: rings ride `--color-brand` mixes instead of the
 * upstream foreground neutrals, and the Tailwind-config `ripple` keyframes
 * became a motion-driven pulse so the kit ships no extra CSS. Reduced motion
 * renders the rings static — a complete page, no pulse.
 */
export function Ripple({
  className,
  mainCircleSize = 210,
  mainCircleOpacity = 0.24,
  numCircles = 8,
}: RippleProps) {
  const safe = useMotionSafe();
  return (
    <div
      aria-hidden="true"
      className={cn(
        'pointer-events-none absolute inset-0 select-none [mask-image:linear-gradient(to_bottom,white,transparent)]',
        className
      )}
    >
      {Array.from({ length: numCircles }, (_, i) => {
        const size = mainCircleSize + i * 70;
        const opacity = Math.max(mainCircleOpacity - i * 0.03, 0.02);
        const ring = (
          <div
            className="size-full rounded-full border bg-[color-mix(in_srgb,var(--color-brand)_18%,transparent)] shadow-xl"
            style={{
              borderWidth: '1px',
              borderColor: 'color-mix(in srgb, var(--color-brand) 45%, transparent)',
            }}
          />
        );
        const placement: React.CSSProperties = {
          width: `${size}px`,
          height: `${size}px`,
          opacity,
          top: '50%',
          left: '50%',
          translate: '-50% -50%',
        };
        return safe ? (
          <motion.div
            key={i}
            className="absolute"
            style={placement}
            animate={{ scale: [1, 1.06, 1] }}
            transition={{
              repeat: Infinity,
              duration: 3,
              delay: i * 0.06,
              ease: 'easeInOut',
            }}
          >
            {ring}
          </motion.div>
        ) : (
          <div key={i} className="absolute" style={placement}>
            {ring}
          </div>
        );
      })}
    </div>
  );
}
