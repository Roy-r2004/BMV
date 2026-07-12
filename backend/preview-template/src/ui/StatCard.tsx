import * as React from 'react';

import { Card, CardContent } from './Card.js';
import { cn } from '../lib/cn.js';

const deltaToneClasses = {
  neutral: 'bg-slate-100 text-slate-600',
  positive: 'bg-emerald-50 text-emerald-700',
  negative: 'bg-rose-50 text-rose-700',
} as const;

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  label: React.ReactNode;
  value: React.ReactNode;
  delta?: React.ReactNode;
  deltaTone?: keyof typeof deltaToneClasses;
  hint?: React.ReactNode;
}

export function StatCard({
  className,
  delta,
  deltaTone = 'neutral',
  hint,
  label,
  value,
  ...props
}: StatCardProps) {
  return (
    <Card className={cn('rounded-3xl border-slate-200 bg-white shadow-sm', className)} {...props}>
      <CardContent className="flex h-full flex-col gap-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <p className="text-sm font-medium text-slate-500">{label}</p>
          {delta ? (
            <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', deltaToneClasses[deltaTone])}>
              {delta}
            </span>
          ) : null}
        </div>
        <div>
          <p className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">{value}</p>
          {hint ? <p className="mt-2 text-sm leading-6 text-slate-500">{hint}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default StatCard;
