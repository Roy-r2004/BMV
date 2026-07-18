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

/** Trust strip — credentials / protocols / studios with brand atmosphere. */
export function CredentialStrip({
  className,
  heading = 'Clinical trust',
  items: itemsProp = [],
}: CredentialStripProps) {
  const items = Array.isArray(itemsProp) ? itemsProp : [];
  return (
    <section
      className={cn(
        'relative overflow-hidden border-y border-foreground/10 bg-[color-mix(in_srgb,var(--color-brand)_4%,var(--color-card))] px-6 py-14 lg:px-12',
        className
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{
          background:
            'radial-gradient(60% 80% at 100% 50%, color-mix(in srgb, var(--color-brand) 12%, transparent), transparent 60%)',
        }}
      />
      <div className="relative mx-auto w-full max-w-[92rem]">
        <MotionReveal>
          <p className="text-[11px] font-semibold tracking-[0.2em] text-brand uppercase">{heading}</p>
        </MotionReveal>
        <MotionStagger className="mt-8 grid gap-8 md:grid-cols-3">
          {items.map((item) => (
            <MotionStaggerItem key={item.title}>
              <article className="rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle/80 bg-card/80 p-5 shadow-[var(--shadow-ui)] backdrop-blur-sm">
                <div className="mb-3 h-1 w-10 rounded-full bg-brand/70" />
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
