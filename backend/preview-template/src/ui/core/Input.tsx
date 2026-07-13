import * as React from 'react';

import { cn } from '../lib/cn';

export interface InputProps {
  type?: string;
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  name?: string;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  className?: string;
  'aria-label'?: string;
}

export function Input({ className, type = 'text', ...props }: InputProps) {
  return (
    <input
      type={type}
      className={cn(
        'flex h-10 w-full rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 text-sm text-foreground shadow-sm outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-[color:var(--color-ring)]/15 disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  );
}
