import * as React from 'react';

import { UiIcon } from '../../components/UiIcons';
import { cn } from '../lib/cn';
import { formatRelative } from '../lib/format';

function safeRelative(value: string): string {
  try {
    return formatRelative(value);
  } catch {
    return value;
  }
}

export interface ActivityFeedItem {
  id?: string;
  title?: string;
  /**
   * Text, or a node: request 46's dashboard composed a `<Badge>` and a link into
   * the detail line. A node is rendered as given; anything else is coerced to text
   * through the alias chain below.
   */
  detail?: React.ReactNode;
  time?: string;
  /** A leading glyph for the row, in place of the title's initial. */
  icon?: React.ReactNode;
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
  // A node is content, not a string to be coerced: `asText` would drop it.
  const detail: React.ReactNode = React.isValidElement(item.detail)
    ? item.detail
    : asText(item.detail) ||
      (asText(item.description) !== title ? asText(item.description) : '') ||
      (asText(item.message) !== title ? asText(item.message) : '');
  const time =
    asText(item.time) || asText(item.timestamp) || asText(item.createdAt) || asText(item.at);
  return {
    id: asText(item.id) || `activity-${index}`,
    title: title || 'Activity update',
    detail,
    time,
    icon: item.icon,
  };
}

/** Tremor-inspired activity list — dense timeline, tolerant of AI prop aliases. */
export function ActivityFeed({ className, heading = 'Activity', items }: ActivityFeedProps) {
  const rows = (items || []).map(normalizeItem);

  return (
    <section
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.55rem)] border border-border-subtle bg-card p-5 shadow-[var(--shadow-ui)]',
        className
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-brand)_8%,transparent),transparent)]"
      />
      <div className="relative flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight text-foreground">{heading}</h3>
        <span className="inline-flex items-center gap-1 rounded-full bg-[color-mix(in_srgb,var(--color-brand)_10%,var(--color-background))] px-2 py-1 text-[11px] font-medium text-brand">
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
                ? safeRelative(item.time)
                : item.time || '';
            const initial = (item.title || 'A').trim().charAt(0).toUpperCase();
            return (
              <li
                key={item.id}
                className="relative flex gap-3 border-t border-[#eef2f7] py-3.5 first:border-t-0 first:pt-0"
              >
                <span
                  className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-brand)_12%,white)] text-xs font-semibold text-brand"
                  aria-hidden="true"
                >
                  {item.icon ?? initial}
                </span>
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
