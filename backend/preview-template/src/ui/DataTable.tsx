import * as React from 'react';

import { Card } from './Card.js';
import { cn } from '../lib/cn.js';

type DataTableRow = Record<string, React.ReactNode>;

export interface DataTableColumn<Row extends DataTableRow> {
  key: keyof Row | string;
  header: React.ReactNode;
  render?: (row: Row, rowIndex: number) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
  headerClassName?: string;
}

export interface DataTableProps<Row extends DataTableRow> extends React.HTMLAttributes<HTMLDivElement> {
  columns: DataTableColumn<Row>[];
  rows: Row[];
  rowKey?: (row: Row, rowIndex: number) => React.Key;
  emptyMessage?: React.ReactNode;
}

const alignmentClasses = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
} as const;

export function DataTable<Row extends DataTableRow>({
  className,
  columns,
  emptyMessage = 'No records to display.',
  rowKey,
  rows,
  ...props
}: DataTableProps<Row>) {
  return (
    <Card className={cn('overflow-hidden rounded-3xl border-slate-200 bg-white shadow-sm', className)} {...props}>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-slate-50/80">
            <tr>
              {columns.map((column) => (
                <th
                  key={String(column.key)}
                  className={cn(
                    'px-5 py-3.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400',
                    alignmentClasses[column.align ?? 'left'],
                    column.headerClassName
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row, rowIndex) => (
                <tr key={rowKey?.(row, rowIndex) ?? rowIndex} className="border-t border-slate-200/80">
                  {columns.map((column) => (
                    <td
                      key={String(column.key)}
                      className={cn(
                        'px-5 py-4 text-sm text-slate-700',
                        alignmentClasses[column.align ?? 'left'],
                        column.className
                      )}
                    >
                      {column.render ? column.render(row, rowIndex) : row[String(column.key)]}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="px-5 py-12 text-center text-sm text-slate-500">
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default DataTable;
