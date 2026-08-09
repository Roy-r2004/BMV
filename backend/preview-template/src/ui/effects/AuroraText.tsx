import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface AuroraTextProps {
  children: React.ReactNode;
  className?: string;
  /** Gradient stops; defaults ride the brand tokens, never fixed hues. */
  colors?: string[];
  /** 1 = one sweep every 10s; higher is faster. */
  speed?: number;
}

/**
 * Animated aurora gradient inside display text.
 * Adapted from Magic UI `aurora-text` (MIT) — see PROVENANCE.json.
 * Rewritten onto tokens: the default stops are brand/accent mixes instead of
 * upstream's fixed pink/violet set, and the Tailwind-config `aurora`
 * keyframes became a motion-driven background sweep (no new CSS). Reduced
 * motion keeps the gradient fill, static — identity without movement.
 */
export function AuroraText({ children, className, colors, speed = 1 }: AuroraTextProps) {
  const safe = useMotionSafe();
  const stops =
    colors && colors.length >= 2
      ? colors
      : [
          'var(--color-brand)',
          'color-mix(in srgb, var(--color-brand) 45%, var(--color-accent))',
          'var(--color-accent)',
          'color-mix(in srgb, var(--color-accent) 55%, var(--color-brand))',
        ];
  const gradient: React.CSSProperties = {
    backgroundImage: `linear-gradient(135deg, ${stops.join(', ')}, ${stops[0]})`,
    backgroundSize: '200% auto',
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    color: 'transparent',
  };
  return (
    <span className={cn('relative inline-block', className)}>
      <span className="sr-only">{children}</span>
      {safe ? (
        <motion.span
          className="relative inline-block"
          style={gradient}
          aria-hidden="true"
          initial={{ backgroundPosition: '0% 50%' }}
          animate={{ backgroundPosition: ['0% 50%', '200% 50%'] }}
          transition={{ repeat: Infinity, duration: 10 / Math.max(speed, 0.1), ease: 'linear' }}
        >
          {children}
        </motion.span>
      ) : (
        <span className="relative inline-block" style={gradient} aria-hidden="true">
          {children}
        </span>
      )}
    </span>
  );
}
