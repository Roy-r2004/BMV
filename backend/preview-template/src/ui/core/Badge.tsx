import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../lib/cn';

const badgeVariants = cva('inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold', {
  variants: {
    variant: {
      default: 'border-brand/20 bg-brand/10 text-brand-dark',
      secondary: 'border-border-subtle bg-background text-foreground',
      outline: 'border-border-subtle bg-transparent text-muted',
      destructive: 'border-accent/20 bg-accent/10 text-accent',
    },
  },
  defaultVariants: { variant: 'default' },
});

export interface BadgeProps extends VariantProps<typeof badgeVariants> {
  children: React.ReactNode;
  className?: string;
}

export function Badge({ children, className, variant = 'default' }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)}>{children}</span>;
}
