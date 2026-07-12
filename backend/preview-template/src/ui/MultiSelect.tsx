import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface MultiSelectOption {
  value: string;
  label: React.ReactNode;
}

export interface MultiSelectProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> {
  options: MultiSelectOption[];
  value?: string[];
  onChange?: (value: string[]) => void;
  placeholder?: string;
}

export function MultiSelect({
  className,
  onChange,
  options,
  placeholder = 'Select options',
  value = [],
  ...props
}: MultiSelectProps) {
  const selected = new Set(value);

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white p-3 shadow-sm', className)} {...props}>
      <p className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-400">{placeholder}</p>
      <div className="flex flex-col gap-2">
        {options.map((option) => {
          const checked = selected.has(option.value);
          return (
            <label key={option.value} className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => {
                  const next = new Set(selected);
                  if (checked) next.delete(option.value);
                  else next.add(option.value);
                  onChange?.(Array.from(next));
                }}
                className="h-4 w-4 rounded border-slate-300 text-brand focus:ring-brand/30"
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

export default MultiSelect;
