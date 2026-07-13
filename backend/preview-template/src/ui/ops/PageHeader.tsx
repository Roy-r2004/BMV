import * as React from 'react';

import { cn } from '../lib/cn';

export interface PageHeaderAction {
  label: string;
  onClick?: () => void;
  variant?: 'primary' | 'secondary';
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode | PageHeaderAction[];
  className?: string;
}

function isActionDescriptorList(value: unknown): value is PageHeaderAction[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'object' && item !== null && 'label' in item);
}

export function PageHeader({ actions, className, description, title }: PageHeaderProps) {
  const resolvedActions = isActionDescriptorList(actions) ? (
    <>
      {actions.map((action, index) => (
        <button
          key={`${action.label}-${index}`}
          type="button"
          onClick={action.onClick}
          className={cn(
            'rounded-full px-4 py-2 text-sm font-semibold transition-colors',
            action.variant === 'secondary'
              ? 'border border-border-subtle bg-background text-foreground hover:bg-[#f7f9fa]'
              : 'bg-foreground text-background hover:opacity-90'
          )}
        >
          {action.label}
        </button>
      ))}
    </>
  ) : (
    (actions as React.ReactNode)
  );

  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        <h1 className="font-display text-[clamp(2.4rem,4vw,3.4rem)] font-medium italic tracking-[-0.035em] text-foreground">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{description}</p> : null}
      </div>
      {resolvedActions ? <div className="flex shrink-0 flex-wrap items-center gap-3">{resolvedActions}</div> : null}
    </div>
  );
}
