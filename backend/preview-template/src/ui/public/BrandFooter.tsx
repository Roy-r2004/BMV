import * as React from 'react';

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
  const normalizedLinks = normalizeLinks(links);
  const metaText = asText(meta);
  const year = new Date().getFullYear();
  const wordmarkSize = `clamp(2.75rem, ${Math.min(14, 130 / Math.max(brandName.length, 6)).toFixed(1)}vw, 11rem)`;

  if (variant === 'compact') {
    return (
      <footer
        className={cn(
          'relative border-t border-border-subtle bg-card px-6 py-12 text-foreground lg:px-12',
          className
        )}
        data-footer-variant={variant}
      >
        <div className="mx-auto flex w-full max-w-[92rem] flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <div className="max-w-lg">
            <p className="font-display text-2xl tracking-tight text-foreground">{brandName}</p>
            <p className="mt-3 text-sm leading-7 text-muted">{description}</p>
          </div>
          {normalizedLinks.length > 0 ? (
            <nav className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted" aria-label="Footer">
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
        <div className="mx-auto mt-10 flex w-full max-w-[92rem] flex-wrap items-center justify-between gap-3 text-xs text-muted">
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
            <p className="font-display text-[clamp(2.5rem,5vw,4rem)] italic leading-[0.95] tracking-[-0.03em]">
              {brandName}
            </p>
            <p className="mt-5 max-w-md text-base leading-8 text-muted">{description}</p>
          </div>
          <div className="grid gap-8 sm:grid-cols-2">
            {normalizedLinks.length > 0 ? (
              <nav className="flex flex-col gap-3 text-sm font-medium" aria-label="Footer">
                {normalizedLinks.map((link) => (
                  <AppLink
                    key={`${link.label}-${link.href}`}
                    href={link.href}
                    className="text-foreground/80 transition-colors hover:text-brand"
                  >
                    {link.label}
                  </AppLink>
                ))}
              </nav>
            ) : (
              <p className="text-sm leading-7 text-muted">Crafted presence — from first visit to booked work.</p>
            )}
            <div className="text-xs leading-6 text-muted">
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
        'relative isolate overflow-hidden bg-foreground px-6 pb-10 pt-20 text-white lg:px-12 lg:pt-24',
        className
      )}
      data-footer-variant="statement"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_60%_at_15%_0%,color-mix(in_srgb,var(--color-brand)_35%,transparent),transparent_60%)]" />
      <div className="ui-film-grain opacity-[0.1]" />
      <div className="relative mx-auto w-full max-w-[92rem]">
        <div className="grid gap-10 border-b border-white/10 pb-14 md:grid-cols-[1.3fr_0.7fr]">
          <p className="max-w-xl text-base leading-8 text-white/60">{description}</p>
          {normalizedLinks.length > 0 ? (
            <nav
              className="flex flex-wrap content-start gap-x-7 gap-y-3 text-sm font-medium text-white/75 md:justify-end"
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
          className="mt-10 select-none whitespace-nowrap font-display leading-[0.85] tracking-[-0.04em] text-white/95 [mask-image:linear-gradient(to_bottom,black_55%,transparent_100%)]"
          style={{ fontSize: wordmarkSize }}
        >
          {brandName}
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 text-xs text-white/40">
          <p>
            © {year} {brandName}
          </p>
          {metaText ? <p>{metaText}</p> : null}
        </div>
      </div>
    </footer>
  );
}
