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

export function BrandFooter({
  brandName,
  className,
  description = 'Premium digital journeys from first visit to booked revenue.',
  links = [],
  meta,
}: BrandFooterProps) {
  const normalizedLinks = (links || [])
    .map((link) => ({
      label: asText((link as { label?: string; title?: string }).label ?? (link as { title?: string }).title),
      href: String((link as { href?: string }).href || '#'),
    }))
    .filter((link) => link.label);

  const metaText = asText(meta);

  return (
    <footer className={cn('border-t border-border-subtle px-6 py-14 lg:px-10', className)}>
      <div className="mx-auto grid w-full max-w-7xl gap-10 md:grid-cols-[1.3fr_0.7fr]">
        <div>
          <p className="font-display text-4xl italic tracking-tight text-foreground">{brandName}</p>
          <p className="mt-4 max-w-xl text-sm leading-7 text-muted">{description}</p>
        </div>
        {normalizedLinks.length > 0 ? (
          <nav className="flex flex-wrap content-start gap-x-6 gap-y-3 text-sm text-foreground" aria-label="Footer">
            {normalizedLinks.map((link) => (
              <AppLink key={`${link.label}-${link.href}`} href={link.href} className="hover:text-brand">
                {link.label}
              </AppLink>
            ))}
          </nav>
        ) : null}
      </div>
      {metaText ? <p className="mx-auto mt-10 w-full max-w-7xl text-xs text-muted">{metaText}</p> : null}
    </footer>
  );
}
