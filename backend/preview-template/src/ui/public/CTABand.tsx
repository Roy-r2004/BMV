import * as React from 'react';

import { Button } from '../core/Button';
import { MotionReveal } from '../motion';
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
    <section className={cn('bg-foreground px-6 py-24 text-background lg:px-12 lg:py-28', className)}>
      <MotionReveal>
        <div className="mx-auto flex w-full max-w-[92rem] flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] font-semibold tracking-[0.22em] text-brand uppercase">Book</p>
            <h2 className="mt-4 font-display text-[clamp(2.75rem,5.5vw,5rem)] italic leading-[0.95] tracking-[-0.04em]">
              {heading}
            </h2>
            {description ? <p className="mt-5 max-w-lg text-base leading-8 text-background/60">{description}</p> : null}
          </div>
          <div className="flex flex-wrap gap-3">
            <Button href={primaryCta.href} size="lg">
              {primaryCta.label}
            </Button>
            {secondaryCta ? (
              <Button
                href={secondaryCta.href}
                size="lg"
                variant="outline"
                className="border-white/30 text-background hover:bg-white/10"
              >
                {secondaryCta.label}
              </Button>
            ) : null}
          </div>
        </div>
      </MotionReveal>
    </section>
  );
}
