import * as React from 'react';

import { AnimeReveal, AnimeStagger, AnimeStaggerItem } from '../motion';
import { AppLink } from '../lib/AppLink';
import { Badge } from '../core/Badge';
import { cn } from '../lib/cn';

export type CatalogItem = {
  /** Stable id — also the detail-route segment when `href` is absent. */
  id: string;
  title: string;
  description?: string;
  imageSrc?: string;
  imageAlt?: string;
  /** Free-text meta shown under the title (price, dimensions, medium). */
  meta?: string;
  /** Filter facet. Cards with no category are always visible. */
  category?: string;
  /** e.g. "Available", "Sold", "Reserved". */
  status?: string;
  badge?: string;
  /** Overrides the derived `${detailBase}/${id}` link. */
  href?: string;
};

export type CatalogGridProps = {
  heading?: string;
  description?: string;
  items: CatalogItem[];
  /**
   * Detail route base. Every card links to `${detailBase}/${item.id}` unless the
   * item carries its own `href`, so a browsable card is never a dead end.
   */
  detailBase?: string;
  /** Show category facets when the items declare more than one. */
  filterable?: boolean;
  /** Noun for counts and empty state — "pieces", "products", "properties". */
  itemNoun?: string;
  className?: string;
};

/** `/gallery/1` — tolerates a trailing slash on detailBase and a spacey id. */
export function catalogItemHref(item: CatalogItem, detailBase: string): string {
  if (item.href) return item.href;
  const base = (detailBase || '').replace(/\/+$/, '');
  const segment = encodeURIComponent(String(item.id ?? '').trim());
  return segment ? `${base}/${segment}` : base || '/';
}

function isSoldOut(status?: string): boolean {
  const s = (status || '').toLowerCase();
  return s.includes('sold') || s.includes('reserved') || s.includes('unavailable');
}

/**
 * Uniform browsable catalogue grid — merchandising, not storytelling.
 *
 * Distinct from ProductShowcase, which is an editorial 8/4 mosaic capped at
 * three items. This renders every item passed, and the whole card is the link
 * into the detail route, so browse → select is structural rather than something
 * codegen has to remember to wire.
 */
export function CatalogGrid({
  className,
  description,
  detailBase = '/gallery',
  filterable = true,
  heading = 'The collection',
  itemNoun = 'pieces',
  items,
}: CatalogGridProps) {
  const [category, setCategory] = React.useState('All');

  const categories = React.useMemo(() => {
    const set = new Set(items.map((i) => i.category).filter(Boolean) as string[]);
    return ['All', ...Array.from(set)];
  }, [items]);

  const filtered =
    category === 'All' ? items : items.filter((i) => !i.category || i.category === category);

  const showFilters = filterable && categories.length > 2;

  return (
    <section
      id="catalog"
      data-catalog-grid=""
      className={cn('relative isolate px-6 py-20 sm:px-10 lg:px-12 lg:py-28', className)}
    >
      <div className="mx-auto max-w-[92rem]">
        <AnimeReveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-brand">Browse</p>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-6">
            <h2 className="max-w-3xl font-display text-[clamp(2.4rem,5vw,4rem)] leading-[0.95] tracking-[-0.03em] text-foreground">
              {heading}
            </h2>
            <p className="font-mono text-sm tracking-[0.16em] text-muted">
              {filtered.length} {itemNoun}
            </p>
          </div>
          {description ? (
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">{description}</p>
          ) : null}
        </AnimeReveal>

        {showFilters ? (
          <div className="mt-10 flex flex-wrap gap-2" role="group" aria-label={`Filter ${itemNoun}`}>
            {categories.map((option) => {
              const active = option === category;
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setCategory(option)}
                  className={cn(
                    'h-10 rounded-[var(--radius-ui)] border px-4 text-sm transition',
                    'outline-none focus-visible:ring-4 focus-visible:ring-ring/15',
                    active
                      ? 'border-brand/40 bg-brand/10 font-medium text-foreground'
                      : 'border-border-subtle bg-card text-muted hover:text-foreground'
                  )}
                >
                  {option}
                </button>
              );
            })}
          </div>
        ) : null}

        <AnimeStagger
          className="mt-12 grid gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-3"
          role="list"
        >
          {filtered.map((item) => {
            const href = catalogItemHref(item, detailBase);
            const sold = isSoldOut(item.status);
            return (
              <AnimeStaggerItem key={item.id} role="listitem">
                <article className="group relative flex min-w-0 flex-col">
                  {/* Whole-card click target. Accessible name comes from aria-label. */}
                  <AppLink
                    href={href}
                    className="absolute inset-0 z-10 rounded-[var(--radius-ui)] outline-none focus-visible:ring-4 focus-visible:ring-ring/25"
                    aria-label={`View ${item.title}`}
                  />
                  <div className="relative overflow-hidden rounded-[var(--radius-ui)] bg-foreground/5">
                    {item.imageSrc ? (
                      <img
                        src={item.imageSrc}
                        alt={item.imageAlt ?? ''}
                        loading="lazy"
                        className="aspect-[4/5] w-full object-cover transition duration-700 group-hover:scale-[1.03]"
                      />
                    ) : (
                      <div
                        aria-hidden
                        className="aspect-[4/5] w-full bg-[linear-gradient(135deg,color-mix(in_srgb,var(--color-brand)_18%,transparent),transparent_70%)]"
                      />
                    )}
                    {item.badge || sold ? (
                      <div className="absolute left-4 top-4">
                        <Badge variant={sold ? 'outline' : 'default'}>
                          {sold ? item.status : item.badge}
                        </Badge>
                      </div>
                    ) : null}
                  </div>
                  <div className="mt-5 min-w-0">
                    <h3 className="font-display text-[clamp(1.25rem,2vw,1.6rem)] leading-tight tracking-tight text-foreground">
                      {item.title}
                    </h3>
                    {item.meta ? (
                      <p className="mt-2 font-mono text-xs tracking-[0.14em] text-muted uppercase">
                        {item.meta}
                      </p>
                    ) : null}
                    {item.description ? (
                      <p className="mt-3 text-sm leading-6 text-muted">{item.description}</p>
                    ) : null}
                  </div>
                </article>
              </AnimeStaggerItem>
            );
          })}
        </AnimeStagger>

        {filtered.length === 0 ? (
          <p className="mt-10 text-sm text-muted">
            Nothing in {category} yet — try another filter.
          </p>
        ) : null}
      </div>
    </section>
  );
}
