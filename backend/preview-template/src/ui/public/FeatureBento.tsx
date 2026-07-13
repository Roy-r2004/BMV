import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem, useMotionSafe } from '../motion';
import { cn } from '../lib/cn';

export interface FeatureBentoItem {
  title: string;
  description: string;
}

export type FeatureBentoVariant = 'bento' | 'grid' | 'alternating';

export interface FeatureBentoProps {
  heading: string;
  items: FeatureBentoItem[];
  description?: string;
  variant?: FeatureBentoVariant;
  className?: string;
}

/** Editorial feature section — alternating is a snap-scroll chapter rail. */
export function FeatureBento({
  className,
  description,
  heading,
  items,
  variant = 'bento',
}: FeatureBentoProps) {
  const safe = useMotionSafe();
  const scrollerRef = React.useRef<HTMLDivElement>(null);
  const [active, setActive] = React.useState(0);

  const updateActive = React.useCallback(() => {
    const node = scrollerRef.current;
    if (!node) return;
    const cards = [...node.querySelectorAll<HTMLElement>('[data-chapter]')];
    if (!cards.length) return;
    const mid = node.scrollLeft + node.clientWidth / 2;
    let best = 0;
    let bestDist = Number.POSITIVE_INFINITY;
    cards.forEach((card, index) => {
      const center = card.offsetLeft + card.offsetWidth / 2;
      const dist = Math.abs(center - mid);
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    setActive(best);
  }, []);

  React.useEffect(() => {
    if (variant !== 'alternating') return;
    const node = scrollerRef.current;
    if (!node) return;
    updateActive();
    node.addEventListener('scroll', updateActive, { passive: true });
    window.addEventListener('resize', updateActive);
    return () => {
      node.removeEventListener('scroll', updateActive);
      window.removeEventListener('resize', updateActive);
    };
  }, [updateActive, variant, items.length]);

  const scrollTo = (index: number) => {
    const node = scrollerRef.current;
    const card = node?.querySelectorAll<HTMLElement>('[data-chapter]')[index];
    card?.scrollIntoView({ behavior: safe ? 'smooth' : 'auto', inline: 'center', block: 'nearest' });
  };

  return (
    <section className={cn('px-6 py-28 lg:px-12 lg:py-36', className)}>
      <div className="mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-end lg:gap-16">
          <h2 className="font-display text-[clamp(3rem,6vw,5.5rem)] italic leading-[0.92] tracking-[-0.04em] text-foreground">
            {heading}
          </h2>
          {description ? (
            <p className="max-w-md text-base leading-8 text-muted lg:justify-self-end lg:pb-2">{description}</p>
          ) : null}
        </MotionReveal>

        {variant === 'grid' ? (
          <MotionStagger className="mt-16 grid gap-px bg-border-subtle md:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <MotionStaggerItem key={item.title}>
                <article className="bg-background p-8">
                  <h3 className="text-xl font-semibold tracking-tight text-foreground">{item.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-muted">{item.description}</p>
                </article>
              </MotionStaggerItem>
            ))}
          </MotionStagger>
        ) : null}

        {variant === 'bento' ? (
          <MotionStagger className="mt-20">
            {items.map((item, index) => (
              <MotionStaggerItem key={item.title}>
                <article className="grid gap-4 border-t border-foreground/12 py-12 md:grid-cols-12 md:gap-10 md:py-14">
                  <p className="font-display text-4xl italic text-foreground/25 md:col-span-2">
                    {String(index + 1).padStart(2, '0')}
                  </p>
                  <div className="md:col-span-5">
                    <h3 className="font-display text-[clamp(1.85rem,3vw,2.75rem)] italic leading-[1.05] tracking-tight text-foreground">
                      {item.title}
                    </h3>
                  </div>
                  <p className="text-base leading-8 text-muted md:col-span-5 md:pt-2">{item.description}</p>
                </article>
              </MotionStaggerItem>
            ))}
          </MotionStagger>
        ) : null}

        {variant === 'alternating' ? (
          <div className="mt-14 lg:mt-20">
            <div className="mb-7 flex items-center justify-between gap-4">
              <p className="text-[11px] font-semibold tracking-[0.18em] text-muted uppercase">
                Guest path · {String(active + 1).padStart(2, '0')} / {String(items.length).padStart(2, '0')}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Previous chapter"
                  disabled={active <= 0}
                  onClick={() => scrollTo(Math.max(0, active - 1))}
                  className="inline-flex h-9 w-9 items-center justify-center border border-border-subtle bg-card text-sm text-foreground transition disabled:opacity-30"
                >
                  ←
                </button>
                <button
                  type="button"
                  aria-label="Next chapter"
                  disabled={active >= items.length - 1}
                  onClick={() => scrollTo(Math.min(items.length - 1, active + 1))}
                  className="inline-flex h-9 w-9 items-center justify-center border border-border-subtle bg-card text-sm text-foreground transition disabled:opacity-30"
                >
                  →
                </button>
              </div>
            </div>

            <div
              className={cn(
                'relative',
                '[mask-image:linear-gradient(to_right,transparent,black_1.5rem,black_calc(100%-2rem),transparent)]',
                '[-webkit-mask-image:linear-gradient(to_right,transparent,black_1.5rem,black_calc(100%-2rem),transparent)]'
              )}
            >
              <div
                ref={scrollerRef}
                className={cn(
                  '-mx-6 flex snap-x snap-mandatory gap-8 overflow-x-auto px-6 pb-3 scroll-px-6 lg:mx-0 lg:gap-10 lg:px-1 lg:scroll-px-1',
                  '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
                )}
              >
                {items.map((item, index) => (
                  <article
                    key={item.title}
                    data-chapter
                    className={cn(
                      'flex w-[min(84vw,30rem)] shrink-0 snap-center flex-col justify-between border-y border-foreground/10 py-9 sm:w-[min(68vw,34rem)] lg:min-h-[22rem] lg:py-11',
                      'border-l border-l-foreground/10 pl-7 lg:pl-9',
                      active === index ? 'border-l-foreground/45' : ''
                    )}
                  >
                    <div>
                      <p className="font-display text-5xl italic leading-none tracking-tight text-foreground/18">
                        {String(index + 1).padStart(2, '0')}
                      </p>
                      <h3 className="mt-9 max-w-[14ch] font-display text-[clamp(2rem,3vw,2.85rem)] italic leading-[1.02] tracking-tight text-foreground">
                        {item.title}
                      </h3>
                    </div>
                    <p className="mt-12 max-w-[28ch] text-[0.95rem] leading-7 text-muted">{item.description}</p>
                  </article>
                ))}
                <div className="w-[12vw] shrink-0 snap-none lg:w-40" aria-hidden="true" />
              </div>
            </div>

            <div className="mt-7 flex items-center gap-2" role="tablist" aria-label="Feature chapters">
              {items.map((item, index) => (
                <button
                  key={item.title}
                  type="button"
                  role="tab"
                  aria-selected={active === index}
                  aria-label={`Go to ${item.title}`}
                  onClick={() => scrollTo(index)}
                  className={cn(
                    'h-1.5 rounded-full transition-all',
                    active === index ? 'w-9 bg-foreground' : 'w-1.5 bg-foreground/20 hover:bg-foreground/40'
                  )}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
