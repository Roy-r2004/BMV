import * as React from 'react';

import { cn } from '../lib/cn.js';

const badgeTones = {
  neutral: 'border-slate-200 bg-slate-50 text-slate-700',
  brand: 'border-brand/15 bg-brand/10 text-brand-dark',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  danger: 'border-rose-200 bg-rose-50 text-rose-700',
} as const;

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: keyof typeof badgeTones;
}

export function Badge({ className, tone = 'neutral', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold tracking-wide',
        badgeTones[tone],
        className
      )}
      {...props}
    />
  );
}
