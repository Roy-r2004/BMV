/**
 * Page-level choreography via anime.js.
 * React-bound UI (chat bubbles, AnimatePresence) stays on motion/react.
 *
 * 3.10 wiring: every timing constant below derives from the recipe's motion
 * identity as a ratio off the legacy base (travel 18px, stagger 90ms), so a
 * bare/unknown recipe resolves to exactly the pre-3.10 values while authored
 * recipes get their temperament — an ops floor snaps in 6px hops, nocturne
 * drifts 22px at 130ms. The anime ease swaps to the identity's cubic-bezier
 * only when a recipe authored one; 'out(3)' stays the un-authored voice.
 */
import { animate, stagger, type AnimationParams, type JSAnimation } from 'animejs';

import { motionIdentity, motionIsAuthored } from '../../lib/motion-identity';

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const identity = motionIdentity();

/**
 * The recipe's rhythm as multipliers off the legacy base. travel: amplitude
 * (18px base); pace: stagger cadence (90ms base); tempo: duration scale —
 * pace clamped so extreme staggers stay watchable.
 */
export const motionRhythm = {
  travel: (Number.parseFloat(identity.travel) || 18) / 18,
  pace: identity.staggerMs / 90,
  tempo: Math.min(1.4, Math.max(0.45, identity.staggerMs / 90)),
} as const;

const easeOut = motionIsAuthored()
  ? `cubicBezier(${identity.ease.join(',')})`
  : 'out(3)';

export type EntranceOpts = {
  delay?: number;
  duration?: number;
  y?: number;
  blur?: number;
};

/** Fade + rise a single element (hero lines, CTAs). */
export function playEntrance(
  target: Element | Element[] | NodeListOf<Element> | string,
  opts: EntranceOpts = {},
): JSAnimation | null {
  if (prefersReducedMotion()) return null;
  const {
    delay = 0,
    duration = 1100 * motionRhythm.tempo,
    y = 42 * motionRhythm.travel,
    blur = 14,
  } = opts;
  return animate(target, {
    opacity: [0, 1],
    translateY: [y, 0],
    scale: [1.04, 1],
    filter: [`blur(${blur}px)`, 'blur(0px)'],
    ease: easeOut,
    duration,
    delay,
  } as AnimationParams);
}

/** Stagger children into view (feature rows, cards). */
export function staggerIn(
  targets: Element | Element[] | NodeListOf<Element> | string,
  opts: EntranceOpts & { staggerMs?: number } = {},
): JSAnimation | null {
  if (prefersReducedMotion()) return null;
  const {
    delay = 0,
    duration = 720 * motionRhythm.tempo,
    y = 36 * motionRhythm.travel,
    staggerMs = 110 * motionRhythm.pace,
  } = opts;
  return animate(targets, {
    opacity: [0, 1],
    translateY: [y, 0],
    scale: [0.96, 1],
    filter: ['blur(8px)', 'blur(0px)'],
    ease: easeOut,
    duration,
    delay: stagger(staggerMs, { start: delay }),
  } as AnimationParams);
}

/**
 * Draw-in polish for chart SVGs — animates stroke paths and series groups.
 * Safe no-op when the container has no SVG paths yet.
 */
export function drawChart(container: Element | null, opts: { duration?: number } = {}): JSAnimation | null {
  if (!container || prefersReducedMotion()) return null;
  const { duration = 1100 } = opts;
  const paths = container.querySelectorAll(
    'path.recharts-curve, path.recharts-area, .recharts-bar-rectangle, .recharts-area-area',
  );
  if (!paths.length) {
    return animate(container, {
      opacity: [0, 1],
      translateY: [10, 0],
      ease: easeOut,
      duration: 480,
    } as AnimationParams);
  }
  paths.forEach((path) => {
    const el = path as SVGPathElement;
    try {
      const len = typeof el.getTotalLength === 'function' ? el.getTotalLength() : 0;
      if (len > 0) {
        el.style.strokeDasharray = String(len);
        el.style.strokeDashoffset = String(len);
      }
    } catch {
      /* non-path geometry */
    }
  });
  return animate(paths, {
    opacity: [0, 1],
    strokeDashoffset: [null, 0],
    ease: easeOut,
    duration,
    delay: stagger(40),
  } as AnimationParams);
}

/** Scroll-linked section reveal. Returns cleanup. */
export function observeSectionReveal(
  el: Element,
  opts: EntranceOpts = {},
): () => void {
  const node = el as HTMLElement;
  if (prefersReducedMotion()) {
    node.style.opacity = '1';
    return () => undefined;
  }
  const { duration = 920 * motionRhythm.tempo, y = 56 * motionRhythm.travel } = opts;
  node.style.opacity = '0';
  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        animate(node, {
          opacity: [0, 1],
          translateY: [y, 0],
          scale: [0.97, 1],
          filter: ['blur(10px)', 'blur(0px)'],
          ease: easeOut,
          duration,
        } as AnimationParams);
        io.disconnect();
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -12% 0px' },
  );
  io.observe(node);
  return () => io.disconnect();
}
