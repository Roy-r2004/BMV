import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
import { cn } from '../lib/cn';

export interface CredentialStripItem {
  title: string;
  detail: string;
}

export interface CredentialStripProps {
  heading?: string;
  items: CredentialStripItem[];
  className?: string;
}

/** Clinical trust strip — credentials / protocols / studios. */
export function CredentialStrip({ className, heading = 'Clinical trust', items }: CredentialStripProps) {
  return (
    <section className={cn('border-y border-foreground/10 bg-card px-6 py-12 lg:px-12', className)}>
      <div className="mx-auto w-full max-w-[92rem]">
        <MotionReveal>
          <p className="text-[11px] font-semibold tracking-[0.2em] text-muted uppercase">{heading}</p>
        </MotionReveal>
        <MotionStagger className="mt-8 grid gap-8 md:grid-cols-3">
          {items.map((item) => (
            <MotionStaggerItem key={item.title}>
              <article>
                <h3 className="font-display text-2xl italic tracking-tight text-foreground">{item.title}</h3>
                <p className="mt-2 text-sm leading-7 text-muted">{item.detail}</p>
              </article>
            </MotionStaggerItem>
          ))}
        </MotionStagger>
      </div>
    </section>
  );
}
