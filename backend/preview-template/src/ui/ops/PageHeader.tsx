import * as React from 'react';

import { AppLink } from '../lib/AppLink';
import { cn } from '../lib/cn';

export interface PageHeaderAction {
  label: string;
  href?: string;
  onClick?: () => void;
  variant?: 'primary' | 'secondary';
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  /** Right-side date / notification / custom meta (soft SaaS header). */
  meta?: React.ReactNode;
  actions?: React.ReactNode | PageHeaderAction[];
  className?: string;
}

function isActionDescriptorList(value: unknown): value is PageHeaderAction[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'object' && item !== null && 'label' in item);
}

function actionClassName(variant?: PageHeaderAction['variant']): string {
  return cn(
    'rounded-full px-4 py-2 text-sm font-semibold transition-colors',
    variant === 'secondary'
      ? 'border border-border-subtle bg-card text-foreground hover:bg-[color-mix(in_srgb,var(--color-brand)_8%,var(--color-background))]'
      : 'bg-brand text-white shadow-[var(--shadow-ui)] hover:opacity-95'
  );
}

export function PageHeader({ actions, className, description, meta, title }: PageHeaderProps) {
  const resolvedActions = isActionDescriptorList(actions) ? (
    <>
      {actions.map((action, index) => {
        const classes = actionClassName(action.variant);
        if (action.href) {
          return (
            <AppLink
              key={`${action.label}-${index}`}
              href={action.href}
              className={classes}
              onClick={action.onClick}
            >
              {action.label}
            </AppLink>
          );
        }
        return (
          <button
            key={`${action.label}-${index}`}
            type="button"
            onClick={action.onClick}
            className={classes}
          >
            {action.label}
          </button>
        );
      })}
    </>
  ) : (
    (actions as React.ReactNode)
  );

  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        <h1 className="font-display text-[clamp(1.75rem,3vw,2.35rem)] font-semibold tracking-[-0.03em] text-foreground">
          {title}
        </h1>
        {description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{description}</p> : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        {meta}
        {resolvedActions}
      </div>
    </div>
  );
}
