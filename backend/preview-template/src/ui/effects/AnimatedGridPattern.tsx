import * as React from 'react';

import { motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface AnimatedGridPatternProps {
  /** Cell width in px. */
  width?: number;
  /** Cell height in px. */
  height?: number;
  numSquares?: number;
  maxOpacity?: number;
  /** Seconds for one square's fade cycle. */
  duration?: number;
  className?: string;
}

/** Deterministic [0, 1) from a square id and its cycle — never randomized. */
function hash01(square: number, cycle: number): number {
  let h = (Math.imul(square + 1, 0x9e3779b1) ^ Math.imul(cycle + 1, 0x85ebca6b)) >>> 0;
  h ^= h >>> 16;
  h = Math.imul(h, 0x045d9f3b) >>> 0;
  h ^= h >>> 16;
  return h / 0x100000000;
}

/**
 * Line-grid backdrop where a scatter of cells breathes in and out — the
 * quiet structural texture for editorial and light ops headers.
 * Adapted from Magic UI `animated-grid-pattern` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: square positions come from an id+cycle hash instead
 * of Math random, so the scatter is identical run-to-run; grid lines ride
 * --color-border-subtle and breathing cells ride the brand token; reduced
 * motion renders the bare grid — structure without the breathing.
 */
export function AnimatedGridPattern({
  width = 40,
  height = 40,
  numSquares = 30,
  maxOpacity = 0.35,
  duration = 4,
  className,
}: AnimatedGridPatternProps) {
  const safe = useMotionSafe();
  const id = React.useId();
  const containerRef = React.useRef<SVGSVGElement | null>(null);
  const [dimensions, setDimensions] = React.useState({ width: 0, height: 0 });
  const [cycles, setCycles] = React.useState<number[]>(() =>
    Array.from({ length: numSquares }, () => 0),
  );

  React.useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions((current) => {
          const next = { width: entry.contentRect.width, height: entry.contentRect.height };
          return current.width === next.width && current.height === next.height ? current : next;
        });
      }
    });
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, []);

  const cols = Math.max(1, Math.floor(dimensions.width / width));
  const rows = Math.max(1, Math.floor(dimensions.height / height));

  return (
    <svg
      ref={containerRef}
      aria-hidden="true"
      className={cn(
        'pointer-events-none absolute inset-0 h-full w-full',
        'fill-[color-mix(in_srgb,var(--color-border-subtle)_60%,transparent)]',
        'stroke-[color-mix(in_srgb,var(--color-border-subtle)_60%,transparent)]',
        className,
      )}
    >
      <defs>
        <pattern id={id} width={width} height={height} patternUnits="userSpaceOnUse" x={-1} y={-1}>
          <path d={`M.5 ${height}V.5H${width}`} fill="none" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
      {safe && dimensions.width > 0 && (
        <svg x={-1} y={-1} className="overflow-visible">
          {cycles.map((cycle, index) => {
            const squareX = Math.floor(hash01(index, cycle) * cols);
            const squareY = Math.floor(hash01(index ^ 0x517cc1b7, cycle) * rows);
            return (
              <motion.rect
                key={`${index}-${cycle}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: maxOpacity }}
                transition={{
                  duration,
                  repeat: 1,
                  delay: index * 0.1,
                  repeatType: 'reverse',
                }}
                onAnimationComplete={() =>
                  setCycles((current) =>
                    current.map((value, i) => (i === index ? value + 1 : value)),
                  )
                }
                width={width - 1}
                height={height - 1}
                x={squareX * width + 1}
                y={squareY * height + 1}
                fill="var(--color-brand)"
                strokeWidth="0"
              />
            );
          })}
        </svg>
      )}
    </svg>
  );
}
