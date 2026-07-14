import * as React from 'react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface LogoMarqueeItem {
  label: string;
}

export interface LogoMarqueeProps {
  items: LogoMarqueeItem[];
  heading?: string;
  /** 'display' renders a kinetic oversized-type strip for cinematic homes. */
  size?: 'default' | 'display';
  className?: string;
}

/**
 * Scrolling trust rail — heading lives outside the track so labels never shear under it.
 * `size="display"` turns it into a kinetic typographic band.
 */
export function LogoMarquee({ className, heading, items, size = 'default' }: LogoMarqueeProps) {
  const safe = useMotionSafe();
  const loop = safe ? [...items, ...items] : items;

  if (size === 'display') {
    return (
      <section
        className={cn('overflow-hidden border-y border-foreground/10 bg-background py-6 lg:py-8', className)}
        aria-label={heading || 'Highlights'}
      >
        <div
          className={cn(
            'relative min-w-0 overflow-hidden',
            '[mask-image:linear-gradient(to_right,transparent,black_3rem,black_calc(100%-3rem),transparent)]',
            '[-webkit-mask-image:linear-gradient(to_right,transparent,black_3rem,black_calc(100%-3rem),transparent)]'
          )}
        >
          <div className={cn('flex w-max items-center', safe && 'ui-marquee-track')}>
            {loop.map((item, index) => (
              <div key={`${item.label}-${index}`} className="flex shrink-0 items-baseline gap-8 pr-8">
                <p className="whitespace-nowrap font-display text-[clamp(2rem,4.5vw,3.75rem)] leading-none tracking-[-0.03em] text-foreground/85">
                  {item.label}
                </p>
                <span aria-hidden="true" className="select-none font-display text-[clamp(1.5rem,3vw,2.5rem)] text-brand/60">
                  ✦
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={cn('border-y border-border-subtle bg-card px-6 py-8 lg:px-12', className)}>
      <div className="mx-auto flex w-full max-w-[92rem] items-center gap-6 lg:gap-10">
        {heading ? (
          <p className="relative z-20 shrink-0 bg-card pr-2 text-[11px] font-semibold tracking-[0.18em] text-muted uppercase">
            {heading}
          </p>
        ) : null}

        <div
          className={cn(
            'relative min-w-0 flex-1 overflow-hidden',
            '[mask-image:linear-gradient(to_right,transparent,black_1.75rem,black_calc(100%-1.75rem),transparent)]',
            '[-webkit-mask-image:linear-gradient(to_right,transparent,black_1.75rem,black_calc(100%-1.75rem),transparent)]'
          )}
        >
          {safe ? (
            <div className="ui-marquee-track flex w-max items-center">
              {loop.map((item, index) => (
                <div key={`${item.label}-${index}`} className="flex shrink-0 items-center gap-10 pr-10">
                  <p className="whitespace-nowrap text-[13px] font-medium tracking-[0.02em] text-foreground/55">
                    {item.label}
                  </p>
                  <span aria-hidden="true" className="text-[11px] text-border-subtle select-none">
                    ·
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <ul className="m-0 flex list-none flex-wrap items-center gap-x-8 gap-y-2 p-0">
              {items.map((item) => (
                <li
                  key={item.label}
                  className="whitespace-nowrap text-[13px] font-medium tracking-[0.02em] text-foreground/55"
                >
                  {item.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
