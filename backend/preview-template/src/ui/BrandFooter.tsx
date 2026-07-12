import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface BrandFooterProps extends React.HTMLAttributes<HTMLElement> {
  brandName: string;
  description?: React.ReactNode;
  links?: React.ReactNode;
  secondaryLinks?: React.ReactNode;
  meta?: React.ReactNode;
}

export function BrandFooter({
  brandName,
  className,
  description,
  links,
  meta,
  secondaryLinks,
  ...props
}: BrandFooterProps) {
  return (
    <footer className={cn('px-6 py-12 text-white lg:px-10', className)} {...props}>
      <div className="mx-auto grid w-full max-w-7xl gap-10 border-t border-white/10 pt-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="max-w-2xl">
          <p className="text-lg font-semibold tracking-[-0.02em]">{brandName}</p>
          <p className="mt-4 text-sm leading-7 text-white/58">
            {description ?? 'Brand-forward digital journeys that feel premium from the first touch to the final conversion.'}
          </p>
        </div>
        <div className="grid gap-8 sm:grid-cols-2">
          <div className="space-y-3 text-sm text-white/72">{links}</div>
          <div className="space-y-3 text-sm text-white/52">{secondaryLinks}</div>
        </div>
      </div>
      {meta ? <div className="mx-auto mt-8 w-full max-w-7xl text-xs text-white/42">{meta}</div> : null}
    </footer>
  );
}

export default BrandFooter;
