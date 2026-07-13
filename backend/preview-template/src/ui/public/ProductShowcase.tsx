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
    <section className={cn('bg-foreground px-6 py-24 text-background lg:px-10 lg:py-28', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <div className="max-w-2xl">
          <h2 className="font-display text-[clamp(2.25rem,4vw,3.4rem)] leading-[1.05] tracking-[-0.03em]">{heading}</h2>
          {description ? <p className="mt-5 text-base leading-7 text-background/65 sm:text-lg">{description}</p> : null}
        </div>
        {featured ? (
          <article className="mt-14 grid gap-10 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
            <img
              src={featured.imageSrc}
              alt={featured.imageAlt ?? ''}
              className="aspect-[16/10] w-full rounded-[1.75rem] object-cover shadow-[var(--shadow-ui)]"
            />
            <div className="pb-2">
              <p className="text-xs font-semibold tracking-[0.22em] text-brand uppercase">Signature</p>
              <h3 className="mt-3 font-display text-4xl tracking-tight">{featured.title}</h3>
              <p className="mt-4 text-base leading-8 text-background/70">{featured.description}</p>
            </div>
          </article>
        ) : null}
        {rest.length > 0 ? (
          <div className="mt-12 grid gap-8 border-t border-white/10 pt-10 md:grid-cols-2">
            {rest.map((item) => (
              <article key={item.title} className="grid gap-5 sm:grid-cols-[9rem_1fr] sm:items-center">
                <img
                  src={item.imageSrc}
                  alt={item.imageAlt ?? ''}
                  className="aspect-square w-full rounded-[1.15rem] object-cover sm:h-36 sm:w-36"
                />
                <div>
                  <h3 className="text-xl font-semibold tracking-tight">{item.title}</h3>
                  <p className="mt-2 text-sm leading-7 text-background/65">{item.description}</p>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
