import * as React from 'react';

import { cn } from '../lib/cn';

export interface CardProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  className?: string;
}

export function Card({ children, className, description, title }: CardProps) {
  return (
    <div className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-6 shadow-sm', className)}>
      {title ? <h3 className="text-base font-semibold text-foreground">{title}</h3> : null}
      {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
      <div className={title || description ? 'mt-4' : undefined}>{children}</div>
    </div>
  );
}
