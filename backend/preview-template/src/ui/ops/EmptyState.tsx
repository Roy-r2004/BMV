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
    <div
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-dashed border-border-subtle bg-[color-mix(in_srgb,var(--color-brand)_4%,var(--color-card))] px-6 py-14 text-center shadow-[var(--shadow-ui)]',
        className
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-80"
        style={{
          background:
            'radial-gradient(50% 60% at 50% 0%, color-mix(in srgb, var(--color-brand) 14%, transparent), transparent 70%)',
        }}
      />
      <div className="relative">
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-brand/50" />
        <h3 className="font-display text-lg font-semibold tracking-tight text-foreground">{title}</h3>
        {description ? <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">{description}</p> : null}
        {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
}
