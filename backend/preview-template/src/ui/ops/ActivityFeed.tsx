import * as React from 'react';

import { cn } from '../lib/cn';

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

export function ActivityFeed({ className, heading = 'Activity', items }: ActivityFeedProps) {
  return (
    <section className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-6 shadow-sm', className)}>
      <h3 className="text-base font-semibold text-foreground">{heading}</h3>
      <ul className="mt-5 space-y-4">
        {items.map((item) => (
          <li key={item.id} className="border-t border-border-subtle pt-4 first:border-t-0 first:pt-0">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-foreground">{item.title}</p>
              <time className="shrink-0 text-xs text-muted">{item.time}</time>
            </div>
            <p className="mt-1 text-sm leading-6 text-muted">{item.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
