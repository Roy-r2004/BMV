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
  high: 'bg-[#f3e4e0] text-[#8a3a2e]',
  medium: 'bg-[#f3efe4] text-[#7a6440]',
  low: 'bg-brand/10 text-brand',
};

/** Ops glance queue — no-shows, pending SMS, follow-ups. */
export function RiskQueue({ className, heading, items, onAction }: RiskQueueProps) {
  return (
    <section className={cn('border border-border-subtle bg-card', className)}>
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">{heading}</h2>
        <span className="font-mono text-[11px] text-muted">{items.length} open</span>
      </div>
      <MotionStagger className="divide-y divide-border-subtle">
        {items.map((item) => (
          <MotionStaggerItem key={item.id}>
            <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn('px-2 py-0.5 text-[10px] font-semibold tracking-[0.12em] uppercase', severityTone[item.severity])}>
                    {item.severity}
                  </span>
                  <h3 className="truncate text-sm font-medium text-foreground">{item.title}</h3>
                </div>
                <p className="mt-1 text-sm leading-6 text-muted">{item.detail}</p>
              </div>
              {item.actionLabel ? (
                <Button type="button" size="sm" variant="secondary" className="shrink-0" onClick={() => onAction?.(item.id)}>
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
