/**
 * jsdom gaps the catalogue's motion layer depends on.
 *
 * `src/ui/motion/anime.ts` constructs an `IntersectionObserver` to drive
 * scroll-reveal, and jsdom does not implement one. Any test that renders a
 * component wrapped in `MotionReveal` — which is most public catalogue
 * components — dies in a passive effect with `IntersectionObserver is not
 * defined`, pointing at template source rather than at the harness.
 *
 * These are deliberately inert rather than faithful: a stub that never fires
 * leaves revealed content in its initial state, which is what a
 * `prefers-reduced-motion` visitor sees. Tests assert structure and links, not
 * animation. If a test ever needs a reveal to fire, trigger it explicitly
 * rather than making this stub clever.
 */

class InertIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = '';
  readonly thresholds: ReadonlyArray<number> = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

if (!('IntersectionObserver' in globalThis)) {
  Object.defineProperty(globalThis, 'IntersectionObserver', {
    writable: true,
    configurable: true,
    value: InertIntersectionObserver,
  });
}

// `anime.ts` guards on `!window.matchMedia`, so absence is already handled — but
// it resolves to "motion is fine", and reduced motion is the quieter default for
// a DOM assertion.
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) =>
      ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  });
}
