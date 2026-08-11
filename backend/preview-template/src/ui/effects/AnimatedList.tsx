import * as React from 'react';

import { AnimatePresence, motion } from 'motion/react';

import { motionIdentity } from '../../lib/motion-identity';
import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface AnimatedListProps {
  children: React.ReactNode;
  /** Milliseconds between item arrivals. */
  delay?: number;
  className?: string;
}

/**
 * Items arrive one at a time and stack newest-first — the live-feed
 * treatment for ops activity panels, booking notifications, and order pops.
 * Adapted from Magic UI `animated-list` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: each arrival's ease and travel come from the
 * recipe's motion identity instead of a fixed spring, so an ops feed ticks
 * quietly while a retail feed pops; reduced motion renders the complete
 * list statically — every item present, no arrivals.
 */
export function AnimatedList({ children, delay = 1000, className }: AnimatedListProps) {
  const safe = useMotionSafe();
  const [index, setIndex] = React.useState(0);
  const childrenArray = React.useMemo(() => React.Children.toArray(children), [children]);

  React.useEffect(() => {
    if (!safe || index >= childrenArray.length - 1) return;
    const timeout = setTimeout(() => setIndex((prev) => prev + 1), delay);
    return () => clearTimeout(timeout);
  }, [safe, index, delay, childrenArray.length]);

  const identity = motionIdentity();
  const newestFirst = React.useMemo(
    () => childrenArray.slice(0, index + 1).reverse(),
    [index, childrenArray],
  );

  if (!safe) {
    return (
      <div className={cn('flex w-full flex-col gap-4', className)}>
        {[...childrenArray].reverse().map((item) => (
          <div key={(item as React.ReactElement).key} className="w-full">
            {item}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className={cn('flex w-full flex-col gap-4', className)}>
      <AnimatePresence initial={false}>
        {newestFirst.map((item) => (
          <motion.div
            key={(item as React.ReactElement).key}
            layout
            initial={{ opacity: 0, scale: 0.94, y: `-${identity.travel}` }}
            animate={{ opacity: 1, scale: 1, y: '0px' }}
            transition={{ duration: 0.4, ease: identity.ease }}
            className="w-full"
          >
            {item}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
