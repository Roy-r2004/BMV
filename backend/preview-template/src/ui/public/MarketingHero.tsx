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

const variantShell: Record<MarketingHeroVariant, string> = {
  cinematic: 'relative isolate flex min-h-[78vh] items-center overflow-hidden',
  split: 'relative isolate grid min-h-[80vh] items-center gap-10 px-6 py-20 lg:grid-cols-2 lg:px-10',
  editorial: 'relative isolate px-6 py-24 lg:px-10 lg:py-32',
  product: 'relative isolate grid min-h-[78vh] items-end gap-8 px-6 pb-16 pt-24 lg:grid-cols-[1.1fr_0.9fr] lg:px-10',
};

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
    <div className={cn(variant === 'cinematic' ? 'relative mx-auto w-full max-w-7xl px-6 py-24 lg:px-10' : 'relative max-w-2xl')}>
      <p className="ui-fade-up font-display text-sm tracking-[0.22em] text-background/70 uppercase">{brandName}</p>
      <h1 className="ui-fade-up mt-4 font-display text-4xl leading-[1.05] tracking-[-0.03em] text-balance text-background sm:text-5xl lg:text-6xl">
        {headline}
      </h1>
      <p className="ui-fade-up-delay mt-5 max-w-xl text-lg leading-8 text-background/75">{subcopy}</p>
      <div className="ui-fade-up-delay mt-9 flex flex-wrap gap-3">
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
  );

  if (variant === 'cinematic') {
    return (
      <section className={cn(variantShell.cinematic, className)}>
        <img src={imageSrc} alt={imageAlt} className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-foreground via-foreground/55 to-foreground/25" />
        {copy}
      </section>
    );
  }

  if (variant === 'split' || variant === 'product') {
    return (
      <section className={cn(variantShell[variant], 'bg-foreground text-background', className)}>
        {copy}
        <div className="relative overflow-hidden rounded-[calc(var(--radius-ui)+0.75rem)] border border-white/10">
          <img src={imageSrc} alt={imageAlt} className="aspect-[4/5] h-full w-full object-cover" />
        </div>
      </section>
    );
  }

  return (
    <section className={cn(variantShell.editorial, 'bg-foreground text-background', className)}>
      <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
        {copy}
        <img src={imageSrc} alt={imageAlt} className="aspect-[5/4] w-full rounded-[calc(var(--radius-ui)+0.75rem)] object-cover" />
      </div>
    </section>
  );
}
