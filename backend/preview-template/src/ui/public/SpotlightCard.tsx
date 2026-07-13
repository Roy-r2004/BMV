import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { cn } from '../lib/cn';

export interface SpotlightCardProps {
  title: string;
  description: string;
  icon?: string;
  className?: string;
}

export function SpotlightCard({ className, description, icon = 'zap', title }: SpotlightCardProps) {
  return (
    <article className={cn('relative', className)}>
      <div className="flex flex-col gap-5 md:flex-row md:items-start md:gap-10">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
          <UiIcon name={icon} className="h-5 w-5" />
        </span>
        <div>
          <h3 className="font-display text-[clamp(2rem,3.5vw,3.25rem)] italic tracking-tight text-foreground">{title}</h3>
          <p className="mt-3 max-w-2xl text-base leading-8 text-muted">{description}</p>
        </div>
      </div>
    </article>
  );
}
