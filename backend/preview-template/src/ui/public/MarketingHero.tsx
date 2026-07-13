import * as React from 'react';

import { Button } from '../core/Button';
import { cn } from '../lib/cn';

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
  const copy = (
    <div className={cn(variant === 'cinematic' ? 'relative mx-auto w-full max-w-7xl px-6 pb-16 pt-10 lg:px-10 lg:pb-20' : 'relative max-w-xl')}>
      <p className="ui-fade-up font-display text-[clamp(2.75rem,7vw,5.5rem)] leading-[0.92] tracking-[-0.03em] text-white">
        {brandName}
      </p>
      <h1 className="ui-fade-up mt-6 max-w-3xl text-[clamp(1.65rem,3.2vw,2.35rem)] font-medium leading-snug tracking-[-0.02em] text-white/92">
        {headline}
      </h1>
      <p className="ui-fade-up-delay mt-5 max-w-lg text-base leading-7 text-white/72 sm:text-lg sm:leading-8">{subcopy}</p>
      <div className="ui-fade-up-delay-2 mt-9 flex flex-wrap gap-3">
        <Button href={primaryCta.href} size="lg">
          {primaryCta.label}
        </Button>
        {secondaryCta ? (
          <Button href={secondaryCta.href} size="lg" variant="outline" className="border-white/40 bg-white/5 text-white hover:bg-white/12">
            {secondaryCta.label}
          </Button>
        ) : null}
      </div>
    </div>
  );

  if (variant === 'cinematic') {
    return (
      <section className={cn('relative isolate flex min-h-[86vh] items-end overflow-hidden', className)}>
        <img src={imageSrc} alt={imageAlt} className="ui-kenburns absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0c1013] via-[#0c1013]/55 to-[#0c1013]/15" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,var(--glow-atmosphere),transparent_42%)]" />
        {copy}
      </section>
    );
  }

  if (variant === 'split' || variant === 'product') {
    return (
      <section className={cn('relative isolate grid min-h-[80vh] items-center gap-10 bg-foreground px-6 py-16 text-background lg:grid-cols-2 lg:px-10', className)}>
        {copy}
        <div className="relative overflow-hidden rounded-[1.75rem] shadow-[var(--shadow-ui)]">
          <img src={imageSrc} alt={imageAlt} className="aspect-[4/5] h-full w-full object-cover" />
        </div>
      </section>
    );
  }

  return (
    <section className={cn('relative isolate bg-foreground px-6 py-24 text-background lg:px-10 lg:py-28', className)}>
      <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
        {copy}
        <img src={imageSrc} alt={imageAlt} className="aspect-[5/4] w-full rounded-[1.75rem] object-cover shadow-[var(--shadow-ui)]" />
      </div>
    </section>
  );
}
