import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
import { cn } from '../lib/cn';

export interface ResultRailItem {
  label: string;
  beforeSrc: string;
  afterSrc: string;
  beforeAlt?: string;
  afterAlt?: string;
  note?: string;
}

export interface ResultRailProps {
  heading: string;
  items: ResultRailItem[];
  description?: string;
  className?: string;
}

/** Outcome proof — fixed before/after pairs, no open styling API. */
export function ResultRail({ className, description, heading, items }: ResultRailProps) {
  return (
    <section className={cn('px-6 py-28 lg:px-12 lg:py-32', className)}>
      <div className="mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <h2 className="font-display text-[clamp(2.75rem,5.5vw,5rem)] italic leading-[0.92] tracking-[-0.04em] text-foreground">
            {heading}
          </h2>
          {description ? <p className="max-w-md text-base leading-8 text-muted lg:justify-self-end">{description}</p> : null}
        </MotionReveal>

        <MotionStagger className="mt-14 grid gap-8 lg:grid-cols-3">
          {items.map((item) => (
            <MotionStaggerItem key={item.label}>
              <article className="overflow-hidden border border-border-subtle bg-card">
                <div className="grid grid-cols-2 gap-px bg-border-subtle">
                  <figure className="bg-card">
                    <img src={item.beforeSrc} alt={item.beforeAlt ?? `${item.label} before`} className="aspect-[4/5] w-full object-cover" />
                    <figcaption className="px-3 py-2 text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">
                      Before
                    </figcaption>
                  </figure>
                  <figure className="bg-card">
                    <img src={item.afterSrc} alt={item.afterAlt ?? `${item.label} after`} className="aspect-[4/5] w-full object-cover" />
                    <figcaption className="px-3 py-2 text-[10px] font-semibold tracking-[0.16em] text-brand uppercase">
                      After
                    </figcaption>
                  </figure>
                </div>
                <div className="border-t border-border-subtle px-4 py-4">
                  <h3 className="font-display text-xl italic text-foreground">{item.label}</h3>
                  {item.note ? <p className="mt-1 text-sm leading-6 text-muted">{item.note}</p> : null}
                </div>
              </article>
            </MotionStaggerItem>
          ))}
        </MotionStagger>
      </div>
    </section>
  );
}
