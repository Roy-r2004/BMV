import * as React from 'react';

import { Button } from '../core/Button';
import { AnimeHeroItem } from '../motion';
import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';
import { KitImage } from '../lib/KitImage';
import {
  currentRecipeId,
  recipeDisplayClass,
  recipeHeroVariant,
  type HeroVariant,
} from '../../lib/recipe';

export interface MarketingCta {
  label: string;
  href: string;
}

/** @deprecated legacy page props still accepted; recipe composition wins when omitted */
export type MarketingHeroVariant = HeroVariant | 'split';

export interface MarketingHeroProps {
  brandName: string;
  headline: string;
  subcopy: string;
  /** Optional — missing CTA must not crash About/utility scaffolds. */
  primaryCta?: MarketingCta;
  imageSrc: string;
  secondaryCta?: MarketingCta;
  imageAlt?: string;
  /** Small uppercase kicker above the wordmark (business-specific, e.g. "Custom builds · Trade-ins"). */
  eyebrow?: string;
  variant?: MarketingHeroVariant;
  className?: string;
  /**
   * Overlay content — a detail page's "Back to the collection" chip, a badge,
   * a price tag. Rendered as a sibling of the hero section inside a positioned
   * wrapper, so the `absolute top-6 left-6` codegen writes for it lands over the
   * artwork instead of over whatever section happens to be above.
   */
  children?: React.ReactNode;
}

const DEFAULT_PRIMARY_CTA: MarketingCta = { label: 'Explore', href: '/gallery' };

export function MarketingHero({ children, ...props }: MarketingHeroProps) {
  const hero = <MarketingHeroBody {...props} />;
  if (!children) return hero;
  return (
    <div className="relative">
      {hero}
      {children}
    </div>
  );
}

function MarketingHeroBody({
  brandName,
  className,
  eyebrow,
  headline,
  imageAlt = '',
  imageSrc,
  primaryCta,
  secondaryCta,
  subcopy,
  variant: _variant,
}: Omit<MarketingHeroProps, 'children'>) {
  const safe = useMotionSafe();
  const recipeId = currentRecipeId();
  // Recipe owns hero composition — codegen cannot collapse every business to one layout.
  const resolved = recipeHeroVariant(recipeId);
  const display = recipeDisplayClass(recipeId);
  const cta = primaryCta?.href && primaryCta?.label ? primaryCta : DEFAULT_PRIMARY_CTA;

  const ctas = (
    <div className="mt-8 flex flex-wrap gap-3">
      <Button href={cta.href} size="lg">
        {cta.label}
      </Button>
      {secondaryCta ? (
        <Button href={secondaryCta.href} size="lg" variant="outline">
          {secondaryCta.label}
        </Button>
      ) : null}
    </div>
  );

  const onDarkCtas = (
    <div className="mt-8 flex flex-wrap gap-3">
      <Button
        href={cta.href}
        size="lg"
        className="bg-white text-foreground shadow-[0_20px_50px_-20px_rgba(0,0,0,0.65)] hover:bg-white/92 hover:text-foreground"
      >
        {cta.label}
      </Button>
      {secondaryCta ? (
        <Button
          href={secondaryCta.href}
          size="lg"
          variant="outline"
          className="border-white/45 bg-white/5 text-white backdrop-blur-sm hover:bg-white/15 hover:text-white"
        >
          {secondaryCta.label}
        </Button>
      ) : null}
    </div>
  );

  /* ─── warm-service: full-bleed appetite cinema (not soft inset cards) ─── */
  if (resolved === 'service') {
    return (
      <section
        data-hero="service"
        className={cn('relative isolate min-h-[100svh] overflow-hidden bg-[#120e0c] text-white', className)}
      >
        <KitImage
          src={imageSrc}
          alt={imageAlt}
          className={cn(
            'absolute inset-0 h-full w-full scale-105 object-cover object-center',
            safe && 'ui-kenburns-cinematic'
          )}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#120e0c] via-[#120e0c]/55 to-[#120e0c]/15" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#120e0c]/85 via-[#120e0c]/35 to-transparent" />
        <div className="ui-vignette opacity-80" />
        <div className="ui-film-grain opacity-[0.32]" />
        {safe ? <div className="ui-hero-sheen" /> : null}
        {safe ? <div className="ui-light-sweep" aria-hidden="true" /> : null}
        <div className="relative z-10 mx-auto flex min-h-[100svh] max-w-[92rem] flex-col justify-center px-6 pb-20 pt-28 sm:pb-24 lg:px-12 lg:pt-32">
          <AnimeHeroItem index={0}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-white/55">
              {eyebrow || brandName}
            </p>
          </AnimeHeroItem>
          <AnimeHeroItem index={1}>
            <p
              className={cn(
                display,
                'mt-6 max-w-[11ch] text-[clamp(3.5rem,11vw,8rem)] leading-[0.82] tracking-[-0.045em] text-white'
              )}
            >
              {brandName}
            </p>
          </AnimeHeroItem>
          <AnimeHeroItem index={2}>
            <h1 className="mt-7 max-w-[22ch] text-[clamp(1.25rem,2.4vw,1.85rem)] font-medium leading-snug tracking-[-0.02em] text-white/92">
              {headline}
            </h1>
          </AnimeHeroItem>
          <AnimeHeroItem index={3}>
            <p className="mt-5 max-w-md text-[1.05rem] leading-8 text-white/70">{subcopy}</p>
          </AnimeHeroItem>
          <AnimeHeroItem index={4}>
            <div className="mt-10 flex flex-wrap gap-3">
              <Button
                href={cta.href}
                size="lg"
                className="bg-white text-foreground shadow-[0_24px_60px_-24px_rgba(0,0,0,0.7)] hover:bg-white/92 hover:text-foreground"
              >
                {cta.label}
              </Button>
              {secondaryCta ? (
                <Button
                  href={secondaryCta.href}
                  size="lg"
                  variant="outline"
                  className="border-white/45 bg-white/5 text-white backdrop-blur-sm hover:bg-white/15"
                >
                  {secondaryCta.label}
                </Button>
              ) : null}
            </div>
          </AnimeHeroItem>
          <AnimeHeroItem index={5}>
            <p className={cn('mt-14 text-[10px] font-semibold uppercase tracking-[0.32em] text-white/40', safe && 'ui-scroll-cue')}>
              Scroll to taste
            </p>
          </AnimeHeroItem>
        </div>
      </section>
    );
  }

  /* ─── dense-ops: compact utility band ─── */
  if (resolved === 'compact') {
    return (
      <section
        data-hero="compact"
        className={cn(
          'relative isolate overflow-hidden border-b border-border-subtle bg-background px-6 py-12 lg:px-10 lg:py-14',
          className
        )}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(80%_60%_at_100%_0%,color-mix(in_srgb,var(--color-brand)_14%,transparent),transparent_55%)]"
        />
        <div className="relative mx-auto grid max-w-[92rem] gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <AnimeHeroItem index={0}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">
                {eyebrow || brandName}
              </p>
            </AnimeHeroItem>
            <AnimeHeroItem index={1}>
              <h1 className={cn(display, 'mt-2 text-[clamp(1.85rem,3.2vw,2.65rem)] leading-tight text-foreground')}>
                {headline}
              </h1>
            </AnimeHeroItem>
            <AnimeHeroItem index={2}>
              <p className="mt-3 max-w-xl text-sm leading-6 text-muted">{subcopy}</p>
            </AnimeHeroItem>
            <AnimeHeroItem index={3}>
              <div className="mt-5 flex flex-wrap gap-2">
                <Button href={cta.href} size="default">
                  {cta.label}
                </Button>
                {secondaryCta ? (
                  <Button href={secondaryCta.href} size="default" variant="outline">
                    {secondaryCta.label}
                  </Button>
                ) : null}
              </div>
            </AnimeHeroItem>
          </div>
          <AnimeHeroItem index={1}>
            <div className="overflow-hidden rounded-[var(--radius-ui)] border border-border-subtle shadow-[var(--shadow-ui)] ring-1 ring-brand/10">
              <KitImage
                src={imageSrc}
                alt={imageAlt}
                className={cn('aspect-[16/11] w-full object-cover', safe && 'ui-kenburns')}
              />
            </div>
          </AnimeHeroItem>
        </div>
      </section>
    );
  }

  /* ─── product / bold-retail: full-bleed immersive — brand owns the first viewport ─── */
  if (resolved === 'product') {
    const brandText = String(brandName ?? '');
    const headlineText = String(headline ?? '');
    const headlineDistinct =
      headlineText.trim().toLowerCase() !== brandText.trim().toLowerCase() &&
      headlineText.trim().length > 0;
    return (
      <section
        data-hero="product"
        className={cn('relative isolate min-h-[100svh] overflow-hidden bg-[#0a0c0e] text-white', className)}
      >
        <KitImage
          src={imageSrc}
          alt={imageAlt}
          className={cn('absolute inset-0 h-full w-full object-cover', safe && 'ui-kenburns')}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/55 to-black/20" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/30 to-transparent" />
        <div className="ui-vignette opacity-85" />
        <div className="ui-film-grain opacity-[0.28]" />
        {safe ? <div className="ui-hero-sheen" /> : null}
        {safe ? <div className="ui-light-sweep" aria-hidden="true" /> : null}
        <div className="relative z-10 mx-auto flex min-h-[100svh] max-w-[92rem] flex-col justify-end px-6 pb-16 pt-28 sm:pb-20 lg:px-12 lg:pb-24">
          <AnimeHeroItem index={0}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-white/55">
              {eyebrow || brandName}
            </p>
          </AnimeHeroItem>
          <AnimeHeroItem index={1}>
            <p
              className={cn(
                display,
                'mt-6 max-w-[13ch] text-[clamp(4rem,12vw,9rem)] leading-[0.8] tracking-[-0.045em] text-white'
              )}
            >
              {brandName}
            </p>
          </AnimeHeroItem>
          {headlineDistinct ? (
            <AnimeHeroItem index={2}>
              <h1 className="mt-7 max-w-xl text-[clamp(1.2rem,2.3vw,1.7rem)] font-medium leading-snug tracking-[-0.02em] text-white/90">
                {headline}
              </h1>
            </AnimeHeroItem>
          ) : null}
          <AnimeHeroItem index={headlineDistinct ? 3 : 2}>
            <p className="mt-4 max-w-md text-[1rem] leading-7 text-white/68">{subcopy}</p>
          </AnimeHeroItem>
          <AnimeHeroItem index={headlineDistinct ? 4 : 3}>
            <div className="mt-10 flex flex-wrap gap-3">
              <Button
                href={cta.href}
                size="lg"
                className="bg-white text-foreground shadow-[0_20px_50px_-20px_rgba(0,0,0,0.65)] hover:bg-white/92 hover:text-foreground"
              >
                {cta.label}
              </Button>
              {secondaryCta ? (
                <Button
                  href={secondaryCta.href}
                  size="lg"
                  variant="outline"
                  className="border-white/45 bg-white/5 text-white backdrop-blur-sm hover:bg-white/15"
                >
                  {secondaryCta.label}
                </Button>
              ) : null}
            </div>
          </AnimeHeroItem>
          <AnimeHeroItem index={headlineDistinct ? 5 : 4}>
            <p className="mt-14 text-[10px] font-semibold uppercase tracking-[0.3em] text-white/35">
              Scroll to explore
            </p>
          </AnimeHeroItem>
        </div>
      </section>
    );
  }

  /* ─── craft atelier: stone type panel + tall asymmetric media rail (≠ retail full-bleed) ─── */
  if (resolved === 'atelier') {
    return (
      <section
        data-hero="atelier"
        className={cn(
          'relative isolate min-h-[100svh] overflow-hidden bg-[#f3f0ea] text-[#1a1714]',
          className
        )}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              'radial-gradient(70% 50% at 12% 18%, color-mix(in srgb, var(--color-brand) 12%, transparent), transparent 58%), linear-gradient(180deg, #efebe3 0%, #f7f5f0 42%, #f3f0ea 100%)',
          }}
        />
        <div className="ui-noise opacity-[0.35]" aria-hidden="true" />
        <div className="relative z-10 mx-auto grid min-h-[100svh] max-w-[92rem] items-stretch gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="flex flex-col justify-end px-6 pb-16 pt-28 sm:px-10 lg:px-14 lg:pb-24 lg:pt-32">
            <AnimeHeroItem index={0}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-brand">
                {eyebrow || brandName}
              </p>
            </AnimeHeroItem>
            <AnimeHeroItem index={1}>
              <p
                className={cn(
                  display,
                  'mt-5 max-w-[11ch] text-[clamp(3.75rem,10vw,7.5rem)] leading-[0.84] tracking-[-0.04em] text-[#1a1714]'
                )}
              >
                {brandName}
              </p>
            </AnimeHeroItem>
            <AnimeHeroItem index={2}>
              <h1 className="mt-8 max-w-[22ch] text-[clamp(1.15rem,2vw,1.45rem)] font-medium leading-snug tracking-[-0.02em] text-[#1a1714]/90">
                {headline}
              </h1>
            </AnimeHeroItem>
            <AnimeHeroItem index={3}>
              <p className="mt-4 max-w-sm text-[0.95rem] leading-7 text-[#1a1714]/65">{subcopy}</p>
            </AnimeHeroItem>
            <AnimeHeroItem index={4}>{ctas}</AnimeHeroItem>
          </div>
          <AnimeHeroItem index={1}>
            <div className="relative min-h-[48vh] overflow-hidden lg:min-h-full lg:pl-6 lg:pr-10 lg:py-10">
              <div
                className={cn(
                  'relative h-full min-h-[48vh] overflow-hidden shadow-[var(--shadow-ui)] ring-1 ring-[#1a1714]/10 lg:min-h-[calc(100svh-5rem)] lg:rounded-sm',
                  safe && 'ui-float'
                )}
              >
                <KitImage
                  src={imageSrc}
                  alt={imageAlt}
                  className={cn(
                    'absolute inset-0 h-full w-full object-cover object-center',
                    safe && 'ui-kenburns'
                  )}
                />
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#1a1714]/25 via-transparent to-transparent" />
                <div className="ui-film-grain opacity-[0.12]" />
              </div>
            </div>
          </AnimeHeroItem>
        </div>
      </section>
    );
  }

  /* ─── editorial: type-led + edge photo ─── */
  if (resolved === 'editorial') {
    return (
      <section
        data-hero="editorial"
        className={cn('relative isolate overflow-hidden bg-foreground px-6 py-24 text-background lg:px-10 lg:py-32', className)}
      >
        <div className="ui-mesh opacity-30" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-7xl gap-14 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div>
            <AnimeHeroItem index={0}>
              <p className={cn(display, 'text-[clamp(3.5rem,9vw,7rem)] leading-[0.82] text-white')}>{brandName}</p>
            </AnimeHeroItem>
            <AnimeHeroItem index={1}>
              <h1 className="mt-8 max-w-xl text-[clamp(1.2rem,2.2vw,1.7rem)] font-medium leading-snug text-white/88">
                {headline}
              </h1>
            </AnimeHeroItem>
            <AnimeHeroItem index={2}>
              <p className="mt-5 max-w-md text-[0.95rem] leading-7 text-white/65">{subcopy}</p>
            </AnimeHeroItem>
            <AnimeHeroItem index={3}>{onDarkCtas}</AnimeHeroItem>
          </div>
          <AnimeHeroItem index={1}>
            <div className={cn('relative overflow-hidden rounded-[var(--radius-ui)]', safe && 'ui-float')}>
              <KitImage
                src={imageSrc}
                alt={imageAlt}
                className={cn('aspect-[5/4] w-full object-cover shadow-[var(--shadow-ui)]', safe && 'ui-kenburns')}
              />
              <div className="ui-film-grain opacity-[0.14]" />
            </div>
          </AnimeHeroItem>
        </div>
      </section>
    );
  }

  /* ─── cinematic (Manus-clear): brand-first type panel + full-bleed photo ─── */
  return (
    <section
      data-hero="cinematic"
      className={cn(
        'relative isolate grid min-h-[100svh] overflow-hidden bg-background md:grid-cols-[minmax(20rem,0.92fr)_1.18fr]',
        className
      )}
    >
      <div className="relative order-2 z-10 flex flex-col justify-center px-6 py-14 sm:px-8 md:order-1 md:px-12 md:py-24 lg:px-16">
        <div className="ui-mesh opacity-40" aria-hidden="true" />
        {eyebrow ? (
          <AnimeHeroItem index={0}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-brand">
              {eyebrow}
            </p>
          </AnimeHeroItem>
        ) : null}
        <AnimeHeroItem index={eyebrow ? 1 : 0}>
          <p
            className={cn(
              display,
              'max-w-[12ch] text-[clamp(3.5rem,9vw,6.75rem)] leading-[0.88] tracking-[-0.035em] text-foreground'
            )}
          >
            {brandName}
          </p>
        </AnimeHeroItem>
        <AnimeHeroItem index={eyebrow ? 2 : 1}>
          <h1 className="mt-8 max-w-[22ch] text-[clamp(1.2rem,2vw,1.55rem)] font-medium leading-snug tracking-[-0.02em] text-foreground">
            {headline}
          </h1>
        </AnimeHeroItem>
        <AnimeHeroItem index={eyebrow ? 3 : 2}>
          <p className="mt-4 max-w-sm text-[0.95rem] leading-7 text-muted">{subcopy}</p>
        </AnimeHeroItem>
        <AnimeHeroItem index={eyebrow ? 4 : 3}>{ctas}</AnimeHeroItem>
      </div>
      <div className="relative order-1 min-h-[52vh] overflow-hidden md:order-2 md:min-h-full">
        <KitImage
          src={imageSrc}
          alt={imageAlt}
          className={cn('absolute inset-0 h-full w-full object-cover', safe && 'ui-kenburns')}
        />
        <div className="ui-film-grain opacity-[0.14]" />
        <div className="ui-vignette opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/40 md:bg-gradient-to-r md:from-background/30 md:via-transparent md:to-transparent" />
      </div>
    </section>
  );
}
