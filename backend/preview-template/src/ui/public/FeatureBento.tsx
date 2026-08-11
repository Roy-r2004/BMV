import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem, useMotionSafe } from '../motion';
import { cn } from '../lib/cn';
import {
  currentRecipeId,
  FEATURE_VARIANTS,
  recipeFeatureVariant,
  type FeatureVariant,
} from '../../lib/recipe';
import { KitImage } from '../lib/KitImage';

export interface FeatureBentoItem {
  title: string;
  description: string;
  imageSrc?: string;
  imageAlt?: string;
  href?: string;
}

export type FeatureBentoVariant = 'bento' | 'grid' | 'alternating';

export interface FeatureBentoProps {
  heading: string;
  items: FeatureBentoItem[];
  description?: string;
  variant?: FeatureBentoVariant;
  /** When items lack imageSrc, pull from this pool (card1/card2/…) so bento stays cinematic. */
  imagePool?: string[];
  className?: string;
  /**
   * Content below the grid — request 46's contact page composed its form into the
   * section this way. Rendered after the items, inside the same container.
   */
  children?: React.ReactNode;
}

/** Feature section — default variant comes from the active design recipe. */
export function FeatureBento({ children, ...props }: FeatureBentoProps) {
  const section = <FeatureBentoBody {...props} />;
  if (!children) return section;
  return (
    <>
      {section}
      {children}
    </>
  );
}

function FeatureBentoBody({
  className,
  description,
  heading,
  imagePool,
  items: itemsProp = [],
  variant: variantProp,
}: Omit<FeatureBentoProps, 'children'>) {
  const safe = useMotionSafe();
  // A valid caller-supplied variant is honoured (3.1 — this prop used to be
  // destructured into a discard); the recipe's composition is the default.
  const resolved: FeatureVariant =
    variantProp && (FEATURE_VARIANTS as readonly string[]).includes(variantProp)
      ? variantProp
      : recipeFeatureVariant(currentRecipeId());
  const pool = Array.isArray(imagePool) ? imagePool.filter(Boolean) : [];
  const items = (Array.isArray(itemsProp) ? itemsProp : []).map((item, index) => ({
    ...item,
    imageSrc: item.imageSrc || (pool.length ? pool[index % pool.length] : undefined),
  }));
  const scrollerRef = React.useRef<HTMLDivElement>(null);
  const [active, setActive] = React.useState(0);
  // A heading and a "01 / 00" counter over nothing reads as a broken page.
  const isEmpty = items.length === 0;

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
    if (resolved !== 'alternating') return;
    const node = scrollerRef.current;
    if (!node) return;
    updateActive();
    node.addEventListener('scroll', updateActive, { passive: true });
    window.addEventListener('resize', updateActive);
    return () => {
      node.removeEventListener('scroll', updateActive);
      window.removeEventListener('resize', updateActive);
    };
  }, [updateActive, resolved, items.length]);

  const scrollTo = (index: number) => {
    const node = scrollerRef.current;
    const card = node?.querySelectorAll<HTMLElement>('[data-chapter]')[index];
    card?.scrollIntoView({ behavior: safe ? 'smooth' : 'auto', inline: 'center', block: 'nearest' });
  };

  if (isEmpty) return null;

  return (
    <section
      className={cn(
        'relative px-6 py-28 lg:px-12 lg:py-36',
        resolved === 'grid' && 'bg-[color-mix(in_srgb,var(--color-brand)_3%,var(--color-background))]',
        resolved === 'bento' && 'bg-background',
        resolved === 'alternating' && 'bg-card/40',
        className
      )}
      data-feature-variant={resolved}
    >
      <div className="mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-end lg:gap-16">
          <h2
            className={cn(
              'font-display text-[clamp(3rem,6vw,5.5rem)] leading-[0.92] tracking-[-0.04em] text-foreground',
              resolved === 'grid' ? 'not-italic' : 'italic'
            )}
          >
            {heading}
          </h2>
          {description ? (
            <p className="max-w-md text-base leading-8 text-muted lg:justify-self-end lg:pb-2">{description}</p>
          ) : null}
        </MotionReveal>

        {resolved === 'grid' ? (
          <MotionStagger className="mt-16 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {items.map((item, index) => (
              <MotionStaggerItem key={item.title}>
                <article
                  className={cn(
                    'group relative overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card p-8 shadow-[var(--shadow-ui)] transition duration-500 hover:-translate-y-1 hover:border-brand/25',
                    index === 0 && 'lg:col-span-1 lg:ring-1 lg:ring-brand/25',
                    index === 1 && 'lg:ring-1 lg:ring-border-subtle'
                  )}
                >
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-brand)_18%,transparent),transparent_70%)] opacity-0 transition group-hover:opacity-100"
                  />
                  <div className="ui-gradient-border pointer-events-none absolute inset-0 opacity-0 transition group-hover:opacity-100" />
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-brand/70">
                    {String(index + 1).padStart(2, '0')}
                  </p>
                  <h3 className="mt-3 text-xl font-semibold tracking-tight text-foreground">{item.title}</h3>
                  <p className="mt-3 text-sm leading-7 text-muted">{item.description}</p>
                </article>
              </MotionStaggerItem>
            ))}
          </MotionStagger>
        ) : null}

        {resolved === 'bento' ? (
          items.some((item) => item.imageSrc) ? (
            <MotionStagger className="mt-16 grid gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-5">
              {items.map((item, index) => {
                const body = (
                  <article
                    className={cn(
                      'group relative isolate min-h-[22rem] overflow-hidden bg-foreground text-background',
                      index === 0 && 'md:col-span-2 md:min-h-[28rem]'
                    )}
                  >
                    {item.imageSrc ? (
                      <KitImage
                        src={item.imageSrc}
                        alt={item.imageAlt ?? ''}
                        className={cn(
                          'absolute inset-0 h-full w-full object-cover transition duration-700 group-hover:scale-[1.04]',
                          safe && index === 0 && 'ui-kenburns'
                        )}
                      />
                    ) : null}
                    <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-brand/10" />
                    <div className="ui-film-grain opacity-[0.1]" />
                    <div className="relative z-10 flex h-full flex-col justify-end p-7 lg:p-9">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-white/50">
                        {String(index + 1).padStart(2, '0')}
                      </p>
                      <h3 className="mt-3 font-display text-[clamp(1.75rem,3vw,2.6rem)] leading-[1.02] tracking-tight">
                        {item.title}
                      </h3>
                      <p className="mt-3 max-w-md text-sm leading-7 text-white/70">{item.description}</p>
                    </div>
                  </article>
                );
                return (
                  <MotionStaggerItem key={item.title}>
                    {item.href ? (
                      <a href={item.href} className="block outline-none focus-visible:ring-2 focus-visible:ring-brand">
                        {body}
                      </a>
                    ) : (
                      body
                    )}
                  </MotionStaggerItem>
                );
              })}
            </MotionStagger>
          ) : (
            /* Text-only fallback — stacked spotlight cards, NOT ProcessSection row lists */
            <MotionStagger className="mt-16 grid gap-5 lg:grid-cols-12">
              {items.map((item, index) => (
                <MotionStaggerItem
                  key={item.title}
                  className={cn(
                    index === 0 && 'lg:col-span-7',
                    index === 1 && 'lg:col-span-5',
                    index >= 2 && 'lg:col-span-4'
                  )}
                >
                  <article
                    className={cn(
                      'group relative flex h-full flex-col overflow-hidden rounded-[calc(var(--radius-ui)+0.5rem)] border border-border-subtle bg-card p-8 shadow-[var(--shadow-ui)] transition duration-500 hover:-translate-y-1',
                      index === 0 && 'min-h-[18rem] bg-foreground text-background lg:p-10'
                    )}
                  >
                    <p
                      className={cn(
                        'text-[11px] font-semibold uppercase tracking-[0.22em]',
                        index === 0 ? 'text-white/45' : 'text-brand/70'
                      )}
                    >
                      Highlight {String(index + 1).padStart(2, '0')}
                    </p>
                    <h3
                      className={cn(
                        'mt-5 font-display leading-[1.05] tracking-tight',
                        index === 0
                          ? 'text-[clamp(2rem,3.5vw,3rem)] text-white'
                          : 'text-[clamp(1.5rem,2.4vw,2.1rem)] text-foreground'
                      )}
                    >
                      {item.title}
                    </h3>
                    <p
                      className={cn(
                        'mt-4 text-sm leading-7',
                        index === 0 ? 'max-w-md text-white/70' : 'text-muted'
                      )}
                    >
                      {item.description}
                    </p>
                  </article>
                </MotionStaggerItem>
              ))}
            </MotionStagger>
          )
        ) : null}

        {resolved === 'alternating' ? (
          <div className="mt-14 lg:mt-20">
            <div className="mb-7 flex items-center justify-between gap-4">
              <p className="text-[11px] font-semibold tracking-[0.18em] text-muted uppercase">
                {String(active + 1).padStart(2, '0')} / {String(items.length).padStart(2, '0')}
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
                      'border-l-[3px] pl-7 lg:pl-9 transition-[border-color,background-color,box-shadow] duration-300',
                      active === index
                        ? 'border-l-brand bg-card/70 shadow-[var(--shadow-ui)]'
                        : 'border-l-foreground/10'
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
                    active === index ? 'w-9 bg-brand' : 'w-1.5 bg-foreground/20 hover:bg-foreground/40'
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
