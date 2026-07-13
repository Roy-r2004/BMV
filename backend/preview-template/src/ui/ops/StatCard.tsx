import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { cn } from '../lib/cn';

export interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  hint?: string;
  className?: string;
}

/** Dense KPI tile for ops floor — no equal-card fluff. */
export function StatCard({ className, delta, hint, label, value }: StatCardProps) {
  const positive = delta?.startsWith('+');
  const negative = delta?.startsWith('-');

  return (
    <div className={cn('border-r border-border-subtle pr-5 last:border-r-0', className)}>
      <div className="flex items-center gap-2">
        <UiIcon name="chart" className="h-3.5 w-3.5 text-brand" />
        <p className="text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">{label}</p>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <p className="font-display text-[2.1rem] leading-none tracking-tight text-foreground tabular-nums">{value}</p>
        {delta ? (
          <span
            className={cn(
              'text-xs font-semibold tabular-nums',
              positive && 'text-brand',
              negative && 'text-accent',
              !positive && !negative && 'text-muted'
            )}
          >
            {delta}
          </span>
        ) : null}
      </div>
      {hint ? <p className="mt-1.5 text-[11px] leading-4 text-muted">{hint}</p> : null}
    </div>
  );
}
