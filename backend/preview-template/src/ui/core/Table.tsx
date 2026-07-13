import * as React from 'react';

import { cn } from '../lib/cn';

export interface TableColumn {
  key: string;
  header: string;
}

export interface TableProps {
  columns: TableColumn[];
  rows: Array<Record<string, string>>;
  caption?: string;
  className?: string;
}

/** Simple semantic table. Prefer DataTable on ops pages for sorting density. */
export function Table({ caption, className, columns, rows }: TableProps) {
  return (
    <div className={cn('overflow-x-auto rounded-[var(--radius-ui)] border border-border-subtle bg-card', className)}>
      <table className="min-w-full text-left text-sm">
        {caption ? <caption className="px-4 py-3 text-left text-muted">{caption}</caption> : null}
        <thead className="bg-background text-muted">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="px-4 py-3 font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-border-subtle text-foreground">
              {columns.map((column) => (
                <td key={column.key} className="px-4 py-3">
                  {row[column.key] ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
