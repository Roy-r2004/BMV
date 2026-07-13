import * as React from 'react';

import { cn } from '../lib/cn';

export interface ProductShowcaseItem {
  title: string;
  description: string;
  imageSrc: string;
  imageAlt?: string;
}

export interface ProductShowcaseProps {
  heading: string;
  items: ProductShowcaseItem[];
  description?: string;
  className?: string;
}

export function ProductShowcase({ className, description, heading, items }: ProductShowcaseProps) {
  const [featured, ...rest] = items;
  return (
    <section className={cn('px-6 py-20 text-background lg:px-10 lg:py-24', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <h2 className="max-w-2xl font-display text-3xl tracking-[-0.03em] sm:text-4xl">{heading}</h2>
        {description ? <p className="mt-4 max-w-2xl text-base leading-7 text-background/65">{description}</p> : null}
        {featured ? (
          <article className="mt-12 grid gap-8 lg:grid-cols-[1.25fr_0.75fr] lg:items-center">
            <img
              src={featured.imageSrc}
              alt={featured.imageAlt ?? ''}
              className="aspect-[16/10] w-full rounded-[calc(var(--radius-ui)+0.75rem)] object-cover"
            />
            <div>
              <h3 className="font-display text-3xl tracking-tight">{featured.title}</h3>
              <p className="mt-4 text-base leading-7 text-background/70">{featured.description}</p>
            </div>
          </article>
        ) : null}
        {rest.length > 0 ? (
          <div className="mt-10 grid gap-6 md:grid-cols-2">
            {rest.map((item) => (
              <article key={item.title} className="grid gap-4 sm:grid-cols-[8rem_1fr] sm:items-center">
                <img
                  src={item.imageSrc}
                  alt={item.imageAlt ?? ''}
                  className="aspect-square w-full rounded-[var(--radius-ui)] object-cover sm:h-32 sm:w-32"
                />
                <div>
                  <h3 className="text-lg font-semibold">{item.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-background/65">{item.description}</p>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
