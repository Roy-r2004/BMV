import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: React.ReactNode;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, id, label, ...props }, ref) => {
    const autoId = React.useId();
    const inputId = id || autoId;
    return (
      <label htmlFor={inputId} className={cn('inline-flex items-center gap-2 text-sm text-slate-700', className)}>
        <input
          ref={ref}
          id={inputId}
          type="checkbox"
          className="h-4 w-4 rounded border-slate-300 text-brand focus:ring-brand/30"
          {...props}
        />
        {label ? <span>{label}</span> : null}
      </label>
    );
  }
);

Checkbox.displayName = 'Checkbox';

export default Checkbox;
