/**
 * The shell every public page sits in: the bar, the page, the firm's footer.
 * Sections are white or black; the bar has no background of its own and
 * takes the colour that reads on the section under it. A section's headline
 * rises in as the section reaches the middle of the screen.
 */
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useOutlet } from 'react-router-dom';
import SiteFooter from '../components/SiteFooter';
import { scrollToHashWhenReady } from '../utils/scroll';
import FilmNav from './FilmNav';
import '../styles/film.css';

/** The bar's height: the section under its middle decides its colour. */
const BAR_PROBE = 36;

export default function FilmShell() {
  const location = useLocation();
  const outlet = useOutlet();
  const mainRef = useRef<HTMLElement>(null);
  const [tone, setTone] = useState<'light' | 'dark'>('light');

  const follow = useCallback(() => {
    const main = mainRef.current;
    if (!main) return;
    const mid = window.innerHeight * 0.5;
    let under: 'light' | 'dark' = 'light';
    // the newest marker under the bar wins: a pinned hero may set its own tone as it darkens
    main.querySelectorAll<HTMLElement>('[data-tone]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.top <= BAR_PROBE && r.bottom > BAR_PROBE) under = el.dataset.tone === 'dark' ? 'dark' : 'light';
      if (el.classList.contains('film-shot')) el.classList.toggle('is-on', r.top <= mid + window.innerHeight * 0.25 && r.bottom > mid * 0.4);
    });
    setTone(under);
  }, []);

  useEffect(() => {
    const main = mainRef.current;
    if (!main) return;
    let frame = 0;
    const soon = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(follow);
    };
    soon();
    const mo = new MutationObserver(soon);
    mo.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-tone'] });
    window.addEventListener('scroll', soon, { passive: true });
    window.addEventListener('resize', soon);
    return () => {
      mo.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', soon);
      window.removeEventListener('resize', soon);
    };
  }, [follow]);

  // on a new page: its anchor if the link named one, otherwise the top
  const lastPath = useRef(location.pathname);
  useEffect(() => {
    const fresh = lastPath.current !== location.pathname;
    lastPath.current = location.pathname;
    if (location.hash) return scrollToHashWhenReady(location.hash);
    if (fresh) window.scrollTo(0, 0);
    return undefined;
  }, [location.pathname, location.hash]);

  return (
    <div className="film">
      <FilmNav tone={tone} />
      <main ref={mainRef} className="film-main">
        <Suspense fallback={null}>{outlet}</Suspense>
      </main>
      <div className="film-foot">
        <SiteFooter />
      </div>
    </div>
  );
}
