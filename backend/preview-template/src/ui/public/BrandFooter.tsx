import * as React from 'react';

import { cn } from '../lib/cn';

export interface BrandFooterLink {
  label: string;
  href: string;
}

export interface BrandFooterProps {
  brandName: string;
  description?: string;
  links?: BrandFooterLink[];
  meta?: string;
  className?: string;
}

export function BrandFooter({
  brandName,
  className,
  description = 'Premium digital journeys from first visit to booked revenue.',
  links = [],
  meta,
}: BrandFooterProps) {
  return (
    <footer className={cn('border-t border-border-subtle px-6 py-14 lg:px-10', className)}>
      <div className="mx-auto grid w-full max-w-7xl gap-10 md:grid-cols-[1.3fr_0.7fr]">
        <div>
          <p className="font-display text-3xl tracking-tight text-foreground">{brandName}</p>
          <p className="mt-4 max-w-xl text-sm leading-7 text-muted">{description}</p>
        </div>
        {links.length > 0 ? (
          <nav className="flex flex-wrap content-start gap-x-6 gap-y-3 text-sm text-foreground" aria-label="Footer">
            {links.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-brand">
                {link.label}
              </a>
            ))}
          </nav>
        ) : null}
      </div>
      {meta ? <p className="mx-auto mt-10 w-full max-w-7xl text-xs text-muted">{meta}</p> : null}
    </footer>
  );
}
