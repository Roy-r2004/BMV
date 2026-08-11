import * as React from 'react';

import { motion, useScroll, useTransform, type MotionValue } from 'motion/react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface TextRevealProps {
  /** The statement to reveal, one word at a time. */
  children: string;
  className?: string;
}

/**
 * Scroll-scrubbed manifesto: the section pins while each word resolves from
 * a ghost of the surrounding text color to full strength — editorial pacing
 * for the one sentence a page is really about.
 * Adapted from Magic UI `text-reveal` (MIT) — see PROVENANCE.json.
 * Rewritten for the kit: ghost/active colors are currentColor mixes instead
 * of black/white pairs with dark: variants, so the treatment inherits any
 * section's palette; native scroll drives the scrub; reduced motion renders
 * the sentence as a plain full-strength paragraph in normal flow — the
 * statement is content, not an effect.
 */
export function TextReveal({ children, className }: TextRevealProps) {
  const safe = useMotionSafe();
  const sectionRef = React.useRef<HTMLDivElement | null>(null);
  const { scrollYProgress } = useScroll({ target: sectionRef });
  const words = children.split(' ');

  if (!safe) {
    return (
      <div className={cn('mx-auto max-w-4xl px-4 py-20', className)}>
        <p className="text-2xl font-semibold tracking-tight md:text-3xl lg:text-4xl">
          {children}
        </p>
      </div>
    );
  }
  return (
    <div ref={sectionRef} className={cn('relative z-0 h-[200vh]', className)}>
      <div className="sticky top-0 mx-auto flex h-[50%] max-w-4xl items-center px-4 py-20">
        <span className="flex flex-wrap p-5 text-2xl font-semibold tracking-tight md:p-8 md:text-3xl lg:p-10 lg:text-4xl">
          {words.map((word, i) => (
            <Word
              key={i}
              progress={scrollYProgress}
              range={[i / words.length, i / words.length + 1 / words.length]}
            >
              {word}
            </Word>
          ))}
        </span>
      </div>
    </div>
  );
}

interface WordProps {
  children: React.ReactNode;
  progress: MotionValue<number>;
  range: [number, number];
}

function Word({ children, progress, range }: WordProps) {
  const opacity = useTransform(progress, range, [0, 1]);
  return (
    <span className="relative mx-1 lg:mx-1.5">
      <span
        aria-hidden
        className="absolute"
        style={{ color: 'color-mix(in srgb, currentColor 22%, transparent)' }}
      >
        {children}
      </span>
      <motion.span style={{ opacity }} className="relative">
        {children}
      </motion.span>
    </span>
  );
}
