import { Button } from '../core/Button';
import { AnimeHeroItem } from '../motion';
import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';
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
  primaryCta: MarketingCta;
  imageSrc: string;
  secondaryCta?: MarketingCta;
  imageAlt?: string;
  /** Small uppercase kicker above the wordmark (business-specific, e.g. "Custom builds · Trade-ins"). */
  eyebrow?: string;
  variant?: MarketingHeroVariant;
  className?: string;
}

export function MarketingHero({
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
}: MarketingHeroProps) {
  const safe = useMotionSafe();
  const recipeId = currentRecipeId();
  // Recipe owns hero composition — codegen cannot collapse every business to one layout.
  const resolved = recipeHeroVariant(recipeId);
  const display = recipeDisplayClass(recipeId);

  const ctas = (
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
  );

  /* ─── warm-service: soft stacked service hero (offer-first, cream, rounded photo) ─── */
  if (resolved === 'service') {
    return (
      <section
        data-hero="service"
        className={cn('relative isolate overflow-hidden bg-card px-6 py-14 lg:px-12 lg:py-20', className)}
      >
        <div className="ui-mesh opacity-80" aria-hidden="true" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 top-0 h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-brand)_22%,transparent),transparent_68%)] blur-2xl"
        />
        <div className="relative mx-auto grid max-w-[92rem] items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
          <div>
            <AnimeHeroItem index={0}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-brand">
                {brandName}
              </p>
            </AnimeHeroItem>
            <AnimeHeroItem index={1}>
              <h1 className={cn(display, 'mt-4 max-w-[16ch] text-[clamp(2.6rem,5.5vw,4.75rem)] leading-[0.95] text-foreground')}>
                {headline}
              </h1>
            </AnimeHeroItem>
            <AnimeHeroItem index={2}>
              <p className="mt-5 max-w-md text-base leading-8 text-muted">{subcopy}</p>
            </AnimeHeroItem>
            <AnimeHeroItem index={3}>{ctas}</AnimeHeroItem>
          </div>
          <AnimeHeroItem index={1}>
            <div
              className={cn(
                'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.75rem)] shadow-[var(--shadow-ui)] ring-1 ring-border-subtle',
                safe && 'ui-float'
              )}
            >
              <img
                src={imageSrc}
                alt={imageAlt}
                className={cn('aspect-[5/4] w-full object-cover', safe && 'ui-kenburns')}
              />
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-tr from-brand/15 via-transparent to-transparent" />
            </div>
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
          'relative isolate border-b border-border-subtle bg-background px-6 py-10 lg:px-10',
          className
        )}
      >
        <div className="mx-auto grid max-w-[92rem] gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">{brandName}</p>
            <h1 className={cn(display, 'mt-2 text-[clamp(1.75rem,3vw,2.5rem)] leading-tight text-foreground')}>
              {headline}
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted">{subcopy}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button href={primaryCta.href} size="default">
                {primaryCta.label}
              </Button>
              {secondaryCta ? (
                <Button href={secondaryCta.href} size="default" variant="outline">
                  {secondaryCta.label}
                </Button>
              ) : null}
            </div>
          </div>
          <div className="overflow-hidden rounded-[var(--radius-ui)] border border-border-subtle">
            <img src={imageSrc} alt={imageAlt} className="aspect-[16/11] w-full object-cover" />
          </div>
        </div>
      </section>
    );
  }

  /* ─── product / craft: full-bleed immersive — brand owns the first viewport ─── */
  if (resolved === 'product') {
    const headlineDistinct =
      headline.trim().toLowerCase() !== brandName.trim().toLowerCase() && headline.trim().length > 0;
    return (
      <section
        data-hero="product"
        className={cn('relative isolate min-h-[100svh] overflow-hidden bg-[#0a0c0e] text-white', className)}
      >
        <img
          src={imageSrc}
          alt={imageAlt}
          className={cn('absolute inset-0 h-full w-full object-cover', safe && 'ui-kenburns')}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/50 to-black/15" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/25 to-transparent" />
        <div className="ui-vignette opacity-80" />
        <div className="ui-film-grain opacity-[0.22]" />
        {safe ? <div className="ui-hero-sheen" /> : null}
        <div className="relative z-10 mx-auto flex min-h-[100svh] max-w-[92rem] flex-col justify-end px-6 pb-16 pt-28 sm:pb-20 lg:px-12 lg:pb-24">
          <AnimeHeroItem index={0}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-white/55">
              {eyebrow || 'Studio · Clay · Fire'}
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
                href={primaryCta.href}
                size="lg"
                className="bg-white text-foreground shadow-[0_20px_50px_-20px_rgba(0,0,0,0.65)] hover:bg-white/92 hover:text-foreground"
              >
                {primaryCta.label}
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

  /* ─── editorial: type-led + edge photo ─── */
  if (resolved === 'editorial') {
    return (
      <section
        data-hero="editorial"
        className={cn('relative isolate bg-foreground px-6 py-24 text-background lg:px-10 lg:py-32', className)}
      >
        <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
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
            <AnimeHeroItem index={3}>{ctas}</AnimeHeroItem>
          </div>
          <AnimeHeroItem index={1}>
            <img
              src={imageSrc}
              alt={imageAlt}
              className="aspect-[5/4] w-full rounded-[var(--radius-ui)] object-cover shadow-[var(--shadow-ui)]"
            />
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
        <img
          src={imageSrc}
          alt={imageAlt}
          className={cn('absolute inset-0 h-full w-full object-cover', safe && 'ui-kenburns')}
        />
        <div className="ui-film-grain opacity-[0.1]" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/40 md:bg-gradient-to-r md:from-background/30 md:via-transparent md:to-transparent" />
      </div>
    </section>
  );
}
