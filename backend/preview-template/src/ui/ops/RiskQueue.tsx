import * as React from 'react';

import { Button } from '../core/Button';
import { MotionStagger, MotionStaggerItem } from '../motion';
import { cn } from '../lib/cn';

export type RiskSeverity = 'high' | 'medium' | 'low';

export interface RiskQueueItem {
  id: string;
  title: string;
  detail: string;
  severity: RiskSeverity;
  actionLabel?: string;
}

export interface RiskQueueProps {
  heading: string;
  items: RiskQueueItem[];
  onAction?: (id: string) => void;
  className?: string;
}

const severityTone: Record<RiskSeverity, string> = {
  high: 'bg-rose-100 text-rose-800 ring-1 ring-rose-200/80',
  medium: 'bg-amber-100 text-amber-900 ring-1 ring-amber-200/80',
  low: 'bg-brand/10 text-brand ring-1 ring-brand/15',
};

/** Ops glance queue — no-shows, pending SMS, follow-ups. */
export function RiskQueue({ className, heading, items, onAction }: RiskQueueProps) {
  return (
    <section
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.45rem)] border border-border-subtle bg-card shadow-[var(--shadow-ui)]',
        className
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-brand)_10%,transparent),transparent)]"
      />
      <div className="relative flex items-center justify-between border-b border-border-subtle px-5 py-4">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">{heading}</h2>
        <span className="rounded-full bg-[color-mix(in_srgb,var(--color-brand)_10%,var(--color-background))] px-2 py-0.5 font-mono text-[11px] text-brand">
          {items.length} open
        </span>
      </div>
      <MotionStagger className="relative divide-y divide-border-subtle">
        {items.map((item) => (
          <MotionStaggerItem key={item.id}>
            <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-[0.12em] uppercase',
                      severityTone[item.severity]
                    )}
                  >
                    {item.severity}
                  </span>
                  <h3 className="truncate text-sm font-medium text-foreground">{item.title}</h3>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted">{item.detail}</p>
              </div>
              {item.actionLabel ? (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="shrink-0"
                  onClick={() => onAction?.(item.id)}
                >
                  {item.actionLabel}
                </Button>
              ) : null}
            </div>
          </MotionStaggerItem>
        ))}
      </MotionStagger>
    </section>
  );
}
