import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface DotPatternProps {
  /** Horizontal / vertical spacing between dots, in px. */
  width?: number;
  height?: number;
  /** Radius of each dot. */
  cr?: number;
  className?: string;
  /** Dots breathe with a soft glow; off = static texture. */
  glow?: boolean;
}

/**
 * Quiet dot-grid texture for services/gallery sections.
 * Adapted from Magic UI `dot-pattern` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: the default color rides `--color-border-subtle`
 * (upstream forced a neutral), the glow delays are DETERMINISTIC — seeded by
 * dot index, never randomized, so the screenshot critic sees the same frame
 * twice — and reduced motion renders the static texture.
 */
export function DotPattern({
  width = 16,
  height = 16,
  cr = 1,
  className,
  glow = false,
}: DotPatternProps) {
  const safe = useMotionSafe();
  const id = React.useId();
  const containerRef = React.useRef<SVGSVGElement>(null);
  const [dimensions, setDimensions] = React.useState({ width: 0, height: 0 });

  React.useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const update = () => {
      const rect = node.getBoundingClientRect();
      setDimensions({ width: rect.width, height: rect.height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const cols = Math.max(0, Math.ceil(dimensions.width / width));
  const rows = Math.max(0, Math.ceil(dimensions.height / height));
  const animated = glow && safe;

  return (
    <svg
      ref={containerRef}
      aria-hidden="true"
      className={cn(
        'pointer-events-none absolute inset-0 h-full w-full text-border-subtle',
        className
      )}
    >
      <defs>
        <radialGradient id={`${id}-gradient`}>
          <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
      </defs>
      {Array.from({ length: cols * rows }, (_, i) => {
        const col = i % Math.max(cols, 1);
        const row = Math.floor(i / Math.max(cols, 1));
        const x = col * width + 1;
        const y = row * height + 1;
        // Seeded, not random: the same grid renders the same frame twice.
        const delay = ((i * 37) % 50) / 10;
        const duration = 2 + ((i * 13) % 30) / 10;
        return animated ? (
          <motion.circle
            key={i}
            cx={x}
            cy={y}
            r={cr}
            fill={`url(#${id}-gradient)`}
            initial={{ opacity: 0.35 }}
            animate={{ opacity: [0.35, 0.9, 0.35] }}
            transition={{ repeat: Infinity, duration, delay, ease: 'easeInOut' }}
          />
        ) : (
          <circle key={i} cx={x} cy={y} r={cr} fill="currentColor" opacity={0.55} />
        );
      })}
    </svg>
  );
}
