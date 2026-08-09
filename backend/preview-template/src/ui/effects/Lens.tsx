import * as React from 'react';

import { AnimatePresence, motion, useMotionTemplate } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface LensProps {
  /** Usually a KitImage — the lens magnifies whatever it wraps. */
  children: React.ReactNode;
  /** Magnification inside the lens; must be >= 1. */
  zoomFactor?: number;
  /** Lens diameter in px. */
  lensSize?: number;
  className?: string;
  ariaLabel?: string;
}

/**
 * Hover magnifier: a circular lens follows the pointer and shows the wrapped
 * content zoomed — the product-detail treatment for craft and retail pages.
 * Adapted from Magic UI `lens` (MIT) — see PROVENANCE.json. Rewritten for
 * the kit: the demo-oriented static/fixed-position modes were dropped, the
 * corner radius rides the kit's radius token, and reduced motion renders the
 * wrapped content untouched — the zoom is a flourish, never the only way to
 * see the image. The mask keyword 'black' is alpha geometry, not palette.
 */
export function Lens({
  children,
  zoomFactor = 1.3,
  lensSize = 170,
  className,
  ariaLabel = 'Zoom area',
}: LensProps) {
  const safe = useMotionSafe();
  const [isHovering, setIsHovering] = React.useState(false);
  const [position, setPosition] = React.useState({ x: 0, y: 0 });

  const maskImage = useMotionTemplate`radial-gradient(circle ${lensSize / 2}px at ${position.x}px ${position.y}px, black 100%, transparent 100%)`;

  const handleMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setPosition({ x: event.clientX - rect.left, y: event.clientY - rect.top });
  };

  if (!safe) {
    return (
      <div className={cn('relative overflow-hidden rounded-[var(--radius-ui)]', className)}>
        {children}
      </div>
    );
  }
  return (
    <div
      role="region"
      aria-label={ariaLabel}
      tabIndex={0}
      className={cn('relative z-20 overflow-hidden rounded-[var(--radius-ui)]', className)}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
      onMouseMove={handleMouseMove}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setIsHovering(false);
      }}
    >
      {children}
      <AnimatePresence mode="popLayout">
        {isHovering && (
          <motion.div
            initial={{ opacity: 0, scale: 0.58 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 z-50 overflow-hidden"
            style={{
              maskImage,
              WebkitMaskImage: maskImage,
              transformOrigin: `${position.x}px ${position.y}px`,
            }}
          >
            <div
              className="absolute inset-0"
              style={{
                transform: `scale(${zoomFactor})`,
                transformOrigin: `${position.x}px ${position.y}px`,
              }}
            >
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
