import * as React from 'react';

import { Button } from '../core/Button';
import { MotionHeroItem } from '../motion';
import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface MarketingCta {
  label: string;
  href: string;
}

export type MarketingHeroVariant = 'cinematic' | 'split' | 'editorial' | 'product';

export interface MarketingHeroProps {
  brandName: string;
  headline: string;
  subcopy: string;
  primaryCta: MarketingCta;
  imageSrc: string;
  secondaryCta?: MarketingCta;
  imageAlt?: string;
  variant?: MarketingHeroVariant;
  className?: string;
}

export function MarketingHero({
  brandName,
  className,
  headline,
  imageAlt = '',
  imageSrc,
  primaryCta,
  secondaryCta,
  subcopy,
  variant = 'cinematic',
}: MarketingHeroProps) {
  const safe = useMotionSafe();

  /** Daylight atelier thesis: type panel + edge-bleed photography. Not dark-spa overlay. */
  if (variant === 'cinematic') {
    return (
      <section
        className={cn(
          'relative isolate grid min-h-[100svh] overflow-hidden bg-[#ecefec] md:grid-cols-[minmax(18rem,0.95fr)_1.15fr]',
          className
        )}
      >
        <div className="relative order-2 z-10 flex flex-col justify-center px-6 py-12 sm:px-8 md:order-1 md:px-10 md:py-20 lg:px-12">
          <MotionHeroItem index={0}>
            <p className="font-display text-[clamp(3.75rem,10vw,7.25rem)] italic leading-[0.8] tracking-[-0.04em] text-foreground">
              {brandName}
            </p>
          </MotionHeroItem>
          <MotionHeroItem index={1}>
            <h1 className="mt-7 max-w-md text-[clamp(1.3rem,2.1vw,1.65rem)] font-medium leading-snug tracking-[-0.02em] text-foreground">
              {headline}
            </h1>
          </MotionHeroItem>
          <MotionHeroItem index={2}>
            <p className="mt-5 max-w-sm text-[0.95rem] leading-7 text-muted">{subcopy}</p>
          </MotionHeroItem>
          <MotionHeroItem index={3}>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button href={primaryCta.href} size="lg">
                {primaryCta.label}
              </Button>
              {secondaryCta ? (
                <Button href={secondaryCta.href} size="lg" variant="outline">
                  {secondaryCta.label}
                </Button>
              ) : null}
            </div>
          </MotionHeroItem>
          <MotionHeroItem index={4}>
            <p className="mt-10 text-[11px] font-semibold tracking-[0.2em] text-muted uppercase">Studio daylight · clinical calm</p>
          </MotionHeroItem>
        </div>

        <div className="relative order-1 min-h-[42vh] md:order-2 md:min-h-full">
          <img
            src={imageSrc}
            alt={imageAlt}
            className={cn('absolute inset-0 h-full w-full object-cover', safe && 'ui-kenburns')}
          />
          <div
            aria-hidden="true"
            className="ui-treatment-light pointer-events-none absolute inset-y-0 left-0 z-10 hidden w-px md:block"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#ecefec]/50 md:bg-gradient-to-r md:from-[#ecefec]/25 md:to-transparent" />
        </div>
      </section>
    );
  }

  const copy = (
    <div className="relative max-w-xl">
      <MotionHeroItem index={0}>
        <p className="font-display text-[clamp(3.25rem,8vw,6rem)] italic leading-[0.88] tracking-[-0.04em] text-white">
          {brandName}
        </p>
      </MotionHeroItem>
      <MotionHeroItem index={1}>
        <h1 className="mt-5 max-w-2xl text-[clamp(1.35rem,2.6vw,1.85rem)] font-medium leading-snug tracking-[-0.015em] text-white/90">
          {headline}
        </h1>
      </MotionHeroItem>
      <MotionHeroItem index={2}>
        <p className="mt-4 max-w-md text-[0.95rem] leading-7 text-white/68">{subcopy}</p>
      </MotionHeroItem>
      <MotionHeroItem index={3}>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button href={primaryCta.href} size="lg">
            {primaryCta.label}
          </Button>
          {secondaryCta ? (
            <Button
              href={secondaryCta.href}
              size="lg"
              variant="outline"
              className="border-white/35 bg-transparent text-white hover:bg-white/10"
            >
              {secondaryCta.label}
            </Button>
          ) : null}
        </div>
      </MotionHeroItem>
    </div>
  );

  if (variant === 'split' || variant === 'product') {
    return (
      <section
        className={cn(
          'relative isolate grid min-h-[80vh] items-center gap-10 bg-foreground px-6 py-16 text-background lg:grid-cols-2 lg:px-10',
          className
        )}
      >
        {copy}
        <MotionHeroItem index={1} className="relative overflow-hidden rounded-[var(--radius-ui)] shadow-[var(--shadow-ui)]">
          <img src={imageSrc} alt={imageAlt} className="aspect-[4/5] h-full w-full object-cover" />
        </MotionHeroItem>
      </section>
    );
  }

  return (
    <section className={cn('relative isolate bg-foreground px-6 py-24 text-background lg:px-10 lg:py-28', className)}>
      <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
        {copy}
        <MotionHeroItem index={1}>
          <img
            src={imageSrc}
            alt={imageAlt}
            className="aspect-[5/4] w-full rounded-[var(--radius-ui)] object-cover shadow-[var(--shadow-ui)]"
          />
        </MotionHeroItem>
      </div>
    </section>
  );
}
