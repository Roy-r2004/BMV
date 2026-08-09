import * as React from 'react';

import { AnimatePresence, motion } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface WordRotateProps {
  /** Words cycled through in order; the first word is the reduced-motion text. */
  words: string[];
  /** Milliseconds each word stays before rotating. */
  duration?: number;
  className?: string;
}

/**
 * Vertically rotating word inside a headline.
 * Adapted from Magic UI `word-rotate` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: renders a `span` (the upstream `h1` broke heading
 * composition), the interval never runs under reduced motion, and styling
 * stays with the caller — headlines already carry `font-display` and tokens.
 */
export function WordRotate({ words, duration = 2500, className }: WordRotateProps) {
  const safe = useMotionSafe();
  const [index, setIndex] = React.useState(0);
  const count = words.length;

  React.useEffect(() => {
    if (!safe || count < 2) return;
    const interval = setInterval(() => {
      setIndex((prev) => (prev + 1) % count);
    }, duration);
    return () => clearInterval(interval);
  }, [safe, count, duration]);

  if (count === 0) return null;
  if (!safe || count === 1) {
    return <span className={cn('inline-block', className)}>{words[0]}</span>;
  }
  return (
    <span className={cn('inline-block overflow-hidden py-0.5 align-bottom', className)}>
      <AnimatePresence mode="wait">
        <motion.span
          key={words[index]}
          className="inline-block"
          initial={{ opacity: 0, y: '-0.9em' }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: '0.9em' }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
        >
          {words[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
