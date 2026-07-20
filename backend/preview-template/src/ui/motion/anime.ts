/**
 * Page-level choreography via anime.js.
 * React-bound UI (chat bubbles, AnimatePresence) stays on motion/react.
 */
import { animate, stagger, type AnimationParams, type JSAnimation } from 'animejs';

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const easeOut = 'out(3)';

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
  const { delay = 0, duration = 820, y = 22, blur = 6 } = opts;
  return animate(target, {
    opacity: [0, 1],
    translateY: [y, 0],
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
  const { delay = 0, duration = 560, y = 18, staggerMs = 90 } = opts;
  return animate(targets, {
    opacity: [0, 1],
    translateY: [y, 0],
    scale: [0.985, 1],
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
  const { duration = 680, y = 28 } = opts;
  node.style.opacity = '0';
  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        animate(node, {
          opacity: [0, 1],
          translateY: [y, 0],
          ease: easeOut,
          duration,
        } as AnimationParams);
        io.disconnect();
      }
    },
    { threshold: 0.18, rootMargin: '0px 0px -8% 0px' },
  );
  io.observe(node);
  return () => io.disconnect();
}
