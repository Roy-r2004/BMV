import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface PageHeaderProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageHeader({ actions, className, description, title, ...props }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between', className)} {...props}>
      <div className="min-w-0">
        <h1 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h1>
        {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div> : null}
    </div>
  );
}
