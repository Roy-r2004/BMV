import * as React from 'react';

import { MotionDiv, fadeUp } from './Motion.js';
import { cn } from '../lib/cn.js';

type ActionObject = {
  label?: React.ReactNode;
  href?: string;
  to?: string;
  path?: string;
  onClick?: React.MouseEventHandler<HTMLAnchorElement>;
};

export interface MarketingHeroProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode;
  headline: React.ReactNode;
  subcopy: React.ReactNode;
  /** React node OR AI-friendly `{ label, href }` object */
  primaryAction?: React.ReactNode | ActionObject;
  secondaryAction?: React.ReactNode | ActionObject;
  media?: React.ReactNode;
  contentClassName?: string;
  mediaClassName?: string;
}

function isActionObject(value: unknown): value is ActionObject {
  return (
    !!value &&
    typeof value === 'object' &&
    !React.isValidElement(value) &&
    ('label' in (value as object) || 'href' in (value as object) || 'to' in (value as object))
  );
}

function renderAction(action: React.ReactNode | ActionObject | undefined, tone: 'primary' | 'secondary') {
  if (action == null || action === false) return null;
  if (React.isValidElement(action) || typeof action === 'string' || typeof action === 'number') {
    return action;
  }
  if (!isActionObject(action)) return null;
  const href = action.href || action.to || action.path || '#';
  const className =
    tone === 'primary'
      ? 'inline-flex h-11 items-center justify-center rounded-xl bg-brand px-5 text-sm font-semibold text-white shadow-lg shadow-brand/25 transition hover:brightness-110'
      : 'inline-flex h-11 items-center justify-center rounded-xl border border-white/20 bg-white/5 px-5 text-sm font-semibold text-white transition hover:bg-white/10';
  return (
    <a href={href} onClick={action.onClick} className={className}>
      {action.label ?? 'Continue'}
    </a>
  );
}

export function MarketingHero({
  className,
  contentClassName,
  eyebrow,
  headline,
  media,
  mediaClassName,
  primaryAction,
  secondaryAction,
  subcopy,
  ...props
}: MarketingHeroProps) {
  const primary = renderAction(primaryAction, 'primary');
  const secondary = renderAction(secondaryAction, 'secondary');

  return (
    <section className={cn('relative isolate overflow-hidden px-6 py-20 lg:px-10 lg:py-28', className)} {...props}>
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 -z-10 h-96 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.16),transparent_55%)]"
      />
      <div className="mx-auto grid w-full max-w-7xl items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)] lg:gap-16">
        <MotionDiv
          initial="hidden"
          animate="show"
          variants={fadeUp}
          className={cn('max-w-3xl', contentClassName)}
        >
          {eyebrow ? (
            <div className="inline-flex items-center rounded-full border border-white/12 bg-white/6 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-white/70">
              {eyebrow}
            </div>
          ) : null}
          <h1 className="mt-6 text-5xl font-semibold tracking-[-0.04em] text-balance text-white sm:text-6xl lg:text-7xl">
            {headline}
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-white/70 sm:text-xl">{subcopy}</p>
          {(primary || secondary) && (
            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              {primary}
              {secondary}
            </div>
          )}
        </MotionDiv>

        {media ? (
          <MotionDiv
            initial="hidden"
            animate="show"
            variants={fadeUp}
            transition={{ delay: 0.08 }}
            className={cn(
              'relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/8 p-3 shadow-2xl shadow-brand/10 backdrop-blur-sm',
              mediaClassName
            )}
          >
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.22),transparent_38%)]" aria-hidden="true" />
            <div className="relative overflow-hidden rounded-[1.5rem] border border-white/10 bg-slate-900/70">{media}</div>
          </MotionDiv>
        ) : null}
      </div>
    </section>
  );
}

export default MarketingHero;
