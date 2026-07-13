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
    <footer className={cn('border-t border-white/10 px-6 py-12 text-background lg:px-10', className)}>
      <div className="mx-auto grid w-full max-w-7xl gap-10 md:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="font-display text-lg tracking-tight">{brandName}</p>
          <p className="mt-4 max-w-xl text-sm leading-7 text-background/58">{description}</p>
        </div>
        {links.length > 0 ? (
          <nav className="flex flex-wrap gap-x-6 gap-y-3 text-sm text-background/72" aria-label="Footer">
            {links.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-background">
                {link.label}
              </a>
            ))}
          </nav>
        ) : null}
      </div>
      {meta ? <p className="mx-auto mt-8 w-full max-w-7xl text-xs text-background/40">{meta}</p> : null}
    </footer>
  );
}
