import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { cn } from '../lib/cn';
import { formatRelative } from '../lib/format';

export interface ActivityFeedItem {
  id?: string;
  title?: string;
  detail?: string;
  time?: string;
  /** Common AI aliases — normalized at render time. */
  text?: string;
  message?: string;
  description?: string;
  label?: string;
  timestamp?: string;
  createdAt?: string;
  at?: string;
}

export interface ActivityFeedProps {
  items: ActivityFeedItem[];
  heading?: string;
  className?: string;
}

function asText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return '';
}

function normalizeItem(item: ActivityFeedItem, index: number) {
  const title =
    asText(item.title) ||
    asText(item.text) ||
    asText(item.message) ||
    asText(item.label) ||
    asText(item.description);
  const detail =
    asText(item.detail) ||
    (asText(item.description) !== title ? asText(item.description) : '') ||
    (asText(item.message) !== title ? asText(item.message) : '');
  const time =
    asText(item.time) || asText(item.timestamp) || asText(item.createdAt) || asText(item.at);
  return {
    id: asText(item.id) || `activity-${index}`,
    title: title || 'Activity update',
    detail,
    time,
  };
}

/** Tremor-inspired activity list — dense timeline, tolerant of AI prop aliases. */
export function ActivityFeed({ className, heading = 'Activity', items }: ActivityFeedProps) {
  const rows = (items || []).map(normalizeItem);

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
        {rows.length === 0 ? (
          <li className="py-3 text-sm text-muted">No recent activity.</li>
        ) : (
          rows.map((item) => {
            const relative =
              item.time && (item.time.includes('T') || item.time.includes('-'))
                ? formatRelative(item.time)
                : item.time || '';
            return (
              <li
                key={item.id}
                className="relative flex gap-3 border-t border-border-subtle py-3.5 first:border-t-0 first:pt-0"
              >
                <span className="mt-1.5 flex h-2 w-2 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium text-foreground">{item.title}</p>
                    {relative ? (
                      <time className="shrink-0 text-[11px] tabular-nums text-muted" dateTime={item.time}>
                        {relative}
                      </time>
                    ) : null}
                  </div>
                  {item.detail ? (
                    <p className="mt-1 text-xs leading-5 text-muted">{item.detail}</p>
                  ) : null}
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
