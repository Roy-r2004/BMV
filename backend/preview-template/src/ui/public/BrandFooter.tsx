import * as React from 'react';

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

/** Statement footer — oversized wordmark closes the page like a film credit. */
export function BrandFooter({
  brandName,
  className,
  description = 'Premium digital journeys from first visit to booked revenue.',
  links = [],
  meta,
}: BrandFooterProps) {
  // Flatten nested groups `{ title, items: [{ label, href }] }` that codegen often emits.
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
  const normalizedLinks = flattened.filter((link) => link.label);

  const metaText = asText(meta);
  const year = new Date().getFullYear();
  // Scale the wordmark to the name length so long brands still fit on one line
  // (uppercase display glyphs average ~0.62em wide).
  const wordmarkSize = `clamp(2.75rem, ${Math.min(14, 130 / Math.max(brandName.length, 6)).toFixed(1)}vw, 11rem)`;

  return (
    <footer className={cn('relative isolate overflow-hidden bg-foreground px-6 pb-10 pt-20 text-white lg:px-12 lg:pt-24', className)}>
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
