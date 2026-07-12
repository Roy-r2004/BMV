import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface TestimonialRailItem {
  id?: string;
  quote: React.ReactNode;
  author: React.ReactNode;
  role?: React.ReactNode;
}

export interface TestimonialRailProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode;
  heading?: React.ReactNode;
  items: TestimonialRailItem[];
}

export function TestimonialRail({ className, eyebrow, heading, items, ...props }: TestimonialRailProps) {
  return (
    <section className={cn('px-6 py-18 lg:px-10 lg:py-24', className)} {...props}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8">
        {(eyebrow || heading) && (
          <div className="max-w-2xl">
            {eyebrow ? <p className="text-sm font-semibold uppercase tracking-[0.24em] text-brand">{eyebrow}</p> : null}
            {heading ? <h2 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-white sm:text-4xl">{heading}</h2> : null}
          </div>
        )}
        <div className="-mx-2 overflow-x-auto px-2 [scrollbar-width:none]">
          <div className="flex min-w-full gap-4">
            {items.map((item, index) => (
              <article
                key={item.id ?? `${index}-${String(item.author)}`}
                className="min-h-64 min-w-[18rem] flex-1 rounded-[1.75rem] border border-white/10 bg-white/6 p-6 shadow-[0_18px_60px_-34px_rgba(99,102,241,0.5)] backdrop-blur-sm md:min-w-[22rem]"
              >
                <p className="text-base leading-7 text-white/78">"{item.quote}"</p>
                <div className="mt-8">
                  <p className="font-semibold text-white">{item.author}</p>
                  {item.role ? <p className="mt-1 text-sm text-white/52">{item.role}</p> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default TestimonialRail;
