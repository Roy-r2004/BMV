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
    <section className={cn('overflow-hidden px-6 py-20 text-background lg:px-10 lg:py-24', className)}>
      <div className="mx-auto w-full max-w-7xl">
        {heading ? <h2 className="mb-10 max-w-2xl font-display text-3xl tracking-[-0.03em] sm:text-4xl">{heading}</h2> : null}
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-12 bg-gradient-to-r from-foreground to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-12 bg-gradient-to-l from-foreground to-transparent" />
          <div className="ui-marquee-track flex w-max gap-4">
            {loop.map((item, index) => (
              <article
                key={`${item.author}-${index}`}
                className="w-[22rem] shrink-0 rounded-[calc(var(--radius-ui)+0.5rem)] border border-white/10 bg-white/5 p-6"
              >
                <p className="text-base leading-7 text-background/80">“{item.quote}”</p>
                <div className="mt-8">
                  <p className="font-semibold">{item.author}</p>
                  {item.role ? <p className="mt-1 text-sm text-background/50">{item.role}</p> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
