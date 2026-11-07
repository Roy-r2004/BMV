/**
 * The shell every public page plays in. One light field lives behind all of
 * them and survives navigation; each page is a scene and each of its
 * `Shot`s a shot. Moving between pages is a film cut: the bars close to a
 * slit with the next scene's title, the old page stays on screen until they
 * have closed, the camera pushes in, and the bars open on the new page.
 * The firm's footer closes every scene.
 */
import { Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useOutlet } from 'react-router-dom';
import SiteFooter from '../components/SiteFooter';
import { scrollToHashWhenReady } from '../utils/scroll';
import FilmNav from './FilmNav';
import { createLightField, type LightField } from './field';
import { pad2, sceneFor } from './scenes';
import type { ShapeName } from './shapes';
import '../styles/film.css';

const CLOSE_MS = 640;
const OPEN_MS = 520;
const INTRO_KEY = 'bmv_film_intro';

type Cut = { on: boolean; instant: boolean; small: string; title: string };

function prefersReduce() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export default function FilmShell() {
  const location = useLocation();
  const outlet = useOutlet();
  const [reduce] = useState(prefersReduce);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const fieldRef = useRef<LightField | null>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  // the page on screen; during a cut, the page being left
  const [shownPath, setShownPath] = useState(location.pathname);
  const held = useRef<ReactNode>(outlet);
  const same = location.pathname === shownPath;
  useEffect(() => {
    if (same) held.current = outlet;
  });
  const content = same ? outlet : held.current;

  const [cut, setCut] = useState<Cut>({ on: false, instant: false, small: '', title: '' });
  const [rail, setRail] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const shots = useRef<HTMLElement[]>([]);
  const activeRef = useRef(-1);

  // ---------- the field ----------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const field = createLightField(canvas, reduce);
    fieldRef.current = field;
    document.fonts?.ready.then(() => field?.refreshText());
    return () => {
      field?.dispose();
      fieldRef.current = null;
    };
  }, [reduce]);

  // ---------- shots ----------
  const apply = useCallback((el: HTMLElement, quiet: boolean) => {
    const shape = (el.dataset.shape || 'seed') as ShapeName;
    fieldRef.current?.setShape(shape, el.dataset.words ?? '', quiet);
  }, []);

  const pick = useCallback(
    (i: number) => {
      activeRef.current = i;
      setActive(i);
      shots.current.forEach((s, k) => s.classList.toggle('is-on', k === i));
      const el = shots.current[i];
      if (el) apply(el, false);
    },
    [apply],
  );

  const onScroll = useCallback(() => {
    const mid = window.innerHeight * 0.5;
    const list = shots.current;
    for (let i = 0; i < list.length; i++) {
      const r = list[i].getBoundingClientRect();
      if (r.top <= mid && r.bottom > mid) {
        if (i !== activeRef.current) pick(i);
        fieldRef.current?.setDolly((mid - r.top) / r.height - 0.5);
        break;
      }
    }
  }, [pick]);

  // find the shots of the page on screen, and follow the page as it changes
  useEffect(() => {
    const main = mainRef.current;
    if (!main) return;
    let frame = 0;
    const scan = () => {
      const list = Array.from(main.querySelectorAll<HTMLElement>('.film-shot'));
      const changed = list.length !== shots.current.length || list.some((el, k) => el !== shots.current[k]);
      if (changed) {
        shots.current = list;
        setRail(list.map((el) => el.dataset.shot ?? ''));
        activeRef.current = -1;
        if (list.length) pick(0);
      }
      onScroll();
    };
    scan();
    const mo = new MutationObserver((records) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        // a shot on screen that changed its shape or its words: follow it quietly
        const cur = shots.current[activeRef.current];
        if (cur && records.some((r) => r.type === 'attributes' && r.target === cur)) apply(cur, true);
        scan();
      });
    });
    mo.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-shape', 'data-words'] });
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      mo.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [apply, onScroll, pick]);

  // ---------- the cut between pages ----------
  // The timers run from the navigation, not from the swap: the swap itself must
  // not cancel the bars opening again.
  const shownRef = useRef(shownPath);
  useEffect(() => {
    shownRef.current = shownPath;
  }, [shownPath]);
  useEffect(() => {
    const to = location.pathname;
    if (to === shownRef.current) {
      // back to the page still on screen before the cut finished: open the bars again
      setCut((c) => (c.on && !c.instant ? { ...c, on: false } : c));
      return;
    }
    const scene = sceneFor(to);
    if (reduce || !fieldRef.current) {
      setShownPath(to);
      return;
    }
    setCut({ on: true, instant: false, small: `SCENE ${pad2(scene?.number ?? 1)}`, title: scene?.title ?? '' });
    const t1 = window.setTimeout(() => {
      setShownPath(to);
      fieldRef.current?.pushIn(16);
    }, CLOSE_MS);
    const t2 = window.setTimeout(() => setCut((c) => ({ ...c, on: false })), CLOSE_MS + OPEN_MS);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [location.pathname, reduce]);

  // on a new page: its anchor if the link named one, otherwise the top
  const lastShown = useRef(shownPath);
  useEffect(() => {
    if (location.pathname !== shownPath) return;
    const fresh = lastShown.current !== shownPath;
    lastShown.current = shownPath;
    if (location.hash) return scrollToHashWhenReady(location.hash);
    if (fresh) window.scrollTo(0, 0);
    return undefined;
  }, [shownPath, location.pathname, location.hash]);

  // ---------- the opening title, once a visit ----------
  useEffect(() => {
    let seen = false;
    try {
      seen = sessionStorage.getItem(INTRO_KEY) === '1';
      sessionStorage.setItem(INTRO_KEY, '1');
    } catch {
      seen = true;
    }
    if (seen || reduce || !fieldRef.current) return;
    const scene = sceneFor(window.location.pathname);
    setCut({ on: true, instant: true, small: 'BUILD MY VERSION', title: scene?.number === 1 ? 'Your idea, in light' : scene?.title ?? '' });
    fieldRef.current.pushIn(21);
    const t0 = window.setTimeout(() => setCut((c) => ({ ...c, instant: false })), 60);
    const t1 = window.setTimeout(() => setCut((c) => ({ ...c, on: false })), 1500);
    return () => {
      window.clearTimeout(t0);
      window.clearTimeout(t1);
      // never leave the bars closed: in development React runs this twice, and
      // the second run finds the intro already seen
      setCut((c) => ({ ...c, on: false, instant: false }));
    };
  }, [reduce]);

  // ---------- the cursor ring, and buttons that lean toward the pointer ----------
  useEffect(() => {
    if (reduce || window.matchMedia('(pointer: coarse)').matches) return;
    const ring = ringRef.current;
    let tx = -100, ty = -100, cx = -100, cy = -100, raf = 0;
    let lean: HTMLElement | null = null;
    const onMove = (e: PointerEvent) => {
      tx = e.clientX;
      ty = e.clientY;
      const target = e.target as Element | null;
      ring?.classList.toggle('is-big', !!target?.closest('a, button, textarea, input, select, [role="button"]'));
      const pill = target?.closest<HTMLElement>('.film-pill') ?? null;
      if (lean && lean !== pill) lean.style.transform = '';
      lean = pill;
      if (pill) {
        const r = pill.getBoundingClientRect();
        pill.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.18}px, ${(e.clientY - r.top - r.height / 2) * 0.3}px)`;
      }
    };
    const follow = () => {
      cx += (tx - cx) * 0.2;
      cy += (ty - cy) * 0.2;
      if (ring) ring.style.transform = `translate(${cx}px, ${cy}px)`;
      raf = requestAnimationFrame(follow);
    };
    raf = requestAnimationFrame(follow);
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      if (lean) lean.style.transform = '';
    };
  }, [reduce]);

  const goShot = (i: number) => shots.current[i]?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });

  return (
    <div className="film">
      <div className="film-stage" aria-hidden="true" />
      <div className="film-glow" aria-hidden="true" />
      <canvas ref={canvasRef} className="film-canvas" aria-hidden="true" />
      <div className="film-veil" aria-hidden="true" />

      <FilmNav />

      {rail.length > 1 ? (
        <ol className="film-rail" aria-label="Sections of this page">
          {rail.map((t, i) => (
            <li key={`${shownPath}-${i}`}>
              <button type="button" aria-current={i === active ? 'step' : undefined} onClick={() => goShot(i)}>
                {t}
                <i aria-hidden="true" />
              </button>
            </li>
          ))}
        </ol>
      ) : null}

      <main ref={mainRef} className="film-main">
        <Suspense fallback={null}>{content}</Suspense>
      </main>
      <div className="film-foot">
        <SiteFooter />
      </div>

      <div className={`film-cut${cut.on ? ' is-in' : ''}${cut.instant ? ' is-instant' : ''}`} aria-hidden="true">
        <div className="film-cut-band" />
        <div className="film-cut-top" />
        <div className="film-cut-bottom" />
        <div className="film-cut-card">
          <small>{cut.small}</small>
          <span>{cut.title}</span>
        </div>
      </div>
      <div className="film-grain" aria-hidden="true" />
      <div className="film-ring" ref={ringRef} aria-hidden="true" />
    </div>
  );
}
