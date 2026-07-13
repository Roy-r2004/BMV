import * as React from 'react';

import { cn } from '../lib/cn';

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ action, className, description, title }: EmptyStateProps) {
  return (
    <div className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-dashed border-border-subtle bg-card px-6 py-14 text-center', className)}>
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {description ? <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">{description}</p> : null}
      {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
    </div>
  );
}
