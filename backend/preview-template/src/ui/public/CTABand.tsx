import * as React from 'react';

import { Button } from '../core/Button';
import { cn } from '../lib/cn';

export interface CTALink {
  label: string;
  href: string;
}

export interface CTABandProps {
  heading: string;
  primaryCta: CTALink;
  description?: string;
  secondaryCta?: CTALink;
  className?: string;
}

export function CTABand({ className, description, heading, primaryCta, secondaryCta }: CTABandProps) {
  return (
    <section className={cn('px-6 py-24 lg:px-10 lg:py-24', className)}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 overflow-hidden rounded-[2rem] bg-foreground px-8 py-14 text-background shadow-[var(--shadow-ui)] md:flex-row md:items-end md:justify-between md:px-12">
        <div className="relative max-w-2xl">
          <div aria-hidden="true" className="pointer-events-none absolute -left-20 -top-24 h-56 w-56 rounded-full bg-brand/25 blur-3xl" />
          <h2 className="relative font-display text-[clamp(2.2rem,4vw,3.3rem)] leading-[1.05] tracking-[-0.03em]">{heading}</h2>
          {description ? <p className="relative mt-4 text-base leading-7 text-background/65">{description}</p> : null}
        </div>
        <div className="relative flex flex-wrap gap-3">
          <Button href={primaryCta.href} size="lg">
            {primaryCta.label}
          </Button>
          {secondaryCta ? (
            <Button href={secondaryCta.href} size="lg" variant="outline" className="border-white/35 text-background hover:bg-white/10">
              {secondaryCta.label}
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
