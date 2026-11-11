import { useEffect, useRef, type ReactNode } from 'react';

/**
 * The home page's opening. A data hall in a frame, the headline and the idea
 * box over it. The stage is pinned while the visitor scrolls: the page goes
 * black, the frame steps back and tilts, and the consultation's layers fan
 * out around it, one outline per step, while the line under it comes up.
 * Scroll progress is one CSS variable, `--p`, from 0 to 1; the stylesheet
 * does the rest. With reduced motion the stage is still and nothing pins.
 */
export default function FramedHero({
  children,
  layers,
  after,
}: {
  children: ReactNode;
  /** The consultation's steps, front to back. */
  layers: readonly string[];
  /** What comes up under the frame once it has stepped back. */
  after: ReactNode;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const stage = stageRef.current;
    if (!wrap || !stage) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      wrap.classList.add('is-still');
      return;
    }
    let frame = 0;
    const update = () => {
      const r = wrap.getBoundingClientRect();
      const run = Math.max(1, r.height - window.innerHeight);
      const p = Math.min(1, Math.max(0, -r.top / run));
      wrap.style.setProperty('--p', p.toFixed(4));
      // the bar reads the stage's tone: white page first, black once it has gone dark
      const tone = p > 0.18 ? 'dark' : 'light';
      if (stage.dataset.tone !== tone) stage.dataset.tone = tone;
      // once the words have faded, the idea box stops taking clicks and focus
      stage.classList.toggle('is-past', p > 0.3);
    };
    const soon = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', soon, { passive: true });
    window.addEventListener('resize', soon);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', soon);
      window.removeEventListener('resize', soon);
    };
  }, []);

  return (
    <div className="fh" ref={wrapRef}>
      <div className="fh-stage" ref={stageRef} data-tone="light">
        <div className="fh-layers" aria-hidden="true">
          {layers.map((name, i) => (
            <div className="fh-layer" key={name} style={{ ['--i' as string]: i + 1 }}>
              <span>
                {String(i + 1).padStart(2, '0')} {name}
              </span>
            </div>
          ))}
        </div>
        <div className="fh-frame">
          <div className="fh-hall" aria-hidden="true">
            <div className="fh-glow" />
            <div className="fh-wall fh-wall--l">
              {Array.from({ length: 10 }, (_, i) => (
                <i key={i} className={i % 3 === 1 ? 'dim' : undefined} />
              ))}
            </div>
            <div className="fh-wall fh-wall--r">
              {Array.from({ length: 10 }, (_, i) => (
                <i key={i} className={i % 3 === 2 ? 'dim' : undefined} />
              ))}
            </div>
            <div className="fh-floor" />
            <div className="fh-photo" />
            <div className="fh-shade" />
          </div>
          <div className="fh-copy">{children}</div>
        </div>
        <div className="fh-after">{after}</div>
      </div>
    </div>
  );
}
