import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface CTABandProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode;
  headline: React.ReactNode;
  description?: React.ReactNode;
  primaryAction?: React.ReactNode;
  secondaryAction?: React.ReactNode;
}

export function CTABand({
  className,
  description,
  eyebrow,
  headline,
  primaryAction,
  secondaryAction,
  ...props
}: CTABandProps) {
  return (
    <section className={cn('px-6 py-18 lg:px-10 lg:py-24', className)} {...props}>
      <div className="mx-auto w-full max-w-7xl overflow-hidden rounded-[2rem] border border-white/10 bg-white/7 p-8 shadow-[0_24px_80px_-36px_rgba(99,102,241,0.55)] backdrop-blur-sm sm:p-10 lg:p-12">
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-48 bg-[radial-gradient(circle_at_top,rgba(129,140,248,0.28),transparent_60%)]"
        />
        <div className="relative flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            {eyebrow ? (
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-brand">{eyebrow}</p>
            ) : null}
            <h2 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-white sm:text-4xl">{headline}</h2>
            {description ? <p className="mt-4 text-base leading-7 text-white/68">{description}</p> : null}
          </div>
          {(primaryAction || secondaryAction) && (
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap lg:justify-end">
              {primaryAction}
              {secondaryAction}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default CTABand;
