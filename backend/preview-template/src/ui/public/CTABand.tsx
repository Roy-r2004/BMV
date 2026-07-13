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
    <section className={cn('px-6 py-20 lg:px-10', className)}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 rounded-[calc(var(--radius-ui)+0.75rem)] border border-white/10 bg-white/5 px-8 py-12 text-background md:flex-row md:items-end md:justify-between">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl tracking-tight sm:text-4xl">{heading}</h2>
          {description ? <p className="mt-4 text-base leading-7 text-background/65">{description}</p> : null}
        </div>
        <div className="flex flex-wrap gap-3">
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
