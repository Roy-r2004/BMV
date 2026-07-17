import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { MotionHover } from '../motion';
import { cn } from '../lib/cn';

export type StatCardVariant = 'card' | 'strip';

export interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  hint?: string;
  /** UiIcon name rendered in the corner chip (defaults to 'chart'). */
  icon?: string;
  /** Soft branded card (default) or dense strip cell for shared KPI rows. */
  variant?: StatCardVariant;
  className?: string;
}

/** KPI tile — brand-token card by default for ops dashboards. */
export function StatCard({
  className,
  delta,
  hint,
  icon = 'chart',
  label,
  value,
  variant = 'card',
}: StatCardProps) {
  const positive = delta?.startsWith('+');
  const negative = delta?.startsWith('-');

  if (variant === 'strip') {
    return (
      <div className={cn('border-r border-border-subtle pr-5 last:border-r-0', className)}>
        <div className="flex items-center gap-2">
          <UiIcon name={icon} className="h-3.5 w-3.5 text-brand" />
          <p className="text-[10px] font-semibold tracking-[0.16em] text-muted uppercase">{label}</p>
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <p className="font-display text-[2.1rem] leading-none tracking-tight text-foreground tabular-nums">
            {value}
          </p>
          {delta ? (
            <span
              className={cn(
                'text-xs font-semibold tabular-nums',
                positive && 'text-emerald-600',
                negative && 'text-rose-500',
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

  return (
    <MotionHover>
      <div
        className={cn(
          'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.55rem)] border border-border-subtle bg-card p-5 shadow-[var(--shadow-ui)]',
          className
        )}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[color-mix(in_srgb,var(--color-brand)_14%,transparent)] blur-2xl"
        />
        <div className="relative flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-muted">{label}</p>
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-[calc(var(--radius-ui)+0.2rem)] bg-[color-mix(in_srgb,var(--color-brand)_14%,white)] text-brand ring-1 ring-brand/10">
            <UiIcon name={icon} className="h-4 w-4" />
          </span>
        </div>
        <div className="relative mt-4 flex items-end gap-2">
          <p className="font-display text-[2rem] font-semibold leading-none tracking-tight text-foreground tabular-nums">
            {value}
          </p>
          {delta ? (
            <span
              className={cn(
                'mb-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums',
                positive && 'bg-emerald-50 text-emerald-700',
                negative && 'bg-rose-50 text-rose-600',
                !positive && !negative && 'bg-[color-mix(in_srgb,var(--color-brand)_8%,var(--color-background))] text-muted'
              )}
            >
              {delta}
            </span>
          ) : null}
        </div>
        {hint ? <p className="relative mt-2 text-xs leading-5 text-muted">{hint}</p> : null}
      </div>
    </MotionHover>
  );
}
