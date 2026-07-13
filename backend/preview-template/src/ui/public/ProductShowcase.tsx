import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
import { cn } from '../lib/cn';

export interface ProductShowcaseItem {
  title: string;
  description: string;
  imageSrc: string;
  imageAlt?: string;
}

export interface ProductShowcaseProps {
  heading: string;
  items: ProductShowcaseItem[];
  description?: string;
  className?: string;
}

export function ProductShowcase({ className, description, heading, items }: ProductShowcaseProps) {
  const [featured, secondary, tertiary] = items;
  return (
    <section className={cn('bg-[#12161a] px-6 py-28 text-[#f3f5f4] lg:px-12 lg:py-36', className)}>
      <div className="mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-8 border-b border-white/10 pb-12 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <h2 className="font-display text-[clamp(3rem,6vw,5.5rem)] italic leading-[0.92] tracking-[-0.04em]">
            {heading}
          </h2>
          {description ? <p className="max-w-md text-base leading-8 text-white/55 lg:justify-self-end">{description}</p> : null}
        </MotionReveal>

        {featured ? (
          <MotionReveal className="mt-12 grid gap-6 lg:grid-cols-12 lg:gap-5">
            <figure className="relative overflow-hidden lg:col-span-8">
              <img src={featured.imageSrc} alt={featured.imageAlt ?? ''} className="aspect-[16/11] w-full object-cover" />
              <figcaption className="mt-5 max-w-xl">
                <p className="text-[11px] font-semibold tracking-[0.2em] text-brand uppercase">Lead ritual</p>
                <h3 className="mt-2 font-display text-4xl italic tracking-tight">{featured.title}</h3>
                <p className="mt-3 text-sm leading-7 text-white/60">{featured.description}</p>
              </figcaption>
            </figure>
            <div className="flex flex-col gap-5 lg:col-span-4">
              {secondary ? (
                <figure className="overflow-hidden">
                  <img src={secondary.imageSrc} alt={secondary.imageAlt ?? ''} className="aspect-[4/5] w-full object-cover" />
                  <figcaption className="mt-4">
                    <h3 className="font-display text-2xl italic">{secondary.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-white/55">{secondary.description}</p>
                  </figcaption>
                </figure>
              ) : null}
              {tertiary ? (
                <MotionStagger>
                  <MotionStaggerItem>
                    <figure className="overflow-hidden border-t border-white/10 pt-5">
                      <h3 className="font-display text-2xl italic">{tertiary.title}</h3>
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
