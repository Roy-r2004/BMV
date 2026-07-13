import * as React from 'react';
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';

import { cn } from '../lib/cn';

export interface DataTableColumn {
  key: string;
  header: string;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  rows: Array<Record<string, string>>;
  emptyMessage?: string;
  className?: string;
}

export function DataTable({
  className,
  columns,
  emptyMessage = 'No records to display.',
  rows,
}: DataTableProps) {
  const columnDefs = React.useMemo<ColumnDef<Record<string, string>>[]>(
    () =>
      columns.map((column) => ({
        accessorKey: column.key,
        header: column.header,
        cell: (info) => String(info.getValue() ?? ''),
      })),
    [columns]
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className={cn('overflow-hidden rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card shadow-sm', className)}>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-sm">
          <thead className="bg-background text-muted">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} scope="col" className="px-4 py-3 font-medium">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td className="px-4 py-10 text-center text-muted" colSpan={columns.length}>
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-t border-border-subtle text-foreground">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
