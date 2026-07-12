import * as React from 'react';

import { Search } from 'lucide-react';

import { Card, CardContent } from './Card.js';
import { Input } from './Input.js';
import { cn } from '../lib/cn.js';

export interface FilterBarProps extends React.HTMLAttributes<HTMLDivElement> {
  searchValue?: string;
  onSearchValueChange?: (value: string) => void;
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  actions?: React.ReactNode;
}

export function FilterBar({
  actions,
  className,
  filters,
  onSearchValueChange,
  searchPlaceholder = 'Search',
  searchValue,
  ...props
}: FilterBarProps) {
  return (
    <Card className={cn('rounded-3xl border-slate-200 bg-white shadow-sm', className)} {...props}>
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={searchValue}
              onChange={(event) => onSearchValueChange?.(event.target.value)}
              placeholder={searchPlaceholder}
              className="pl-9"
            />
          </div>
          {filters ? <div className="flex flex-1 flex-wrap items-center gap-3">{filters}</div> : null}
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div> : null}
        </div>
      </CardContent>
    </Card>
  );
}
