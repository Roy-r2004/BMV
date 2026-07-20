import * as React from 'react';

import { AnimeReveal, AnimeStagger, AnimeStaggerItem } from '../motion';
import { Badge } from '../core/Badge';
import { Button } from '../core/Button';
import { cn } from '../lib/cn';

export type ScheduleItem = {
  id: string;
  name: string;
  description?: string;
  duration?: string;
  level?: string;
  day?: string;
  status?: string;
  href?: string;
};

export type ScheduleRailProps = {
  heading?: string;
  description?: string;
  items: ScheduleItem[];
  className?: string;
  /** When true, show level / day / availability filters. */
  filterable?: boolean;
};

function statusLabel(status?: string) {
  const s = (status || 'Open').toLowerCase();
  if (s.includes('full') || s.includes('wait')) return 'Waitlist';
  return 'Open';
}

/**
 * Editorial class/service schedule — numbered rows, not white card grids.
 */
export function ScheduleRail({
  className,
  description,
  filterable = true,
  heading = 'Upcoming sessions',
  items,
}: ScheduleRailProps) {
  const [level, setLevel] = React.useState('All');
  const [day, setDay] = React.useState('All');
  const [status, setStatus] = React.useState('All');

  const levels = React.useMemo(() => {
    const set = new Set(items.map((i) => i.level).filter(Boolean) as string[]);
    return ['All', ...Array.from(set)];
  }, [items]);

  const days = React.useMemo(() => {
    const set = new Set(items.map((i) => i.day).filter(Boolean) as string[]);
    return ['All', ...Array.from(set)];
  }, [items]);

  const filtered = items.filter((item) => {
    const levelOk = level === 'All' || item.level === level;
    const dayOk = day === 'All' || item.day === day;
    const label = statusLabel(item.status);
    const statusOk =
      status === 'All' ||
      (status === 'Open' && label === 'Open') ||
      (status === 'Waitlist' && label === 'Waitlist');
    return levelOk && dayOk && statusOk;
  });

  const selectClass =
    'h-10 rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 text-sm text-foreground outline-none focus:border-brand/40 focus:ring-4 focus:ring-ring/15';

  return (
    <section
      id="classes-list"
      data-schedule-rail=""
      className={cn('relative isolate px-6 py-20 sm:px-10 lg:px-12 lg:py-28', className)}
    >
      <div className="mx-auto max-w-[92rem]">
        <AnimeReveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-brand">Schedule</p>
          <h2 className="mt-4 max-w-3xl font-display text-[clamp(2.4rem,5vw,4rem)] leading-[0.95] tracking-[-0.03em] text-foreground">
            {heading}
          </h2>
          {description ? (
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted">{description}</p>
          ) : null}
        </AnimeReveal>

        {filterable ? (
          <div className="mt-10 flex flex-wrap gap-3">
            <label className="sr-only" htmlFor="schedule-level">
              Level
            </label>
            <select
              id="schedule-level"
              className={selectClass}
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            >
              {levels.map((opt) => (
                <option key={opt} value={opt}>
                  {opt === 'All' ? 'All levels' : opt}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor="schedule-day">
              Day
            </label>
            <select
              id="schedule-day"
              className={selectClass}
              value={day}
              onChange={(e) => setDay(e.target.value)}
            >
              {days.map((opt) => (
                <option key={opt} value={opt}>
                  {opt === 'All' ? 'All days' : opt}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor="schedule-status">
              Availability
            </label>
            <select
              id="schedule-status"
              className={selectClass}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="All">All availability</option>
              <option value="Open">Open</option>
              <option value="Waitlist">Waitlist</option>
            </select>
          </div>
        ) : null}

        <AnimeStagger className="mt-12 border-t border-foreground/12" role="list">
          {filtered.map((item, index) => {
            const waitlisted = statusLabel(item.status) === 'Waitlist';
            const href = item.href || `/classes/${item.id}`;
            return (
              <AnimeStaggerItem key={item.id} role="listitem">
                <article className="grid gap-4 border-b border-foreground/12 py-8 md:grid-cols-[4.5rem_1.2fr_0.9fr_auto] md:items-center md:gap-8">
                  <p className="font-mono text-sm font-semibold tracking-[0.16em] text-muted">
                    {String(index + 1).padStart(2, '0')}
                  </p>
                  <div>
                    <h3 className="font-display text-[clamp(1.35rem,2.2vw,1.85rem)] tracking-tight text-foreground">
                      {item.name}
                    </h3>
                    {item.description ? (
                      <p className="mt-2 max-w-xl text-sm leading-6 text-muted">{item.description}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
                    {item.day ? <span>{item.day}</span> : null}
                    {item.day && item.duration ? <span aria-hidden>·</span> : null}
                    {item.duration ? <span>{item.duration}</span> : null}
                    {item.level ? (
                      <Badge variant="secondary" className="ml-1">
                        {item.level}
                      </Badge>
                    ) : null}
                    <Badge variant={waitlisted ? 'outline' : 'default'}>
                      {statusLabel(item.status)}
                    </Badge>
                  </div>
                  <Button
                    href={waitlisted ? '/waitlist-confirmation' : href}
                    variant={waitlisted ? 'outline' : 'default'}
                    className="w-full md:w-auto"
                  >
                    {waitlisted ? 'Join waitlist' : 'View details'}
                  </Button>
                </article>
              </AnimeStaggerItem>
            );
          })}
        </AnimeStagger>

        {filtered.length === 0 ? (
          <p className="mt-10 text-sm text-muted">No sessions match those filters — try clearing one.</p>
        ) : null}
      </div>
    </section>
  );
}
