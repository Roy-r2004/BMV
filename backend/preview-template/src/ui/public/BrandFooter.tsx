import * as React from 'react';

import { usePublicNavItems } from '../../lib/app-nav';
import { recipeFooterVariant, type FooterVariant } from '../../lib/recipe';
import { AppLink } from '../lib/AppLink';
import { cn } from '../lib/cn';

export interface BrandFooterLink {
  label: string;
  href: string;
}

export interface BrandFooterProps {
  brandName: string;
  description?: string;
  links?: Array<BrandFooterLink | { title?: string; label?: string; href: string }>;
  meta?: string | Array<{ title?: string; label?: string; href?: string } | string>;
  className?: string;
  /** Recipe-driven layout — defaults from the active design recipe. */
  variant?: FooterVariant;
}

function asText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => asText(item)).filter(Boolean).join(' · ');
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const pick = record.label ?? record.title ?? record.name ?? record.text;
    if (pick != null) return asText(pick);
  }
  return '';
}

function normalizeLinks(
  links: BrandFooterProps['links']
): Array<{ label: string; href: string }> {
  const flattened = (links || []).flatMap((link) => {
    const record = link as {
      label?: string;
      title?: string;
      href?: string;
      items?: Array<{ label?: string; title?: string; href?: string }>;
    };
    if (Array.isArray(record.items) && record.items.length > 0) {
      return record.items.map((item) => ({
        label: asText(item.label ?? item.title),
        href: String(item.href || '#'),
      }));
    }
    return [
      {
        label: asText(record.label ?? record.title),
        href: String(record.href || '#'),
      },
    ];
  });
  return flattened.filter((link) => link.label);
}

/** Statement / compact / columns footer — recipe picks the face. */
export function BrandFooter({
  brandName,
  className,
  description = 'Premium digital journeys from first visit to booked revenue.',
  links = [],
  meta,
  variant: variantProp,
}: BrandFooterProps) {
  const variant = variantProp ?? recipeFooterVariant();
  // No composed page has ever passed `links`. Every call site writes only
  // `brandName` and `description`, so the nav was dropped, the right 35% of the
  // statement footer's top row rendered blank, and the whole footer came down
  // to one sentence and a copyright — a dead surface at the bottom of every
  // page. The header's own items are the right fallback: they are the public
  // routes that exist, already filtered of admin/owner/AI paths.
  const navFallback = usePublicNavItems();
  const normalizedLinks = normalizeLinks(
    links && links.length > 0
      ? links
      : navFallback.map((item) => ({ label: item.label, href: item.href }))
  );
  const metaText = asText(meta);
  const year = new Date().getFullYear();
  // Statement wordmark is a quiet signature — never a second hero billboard.
  const wordmarkSize = `clamp(1.5rem, ${Math.min(5.5, 56 / Math.max(brandName.length, 6)).toFixed(1)}vw, 2.75rem)`;

  if (variant === 'compact') {
    return (
      <footer
        className={cn(
          'relative border-t border-border-subtle bg-card px-6 py-14 text-foreground lg:px-12',
          className
        )}
        data-footer-variant={variant}
      >
        <div className="mx-auto flex w-full max-w-[92rem] flex-col gap-10 md:flex-row md:items-end md:justify-between">
          <div className="max-w-lg">
            <p className="font-display text-[clamp(1.75rem,3vw,2.35rem)] leading-tight tracking-[-0.03em] text-foreground">
              {brandName}
            </p>
            <p className="mt-4 font-sans text-[0.95rem] leading-7 text-muted">{description}</p>
          </div>
          {normalizedLinks.length > 0 ? (
            <nav
              className="flex flex-wrap gap-x-6 gap-y-3 font-sans text-[0.95rem] tracking-wide text-muted"
              aria-label="Footer"
            >
              {normalizedLinks.map((link) => (
                <AppLink
                  key={`${link.label}-${link.href}`}
                  href={link.href}
                  className="transition-colors hover:text-foreground"
                >
                  {link.label}
                </AppLink>
              ))}
            </nav>
          ) : null}
        </div>
        <div className="mx-auto mt-12 flex w-full max-w-[92rem] flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-6 font-sans text-sm text-muted">
          <p>
            © {year} {brandName}
          </p>
          {metaText ? <p>{metaText}</p> : null}
        </div>
      </footer>
    );
  }

  if (variant === 'columns') {
    return (
      <footer
        className={cn(
          'relative isolate overflow-hidden border-t border-border-subtle bg-[color-mix(in_srgb,var(--color-brand)_6%,var(--color-background))] px-6 py-16 text-foreground lg:px-12 lg:py-20',
          className
        )}
        data-footer-variant={variant}
      >
        <div className="ui-mesh opacity-40" aria-hidden="true" />
        <div className="relative mx-auto grid w-full max-w-[92rem] gap-12 md:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="font-display text-[clamp(2.25rem,4.5vw,3.5rem)] leading-[0.98] tracking-[-0.03em] text-foreground">
              {brandName}
            </p>
            <p className="mt-5 max-w-md font-sans text-base leading-8 text-muted">{description}</p>
          </div>
          <div className="grid gap-8 sm:grid-cols-2">
            {normalizedLinks.length > 0 ? (
              <nav className="flex flex-col gap-3.5 font-sans text-[0.95rem] font-medium" aria-label="Footer">
                {normalizedLinks.map((link) => (
                  <AppLink
                    key={`${link.label}-${link.href}`}
                    href={link.href}
                    className="text-foreground/85 transition-colors hover:text-brand"
                  >
                    {link.label}
                  </AppLink>
                ))}
              </nav>
            ) : (
              <p className="font-sans text-sm leading-7 text-muted">
                Crafted presence — from first visit to booked work.
              </p>
            )}
            <div className="font-sans text-sm leading-7 text-muted">
              <p>
                © {year} {brandName}
              </p>
              {metaText ? <p className="mt-2">{metaText}</p> : null}
            </div>
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer
      className={cn(
        'relative isolate overflow-hidden px-6 pb-12 pt-20 lg:px-12 lg:pt-24',
        className
      )}
      data-footer-variant="statement"
    >
      {/* The statement footer paints its own plane instead of wearing
          `bg-foreground` on the root, because the root's background was
          defeated two ways and both left white type on a pale surface:
          (1) a composed page passing `className="bg-surface text-muted"` —
          `cn` is tailwind-merge, so the caller's colours win, and request 62
          shipped an illegible footer; (2) the `nocturne` recipe, whose
          `--color-foreground` is #f4f0ea. A brand-tinted near-black is dark
          for every brand hue and reachable by neither. Ink lives on the inner
          wrapper for the same reason. */}
      {/* The hairline is on the plane, not the root, for the same reason as the
          plane itself — and it is not decoration. A `CTABand` above this footer
          is also near-black, so request 48 rendered 237px of unbroken dark with
          no border, no rule and no background step in it: nothing told the eye
          a new section had started. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 border-t border-white/15 bg-[color-mix(in_srgb,var(--color-brand)_30%,#0b0e10)]"
      />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_60%_at_15%_0%,color-mix(in_srgb,var(--color-brand)_35%,transparent),transparent_60%)]" />
      <div className="ui-film-grain opacity-[0.1]" />
      <div className="relative mx-auto w-full max-w-[92rem] text-white">
        <div className="grid gap-10 border-b border-white/15 pb-14 md:grid-cols-[1.3fr_0.7fr]">
          <p className="max-w-xl font-sans text-base leading-8 text-white/75">{description}</p>
          {normalizedLinks.length > 0 ? (
            <nav
              className="flex flex-wrap content-start gap-x-7 gap-y-3 font-sans text-[0.95rem] font-medium tracking-wide text-white/85 md:justify-end"
              aria-label="Footer"
            >
              {normalizedLinks.map((link) => (
                <AppLink
                  key={`${link.label}-${link.href}`}
                  href={link.href}
                  className="transition-colors hover:text-white"
                >
                  {link.label}
                </AppLink>
              ))}
            </nav>
          ) : null}
        </div>

        <p
          aria-hidden="true"
          // `pl-[0.06em]`: the display face is italic, so the first glyph's
          // left overhang sits outside the box and the ancestor's
          // `overflow-hidden` sheared it — every page footer rendered
          // "Jeanne Kassab Art" with a clipped J.
          // No fade mask: it was a gesture that read at billboard scale. At
          // signature scale it just looks like the name got cut off.
          className="mt-12 select-none whitespace-nowrap pl-[0.06em] font-display leading-[0.9] tracking-[-0.035em] text-white/95"
          style={{ fontSize: wordmarkSize }}
        >
          {brandName}
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 font-sans text-sm tracking-wide text-white/55">
          <p>
            © {year} {brandName}
          </p>
          {metaText ? <p>{metaText}</p> : null}
        </div>
      </div>
    </footer>
  );
}
