import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { motionIdentity } from '../../lib/motion-identity';
import { useMotionSafe } from '../motion/presets';

export interface AnimatedShinyTextProps {
  children: React.ReactNode;
  className?: string;
  /** Width of the shimmer highlight sweep, in px. */
  shimmerWidth?: number;
}

/**
 * Shimmer sweep across an eyebrow / announcement pill.
 * Adapted from Magic UI `animated-shiny-text` (MIT) — see PROVENANCE.json.
 * Rewritten onto tokens: the shine rides `--color-foreground` mixes instead of
 * hardcoded neutrals, and the upstream Tailwind-config keyframes became a
 * motion-driven background sweep so the kit ships no extra CSS. Reduced
 * motion renders the text static.
 */
export function AnimatedShinyText({
  children,
  className,
  shimmerWidth = 100,
}: AnimatedShinyTextProps) {
  const safe = useMotionSafe();
  if (!safe) {
    return <span className={cn('text-muted', className)}>{children}</span>;
  }
  return (
    <motion.span
      style={
        {
          '--shiny-width': `${shimmerWidth}px`,
          backgroundImage:
            'linear-gradient(to right, transparent, color-mix(in srgb, var(--color-foreground) 85%, transparent) 50%, transparent)',
          backgroundSize: 'var(--shiny-width) 100%',
          backgroundRepeat: 'no-repeat',
        } as React.CSSProperties
      }
      className={cn('bg-clip-text text-muted', className)}
      initial={{ backgroundPosition: 'calc(-1 * var(--shiny-width)) 0' }}
      animate={{ backgroundPosition: 'calc(100% + var(--shiny-width)) 0' }}
      transition={{ repeat: Infinity, duration: 2.4, ease: motionIdentity().ease, repeatDelay: 0.6 }}
    >
      {children}
    </motion.span>
  );
}
