import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * The chosen item of a showroom (Examples, Solutions). Until the visitor
 * picks one it steps through the items every `ms`; the first pick stops it for
 * good. With reduced motion it never steps on its own.
 */
export function useCycle(count: number, ms: number) {
  const [index, setIndex] = useState(0);
  const picked = useRef(false);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(() => {
      if (!picked.current) setIndex((i) => (i + 1) % count);
    }, ms);
    return () => window.clearInterval(id);
  }, [count, ms]);

  const pick = useCallback((i: number) => {
    picked.current = true;
    setIndex(i);
  }, []);

  return [index, pick] as const;
}
