import * as React from 'react';

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

export function FeatureBento({
  className,
  description,
  heading,
  items,
  variant = 'bento',
}: FeatureBentoProps) {
  return (
    <section className={cn('px-6 py-24 lg:px-10 lg:py-28', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <div className="max-w-2xl">
          <h2 className="font-display text-[clamp(2.25rem,4vw,3.4rem)] leading-[1.05] tracking-[-0.03em] text-foreground">
            {heading}
          </h2>
          {description ? <p className="mt-5 text-base leading-7 text-muted sm:text-lg">{description}</p> : null}
        </div>

        {variant === 'grid' ? (
          <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <article key={item.title} className="rounded-[1.35rem] border border-border-subtle bg-card p-7 shadow-[var(--shadow-ui)]">
                <h3 className="text-xl font-semibold tracking-tight text-foreground">{item.title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted">{item.description}</p>
              </article>
            ))}
          </div>
        ) : null}

        {variant === 'alternating' ? (
          <div className="mt-14 space-y-0">
            {items.map((item, index) => (
              <article
                key={item.title}
                className={cn(
                  'grid gap-4 border-t border-border-subtle py-10 md:grid-cols-2 md:gap-16',
                  index % 2 === 1 && 'md:[&>*:first-child]:order-2'
                )}
              >
                <h3 className="font-display text-3xl tracking-tight text-foreground">{item.title}</h3>
                <p className="self-center text-base leading-8 text-muted">{item.description}</p>
              </article>
            ))}
          </div>
        ) : null}

        {variant === 'bento' ? (
          <div className="mt-14 grid gap-4 md:auto-rows-[minmax(12rem,auto)] md:grid-cols-12">
            {items.map((item, index) => (
              <article
                key={item.title}
                className={cn(
                  'group relative overflow-hidden rounded-[1.5rem] border border-border-subtle bg-card p-7 shadow-[var(--shadow-ui)] transition duration-300 hover:-translate-y-0.5',
                  index === 0 && 'md:col-span-7 md:row-span-2 md:p-10',
                  index === 1 && 'md:col-span-5',
                  index === 2 && 'md:col-span-5',
                  index >= 3 && 'md:col-span-4'
                )}
              >
                <div
                  aria-hidden="true"
                  className={cn(
                    'pointer-events-none absolute -right-8 -top-8 h-36 w-36 rounded-full bg-brand/10 blur-2xl transition group-hover:bg-brand/16',
                    index === 0 && 'h-56 w-56'
                  )}
                />
                <h3
                  className={cn(
                    'relative font-semibold tracking-tight text-foreground',
                    index === 0 ? 'font-display text-[2.35rem] leading-[1.05]' : 'text-xl'
                  )}
                >
                  {item.title}
                </h3>
                <p className={cn('relative mt-4 leading-7 text-muted', index === 0 ? 'max-w-md text-base' : 'text-sm')}>
                  {item.description}
                </p>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
