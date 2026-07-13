import * as React from 'react';

import { cn } from '../lib/cn';

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ actions, className, description, title }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div> : null}
    </div>
  );
}
