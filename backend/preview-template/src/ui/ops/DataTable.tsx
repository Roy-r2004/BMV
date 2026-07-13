import * as React from 'react';
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';

import { cn } from '../lib/cn';

export interface DataTableColumn {
  key: string;
  header: string;
  render?: (row: Record<string, unknown>) => React.ReactNode;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  rows: Array<Record<string, unknown>>;
  emptyMessage?: string;
  onRowSelect?: (row: Record<string, unknown>) => void;
  className?: string;
}

export function DataTable({
  className,
  columns,
  emptyMessage = 'No records to display.',
  onRowSelect,
  rows,
}: DataTableProps) {
  const columnDefs = React.useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      columns.map((column) => ({
        accessorKey: column.key,
        header: column.header,
        cell: (info) =>
          column.render ? column.render(info.row.original) : String(info.getValue() ?? ''),
      })),
    [columns]
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className={cn('overflow-hidden border border-border-subtle bg-card', className)}>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-left text-[13px]">
          <thead className="bg-[#eef2f4] text-[11px] tracking-[0.08em] text-muted uppercase">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} scope="col" className="px-3 py-2.5 font-semibold">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td className="px-3 py-10 text-center text-muted" colSpan={columns.length}>
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    'border-t border-border-subtle text-foreground hover:bg-[#f7f9fa]',
                    onRowSelect && 'cursor-pointer'
                  )}
                  onClick={onRowSelect ? () => onRowSelect(row.original) : undefined}
                  onKeyDown={
                    onRowSelect
                      ? (event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            onRowSelect(row.original);
                          }
                        }
                      : undefined
                  }
                  tabIndex={onRowSelect ? 0 : undefined}
                  role={onRowSelect ? 'button' : undefined}
                >
                  {row.getVisibleCells().map((cell, i) => (
                    <td
                      key={cell.id}
                      className={cn('px-3 py-2.5', i === 0 && 'font-mono text-[12px] tabular-nums text-muted')}
                    >
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
