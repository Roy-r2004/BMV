import * as React from 'react';

import { cn } from '../lib/cn';
import {
  observeSectionReveal,
  playEntrance,
  prefersReducedMotion,
  staggerIn,
} from './anime';

type BoxProps = {
  children?: React.ReactNode;
  className?: string;
  role?: string;
};

/** Hero line — anime.js entrance on mount. */
export function AnimeHeroItem({
  children,
  className,
  index = 0,
}: BoxProps & { index?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      el.style.opacity = '1';
      el.style.filter = 'none';
      el.style.transform = 'none';
      return;
    }
    el.style.opacity = '0';
    let anim: ReturnType<typeof playEntrance> = null;
    try {
      anim = playEntrance(el, { delay: 60 + index * 110, y: 24, blur: 5 });
    } catch {
      el.style.opacity = '1';
      return;
    }
    // Never leave content stuck invisible if the animation engine no-ops.
    const fallback = window.setTimeout(() => {
      if (el.style.opacity === '0' || getComputedStyle(el).opacity === '0') {
        el.style.opacity = '1';
        el.style.filter = 'none';
        el.style.transform = 'none';
      }
    }, 1200 + index * 110);
    return () => {
      window.clearTimeout(fallback);
      anim?.pause?.();
    };
  }, [index]);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/** Section reveal on scroll via anime.js. */
export function AnimeReveal({ children, className }: BoxProps) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return observeSectionReveal(el);
  }, []);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/** Stagger children when the container enters the viewport. */
export function AnimeStagger({ children, className, role }: BoxProps) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) return;

    const kids = Array.from(el.children) as HTMLElement[];
    kids.forEach((kid) => {
      kid.style.opacity = '0';
    });

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          staggerIn(kids, { staggerMs: 85, y: 20 });
          io.disconnect();
        }
      },
      { threshold: 0.16 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className={cn(className)} role={role}>
      {children}
    </div>
  );
}

export function AnimeStaggerItem({ children, className, role }: BoxProps) {
  return (
    <div className={className} role={role} data-anime-stagger-item="">
      {children}
    </div>
  );
}
