import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem, useMotionSafe } from '../motion';
import { cn } from '../lib/cn';

export interface ProductShowcaseItem {
  title: string;
  description: string;
  imageSrc: string;
  imageAlt?: string;
  href?: string;
  badge?: string;
}

export interface ProductShowcaseProps {
  heading: string;
  items: ProductShowcaseItem[];
  description?: string;
  className?: string;
}

export function ProductShowcase({ className, description, heading, items }: ProductShowcaseProps) {
  const safe = useMotionSafe();
  const [featured, secondary, tertiary] = items;
  return (
    <section className={cn('relative isolate overflow-hidden bg-[#0b0d10] px-6 py-28 text-[#f3f5f4] lg:px-12 lg:py-36', className)}>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(80%_60%_at_20%_0%,rgb(255_255_255_/0.08),transparent_55%)]" />
      <div className="ui-film-grain opacity-[0.1]" />
      <div className="relative mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-8 border-b border-white/10 pb-12 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <h2 className="font-display text-[clamp(3rem,6vw,5.75rem)] leading-[0.9] tracking-[-0.04em]">
            {heading}
          </h2>
          {description ? <p className="max-w-md text-base leading-8 text-white/55 lg:justify-self-end">{description}</p> : null}
        </MotionReveal>

        {featured ? (
          <MotionReveal className="mt-12 grid gap-6 lg:grid-cols-12 lg:gap-5">
            <figure className="group relative overflow-hidden lg:col-span-8">
              <img
                src={featured.imageSrc}
                alt={featured.imageAlt ?? ''}
                className={cn(
                  'aspect-[16/11] w-full object-cover transition duration-700 group-hover:scale-[1.03]',
                  safe && 'ui-kenburns'
                )}
              />
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
              <figcaption className="mt-5 max-w-xl">
                <p className="text-[11px] font-semibold tracking-[0.2em] text-white/50 uppercase">
                  {featured.badge || 'Lead drop'}
                </p>
                <h3 className="mt-2 font-display text-4xl tracking-tight">{featured.title}</h3>
                <p className="mt-3 text-sm leading-7 text-white/60">{featured.description}</p>
              </figcaption>
            </figure>
            <div className="flex flex-col gap-5 lg:col-span-4">
              {secondary ? (
                <figure className="group overflow-hidden">
                  <img
                    src={secondary.imageSrc}
                    alt={secondary.imageAlt ?? ''}
                    className="aspect-[4/5] w-full object-cover transition duration-700 group-hover:scale-[1.03]"
                  />
                  <figcaption className="mt-4">
                    <h3 className="font-display text-2xl tracking-tight">{secondary.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-white/55">{secondary.description}</p>
                  </figcaption>
                </figure>
              ) : null}
              {tertiary ? (
                <MotionStagger>
                  <MotionStaggerItem>
                    <figure className="overflow-hidden border-t border-white/10 pt-5">
                      <h3 className="font-display text-2xl tracking-tight">{tertiary.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-white/55">{tertiary.description}</p>
                    </figure>
                  </MotionStaggerItem>
                </MotionStagger>
              ) : null}
            </div>
          </MotionReveal>
        ) : null}
      </div>
    </section>
  );
}
