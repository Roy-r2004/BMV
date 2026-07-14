import * as React from 'react';

import { cn } from '../lib/cn';

export interface InputProps {
  type?: string;
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  checked?: boolean;
  defaultChecked?: boolean;
  id?: string;
  name?: string;
  /** Renders a stacked field label above the input. */
  label?: string;
  /** Renders inline validation text below the input. */
  error?: string;
  min?: number | string;
  max?: number | string;
  step?: number | string;
  /** 'textarea' renders a multi-line field; pair with `rows`. */
  as?: 'input' | 'textarea';
  rows?: number;
  onChange?: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  className?: string;
  'aria-label'?: string;
}

const fieldClasses =
  'flex w-full rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3 text-sm text-foreground shadow-sm outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-[color:var(--color-ring)]/15 disabled:cursor-not-allowed disabled:opacity-50';

export function Input({ as = 'input', className, error, id, label, rows, type = 'text', ...props }: InputProps) {
  const generatedId = React.useId();
  const inputId = id ?? (label ? generatedId : undefined);
  const isCheckable = type === 'checkbox' || type === 'radio';
  const field =
    as === 'textarea' ? (
      <textarea
        id={inputId}
        rows={rows ?? 4}
        className={cn(fieldClasses, 'min-h-20 py-2', error && 'border-red-400 focus:border-red-400', className)}
        aria-invalid={error ? true : undefined}
        {...props}
      />
    ) : (
      <input
        id={inputId}
        type={type}
        className={cn(
          isCheckable
            ? 'h-4 w-4 shrink-0 rounded border-border-subtle accent-[var(--color-brand)]'
            : cn(fieldClasses, 'h-10'),
          error && 'border-red-400 focus:border-red-400',
          className
        )}
        aria-invalid={error ? true : undefined}
        {...props}
      />
    );
  if (!label && !error) {
    return field;
  }
  if (isCheckable) {
    return (
      <label className="flex items-center gap-2 text-sm text-foreground">
        {field}
        {label}
      </label>
    );
  }
  return (
    <div className="space-y-1.5">
      {label ? (
        <label htmlFor={inputId} className="block text-sm font-medium text-foreground">
          {label}
        </label>
      ) : null}
      {field}
      {error ? <p className="text-xs text-red-500">{error}</p> : null}
    </div>
  );
}
