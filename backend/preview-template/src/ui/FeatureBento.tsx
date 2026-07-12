import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface FeatureBentoItem {
  id?: string;
  title: React.ReactNode;
  description: React.ReactNode;
  icon?: React.ReactNode;
}

export interface FeatureBentoProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode;
  heading?: React.ReactNode;
  description?: React.ReactNode;
  items: FeatureBentoItem[];
}

function getTileSpan(index: number) {
  if (index === 0) {
    return 'md:col-span-2 md:row-span-2';
  }

  if (index === 1 || index === 2) {
    return 'md:col-span-1';
  }

  return 'md:col-span-1';
}

export function FeatureBento({
  className,
  description,
  eyebrow,
  heading,
  items,
  ...props
}: FeatureBentoProps) {
  return (
    <section className={cn('px-6 py-18 lg:px-10 lg:py-24', className)} {...props}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-10">
        {(eyebrow || heading || description) && (
          <div className="max-w-3xl">
            {eyebrow ? (
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-brand">{eyebrow}</p>
            ) : null}
            {heading ? <h2 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-white sm:text-4xl">{heading}</h2> : null}
            {description ? <p className="mt-4 text-base leading-7 text-white/65">{description}</p> : null}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-3 md:auto-rows-[minmax(11rem,1fr)]">
          {items.map((item, index) => (
            <article
              key={item.id ?? `${index}-${String(item.title)}`}
              className={cn(
                'group relative overflow-hidden rounded-[1.75rem] border border-white/10 bg-white/6 p-6 shadow-[0_12px_50px_-24px_rgba(99,102,241,0.55)] backdrop-blur-sm transition-transform duration-200 hover:-translate-y-0.5',
                index === 0 ? 'justify-between bg-white/8 p-8' : '',
                getTileSpan(index)
              )}
            >
              <div
                aria-hidden="true"
                className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.16),transparent_40%)] opacity-80 transition-opacity duration-200 group-hover:opacity-100"
              />
              <div className="relative flex h-full flex-col">
                {item.icon ? (
                  <div className="mb-8 inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-white/12 bg-white/10 text-white/90">
                    {item.icon}
                  </div>
                ) : null}
                <h3 className={cn('text-xl font-semibold tracking-[-0.02em] text-white', index === 0 ? 'text-2xl sm:text-3xl' : '')}>
                  {item.title}
                </h3>
                <p className={cn('mt-3 max-w-xl text-sm leading-7 text-white/68', index === 0 ? 'mt-4 text-base' : '')}>
                  {item.description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
