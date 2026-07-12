import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface MarqueeStripProps extends React.HTMLAttributes<HTMLDivElement> {
  label?: React.ReactNode;
  items: React.ReactNode[];
}

export function MarqueeStrip({ className, items, label, ...props }: MarqueeStripProps) {
  return (
    <div className={cn('border-y border-white/10 bg-white/4', className)} {...props}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-6 py-5 lg:flex-row lg:items-center lg:px-10">
        {label ? (
          <p className="shrink-0 text-xs font-semibold uppercase tracking-[0.24em] text-white/45">{label}</p>
        ) : null}
        <div className="-mx-2 overflow-x-auto [scrollbar-width:none]">
          <div className="flex min-w-max items-center gap-3 px-2">
            {items.map((item, index) => (
              <div
                key={index}
                className="inline-flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-medium text-white/70 backdrop-blur-sm"
              >
                {item}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
