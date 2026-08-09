import * as React from 'react';

import { useInView, useMotionValue, useSpring } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface NumberTickerProps {
  value: number;
  startValue?: number;
  direction?: 'up' | 'down';
  /** Seconds to wait after entering the viewport. */
  delay?: number;
  decimalPlaces?: number;
  className?: string;
}

/**
 * Count-up stat number on scroll into view.
 * Adapted from Magic UI `number-ticker` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: color inherits from the caller's tokens (upstream
 * forced black/white), and reduced motion renders the final value instantly —
 * a stat is content, never a casualty of the animation.
 */
export function NumberTicker({
  value,
  startValue = 0,
  direction = 'up',
  delay = 0,
  decimalPlaces = 0,
  className,
}: NumberTickerProps) {
  const safe = useMotionSafe();
  const ref = React.useRef<HTMLSpanElement>(null);
  const motionValue = useMotionValue(direction === 'down' ? value : startValue);
  const springValue = useSpring(motionValue, { damping: 60, stiffness: 100 });
  const isInView = useInView(ref, { once: true, margin: '0px' });

  const format = React.useCallback(
    (n: number) =>
      Intl.NumberFormat('en-US', {
        minimumFractionDigits: decimalPlaces,
        maximumFractionDigits: decimalPlaces,
      }).format(Number(n.toFixed(decimalPlaces))),
    [decimalPlaces]
  );

  React.useEffect(() => {
    if (!safe || !isInView) return;
    const timer = setTimeout(() => {
      motionValue.set(direction === 'down' ? startValue : value);
    }, delay * 1000);
    return () => clearTimeout(timer);
  }, [safe, motionValue, isInView, delay, value, direction, startValue]);

  React.useEffect(() => {
    if (!safe) return;
    return springValue.on('change', (latest) => {
      if (ref.current) ref.current.textContent = format(Number(latest));
    });
  }, [safe, springValue, format]);

  const resting = format(direction === 'down' ? startValue : value);
  return (
    <span ref={ref} className={cn('inline-block tabular-nums tracking-wider', className)}>
      {safe ? format(direction === 'down' ? value : startValue) : resting}
    </span>
  );
}
