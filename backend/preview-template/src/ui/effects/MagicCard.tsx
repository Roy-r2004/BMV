import * as React from 'react';

import { motion, useMotionTemplate, useMotionValue } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface MagicCardProps {
  children: React.ReactNode;
  /** Radius of the pointer spotlight, in px. */
  gradientSize?: number;
  className?: string;
}

/**
 * Card whose border lights up under the pointer and whose surface carries a
 * faint traveling spotlight — premium hover feedback for product, plan, and
 * feature cards.
 * Adapted from Magic UI `magic-card` (MIT) — see PROVENANCE.json. Rewritten
 * for the kit: the border sweep runs brand→accent token mixes and rests on
 * `--color-border-subtle` (upstream hardcoded violet/pink hex plus
 * next-themes dark detection — both gone, the tokens already know the
 * theme); the inner surface is `--color-card`; the "orb" mode and global
 * pointer listeners were dropped. Reduced motion renders a plain resting
 * card — the spotlight only ever augments hover.
 */
export function MagicCard({ children, gradientSize = 200, className }: MagicCardProps) {
  const safe = useMotionSafe();
  const mouseX = useMotionValue(-gradientSize);
  const mouseY = useMotionValue(-gradientSize);

  const border = useMotionTemplate`
    linear-gradient(var(--color-card) 0 0) padding-box,
    radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px,
      color-mix(in srgb, var(--color-brand) 70%, transparent),
      color-mix(in srgb, var(--color-accent) 45%, transparent),
      var(--color-border-subtle) 100%
    ) border-box
  `;
  const spotlight = useMotionTemplate`
    radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px,
      color-mix(in srgb, var(--color-brand) 9%, transparent),
      transparent 100%
    )
  `;

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    mouseX.set(event.clientX - rect.left);
    mouseY.set(event.clientY - rect.top);
  };
  const rest = () => {
    mouseX.set(-gradientSize);
    mouseY.set(-gradientSize);
  };

  if (!safe) {
    return (
      <div
        className={cn(
          'relative rounded-[var(--radius-ui)] border border-[var(--color-border-subtle)] bg-[var(--color-card)]',
          className,
        )}
      >
        {children}
      </div>
    );
  }
  return (
    <motion.div
      className={cn(
        'group relative isolate overflow-hidden rounded-[var(--radius-ui)] border border-transparent',
        className,
      )}
      onPointerMove={handlePointerMove}
      onPointerLeave={rest}
      style={{ background: border }}
    >
      <div className="absolute inset-px z-10 rounded-[inherit] bg-[var(--color-card)]" />
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-px z-20 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: spotlight }}
      />
      <div className="relative z-30">{children}</div>
    </motion.div>
  );
}
