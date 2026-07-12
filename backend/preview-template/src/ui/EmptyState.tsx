import * as React from 'react';

import { Card, CardContent } from './Card.js';
import { cn } from '../lib/cn.js';

export interface EmptyStateProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({ action, className, description, icon, title, ...props }: EmptyStateProps) {
  return (
    <Card className={cn('rounded-3xl border-dashed border-slate-300 bg-white', className)} {...props}>
      <CardContent className="flex flex-col items-center px-6 py-12 text-center sm:px-10">
        {icon ? (
          <div className="mb-5 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
            {icon}
          </div>
        ) : null}
        <h3 className="text-xl font-semibold tracking-[-0.02em] text-slate-950">{title}</h3>
        <p className="mt-3 max-w-md text-sm leading-6 text-slate-500">{description}</p>
        {action ? <div className="mt-6">{action}</div> : null}
      </CardContent>
    </Card>
  );
}
