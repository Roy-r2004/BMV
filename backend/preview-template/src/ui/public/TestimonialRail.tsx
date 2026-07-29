import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
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

/** Editorial quote stack — not equal testimonial cards. */
export function TestimonialRail({
  className,
  heading,
  items: itemsProp = [],
}: TestimonialRailProps) {
  const items = Array.isArray(itemsProp) ? itemsProp : [];
  const [lead, ...rest] = items;
  // A heading over nothing reads as a broken page; render nothing instead.
  if (!items.length) return null;
  return (
    <section className={cn('relative isolate overflow-hidden bg-background px-6 py-28 lg:px-12 lg:py-36', className)}>
      <div className="ui-mesh opacity-50" aria-hidden="true" />
      <div className="relative mx-auto w-full max-w-[92rem]">
        {heading ? (
          <MotionReveal>
            <h2 className="mb-16 max-w-3xl font-display text-[clamp(3rem,6vw,5rem)] italic leading-[0.92] tracking-[-0.04em] text-foreground">
              {heading}
            </h2>
          </MotionReveal>
        ) : null}

        {lead ? (
          <MotionReveal>
            <blockquote className="relative max-w-4xl border-l-2 border-brand pl-8 md:pl-12">
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -left-4 top-0 font-display text-[clamp(4rem,10vw,7rem)] leading-none text-brand/15"
              >
                “
              </div>
              <p className="font-display text-[clamp(1.85rem,3.5vw,3.25rem)] italic leading-[1.15] tracking-[-0.02em] text-foreground">
                “{lead.quote}”
              </p>
              <footer className="mt-8 text-sm">
                <cite className="not-italic font-semibold text-foreground">{lead.author}</cite>
                {lead.role ? <span className="text-muted"> · {lead.role}</span> : null}
              </footer>
            </blockquote>
          </MotionReveal>
        ) : null}

        {rest.length > 0 ? (
          <MotionStagger className="mt-16 grid gap-10 border-t border-foreground/10 pt-12 md:grid-cols-2">
            {rest.map((item) => (
              <MotionStaggerItem key={item.author}>
                <blockquote>
                  <p className="text-lg leading-8 text-foreground/85">“{item.quote}”</p>
                  <footer className="mt-5 text-sm">
                    <cite className="not-italic font-semibold text-foreground">{item.author}</cite>
                    {item.role ? <span className="text-muted"> · {item.role}</span> : null}
                  </footer>
                </blockquote>
              </MotionStaggerItem>
            ))}
          </MotionStagger>
        ) : null}
      </div>
    </section>
  );
}
