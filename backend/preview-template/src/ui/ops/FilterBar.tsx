import * as React from 'react';

import { Input } from '../core/Input';
import { cn } from '../lib/cn';

export interface FilterBarFilter {
  id?: string;
  /** Accepted as an alias for id (generated pages often use value). */
  value?: string;
  label: string;
  active?: boolean;
  onSelect?: () => void;
  /** Accepted as an alias for onSelect since generated pages commonly use onClick. */
  onClick?: () => void;
}

export interface FilterBarAction {
  label: string;
  onClick?: () => void;
}

export interface FilterBarProps {
  searchPlaceholder: string;
  searchValue?: string;
  onSearchChange?: ((value: string) => void) | ((event: { target: { value: string } }) => void);
  /** Descriptor chips, or React nodes (codegen often passes Input/Select elements). */
  filters?: Array<FilterBarFilter | React.ReactNode>;
  /** React nodes or descriptor objects — AI pages often pass `{ label, onClick }[]`. */
  actions?: React.ReactNode | FilterBarAction[];
  className?: string;
}

function isActionDescriptorList(value: unknown): value is FilterBarAction[] {
  return (
    Array.isArray(value) &&
    value.every((item) => typeof item === 'object' && item !== null && 'label' in item && !React.isValidElement(item))
  );
}

export function FilterBar({
  actions,
  className,
  filters = [],
  onSearchChange,
  searchPlaceholder,
  searchValue,
}: FilterBarProps) {
  const resolvedActions = isActionDescriptorList(actions) ? (
    <div className="flex flex-wrap gap-2">
      {actions.map((action, index) => (
        <button
          key={`${action.label}-${index}`}
          type="button"
          onClick={action.onClick}
          className="rounded-full border border-border-subtle bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-card"
        >
          {action.label}
        </button>
      ))}
    </div>
  ) : (
    (actions as React.ReactNode)
  );

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
          onChange={(event) => {
            if (!onSearchChange) return;
            // Support both `(value: string)` and mistaken `(e) => setX(e.target.value)`.
            try {
              (onSearchChange as (value: string) => void)(event.target.value);
            } catch {
              (onSearchChange as (event: { target: { value: string } }) => void)(event);
            }
          }}
          aria-label={searchPlaceholder}
        />
      </div>
      {filters.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          {filters.map((filter, index) => {
            if (React.isValidElement(filter)) {
              return <React.Fragment key={filter.key ?? `filter-node-${index}`}>{filter}</React.Fragment>;
            }
            const chip = filter as FilterBarFilter;
            const key = chip.id ?? chip.value ?? `${chip.label}-${index}`;
            return (
              <button
                key={key}
                type="button"
                onClick={chip.onSelect ?? chip.onClick}
                className={cn(
                  'rounded-full border px-3 py-1.5 text-xs font-semibold',
                  chip.active
                    ? 'border-foreground bg-foreground text-background'
                    : 'border-border-subtle bg-background text-muted hover:text-foreground'
                )}
              >
                {chip.label}
              </button>
            );
          })}
        </div>
      ) : null}
      {resolvedActions}
    </div>
  );
}
