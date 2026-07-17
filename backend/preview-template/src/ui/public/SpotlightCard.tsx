import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { MotionReveal } from '../motion';
import { cn } from '../lib/cn';

export interface SpotlightCardProps {
  title: string;
  description: string;
  icon?: string;
  className?: string;
}

export function SpotlightCard({ className, description, icon = 'zap', title }: SpotlightCardProps) {
  return (
    <MotionReveal>
      <article
        className={cn(
          'group relative overflow-hidden rounded-[calc(var(--radius-ui)+0.5rem)] border border-border-subtle bg-card p-8 shadow-[var(--shadow-ui)] md:p-10',
          className
        )}
      >
        <div className="ui-mesh opacity-60" aria-hidden="true" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-brand)_22%,transparent),transparent_70%)] transition duration-500 group-hover:scale-110"
        />
        <div className="relative flex flex-col gap-5 md:flex-row md:items-start md:gap-10">
          <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand ring-1 ring-brand/15 transition group-hover:bg-brand group-hover:text-white">
            <UiIcon name={icon} className="h-5 w-5" />
          </span>
          <div>
            <h3 className="font-display text-[clamp(2rem,3.5vw,3.25rem)] italic tracking-tight text-foreground">
              {title}
            </h3>
            <p className="mt-3 max-w-2xl text-base leading-8 text-muted">{description}</p>
          </div>
        </div>
      </article>
    </MotionReveal>
  );
}
