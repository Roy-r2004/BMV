import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { cn } from '../lib/cn';
import { formatRelative } from '../lib/format';

export interface ActivityFeedItem {
  id: string;
  title: string;
  detail: string;
  time: string;
}

export interface ActivityFeedProps {
  items: ActivityFeedItem[];
  heading?: string;
  className?: string;
}

/** Tremor-inspired activity list — dense timeline, fixed props. */
export function ActivityFeed({ className, heading = 'Activity', items }: ActivityFeedProps) {
  return (
    <section className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-5 shadow-sm', className)}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight text-foreground">{heading}</h3>
        <span className="inline-flex items-center gap-1 text-xs text-muted">
          <UiIcon name="bell" className="h-3.5 w-3.5" />
          Live
        </span>
      </div>
      <ul className="mt-4 space-y-0">
        {items.map((item, index) => {
          const relative =
            item.time && (item.time.includes('T') || item.time.includes('-'))
              ? formatRelative(item.time)
              : item.time || '';
          return (
            <li key={item.id} className="relative flex gap-3 border-t border-border-subtle py-3.5 first:border-t-0 first:pt-0">
              <span className="mt-1.5 flex h-2 w-2 shrink-0 rounded-full bg-brand" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <time className="shrink-0 text-[11px] tabular-nums text-muted" dateTime={item.time}>
                    {relative}
                  </time>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted">{item.detail}</p>
              </div>
              {index === items.length - 1 ? null : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
