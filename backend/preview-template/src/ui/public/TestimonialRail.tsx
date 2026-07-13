import * as React from 'react';

import { cn } from '../lib/cn';

export interface TestimonialRailItem {
  quote: string;
  author: string;
  role?: string;
}

export interface TestimonialRailProps {
  items: TestimonialRailItem[];
  heading?: string;
  className?: string;
}

export function TestimonialRail({ className, heading, items }: TestimonialRailProps) {
  const loop = [...items, ...items];
  return (
    <section className={cn('overflow-hidden bg-card px-6 py-24 lg:px-10 lg:py-28', className)}>
      <div className="mx-auto w-full max-w-7xl">
        {heading ? (
          <h2 className="mb-12 max-w-2xl font-display text-[clamp(2.25rem,4vw,3.4rem)] leading-[1.05] tracking-[-0.03em] text-foreground">
            {heading}
          </h2>
        ) : null}
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-card to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-card to-transparent" />
          <div className="ui-marquee-track flex w-max gap-5">
            {loop.map((item, index) => (
              <article
                key={`${item.author}-${index}`}
                className="w-[24rem] shrink-0 rounded-[1.5rem] border border-border-subtle bg-background p-7 shadow-[var(--shadow-ui)]"
              >
                <p className="font-display text-2xl leading-snug text-foreground">“{item.quote}”</p>
                <div className="mt-8 border-t border-border-subtle pt-5">
                  <p className="font-semibold text-foreground">{item.author}</p>
                  {item.role ? <p className="mt-1 text-sm text-muted">{item.role}</p> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
