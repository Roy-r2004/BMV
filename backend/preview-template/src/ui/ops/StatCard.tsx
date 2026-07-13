import * as React from 'react';

import { cn } from '../lib/cn';

export interface StatCardProps {
  label: string;
  value: string;
  delta?: string;
  hint?: string;
  className?: string;
}

export function StatCard({ className, delta, hint, label, value }: StatCardProps) {
  return (
    <div className={cn('rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card p-6 shadow-sm', className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted">{label}</p>
        {delta ? <span className="rounded-full bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand-dark">{delta}</span> : null}
      </div>
      <p className="mt-4 text-3xl font-semibold tracking-tight text-foreground">{value}</p>
      {hint ? <p className="mt-2 text-sm leading-6 text-muted">{hint}</p> : null}
    </div>
  );
}
