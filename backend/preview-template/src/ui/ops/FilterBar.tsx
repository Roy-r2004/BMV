import * as React from 'react';

import { Input } from '../core/Input';
import { cn } from '../lib/cn';

export interface FilterBarFilter {
  id: string;
  label: string;
  active?: boolean;
  onSelect?: () => void;
  /** Accepted as an alias for onSelect since generated pages commonly use onClick. */
  onClick?: () => void;
}

export interface FilterBarProps {
  searchPlaceholder: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  filters?: FilterBarFilter[];
  actions?: React.ReactNode;
  className?: string;
}

export function FilterBar({
  actions,
  className,
  filters = [],
  onSearchChange,
  searchPlaceholder,
  searchValue,
}: FilterBarProps) {
  return (
    <div className={cn('flex flex-col gap-3 rounded-[var(--radius-ui)] border border-border-subtle bg-card p-3 sm:flex-row sm:items-center', className)}>
      <div className="min-w-0 flex-1">
        <label className="sr-only" htmlFor="ops-filter-search">
          Search
        </label>
        <Input
          id="ops-filter-search"
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(event) => onSearchChange?.(event.target.value)}
          aria-label={searchPlaceholder}
        />
      </div>
      {filters.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {filters.map((filter) => (
            <button
              key={filter.id}
              type="button"
              onClick={filter.onSelect ?? filter.onClick}
              className={cn(
                'rounded-full border px-3 py-1.5 text-xs font-semibold',
                filter.active
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border-subtle bg-background text-muted hover:text-foreground'
              )}
            >
              {filter.label}
            </button>
          ))}
        </div>
      ) : null}
      {actions}
    </div>
  );
}
