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
    <section className={cn('px-6 py-20 text-background lg:px-10 lg:py-24', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <h2 className="max-w-2xl font-display text-3xl tracking-[-0.03em] sm:text-4xl">{heading}</h2>
        {description ? <p className="mt-4 max-w-2xl text-base leading-7 text-background/65">{description}</p> : null}

        {variant === 'grid' ? (
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <article key={item.title} className="rounded-[calc(var(--radius-ui)+0.5rem)] border border-white/10 bg-white/5 p-6">
                <h3 className="text-xl font-semibold">{item.title}</h3>
                <p className="mt-3 text-sm leading-7 text-background/65">{item.description}</p>
              </article>
            ))}
          </div>
        ) : null}

        {variant === 'alternating' ? (
          <div className="mt-12 space-y-10">
            {items.map((item, index) => (
              <article
                key={item.title}
                className={cn(
                  'grid gap-4 border-t border-white/10 pt-8 md:grid-cols-2 md:gap-10',
                  index % 2 === 1 && 'md:[&>*:first-child]:order-2'
                )}
              >
                <h3 className="font-display text-2xl tracking-tight">{item.title}</h3>
                <p className="text-base leading-7 text-background/70">{item.description}</p>
              </article>
            ))}
          </div>
        ) : null}

        {variant === 'bento' ? (
          <div className="mt-12 grid gap-4 md:auto-rows-[minmax(11rem,auto)] md:grid-cols-3">
            {items.map((item, index) => (
              <article
                key={item.title}
                className={cn(
                  'rounded-[calc(var(--radius-ui)+0.75rem)] border border-white/10 bg-white/5 p-6 backdrop-blur-sm',
                  index === 0 && 'md:col-span-2 md:row-span-2 md:p-8'
                )}
              >
                <h3 className={cn('font-semibold tracking-tight', index === 0 ? 'font-display text-3xl' : 'text-xl')}>
                  {item.title}
                </h3>
                <p className={cn('mt-3 leading-7 text-background/65', index === 0 ? 'text-base' : 'text-sm')}>
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
