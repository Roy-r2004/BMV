import * as React from 'react';
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';

import { cn } from '../lib/cn';

export interface DataTableColumn {
  key?: string;
  /** Accepted as an alias for key (generated pages often use accessor). */
  accessor?: string;
  header: string;
  /**
   * The contract: `(row) => …`. The first parameter is the whole row.
   *
   * `invokeRender` below also recovers `({ row }) => …` and `(value) => …` by
   * calling and checking the result, but this declaration is what the model is
   * shown and what generated pages should write.
   *
   * Deliberately ONE signature. A union of two call shapes gives TypeScript no
   * contextual type to infer from, so every generated `render: (row) => …` became
   * "Parameter 'row' implicitly has an 'any' type" — eight of request 46's sixteen
   * type errors, all from this one declaration.
   */
  render?: (row: any, fullRow?: Record<string, unknown>) => React.ReactNode;
}

export interface DataTableProps {
  columns: DataTableColumn[];
  rows: Array<Record<string, unknown>>;
  emptyMessage?: string;
  onRowSelect?: (row: Record<string, unknown>) => void;
  className?: string;
}

function cellContent(value: unknown): React.ReactNode {
  if (value == null || value === '') return '';
  if (React.isValidElement(value)) return value;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  // Never render raw objects — React #31. Prefer label/name/title, else hide.
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const pick = record.label ?? record.name ?? record.title ?? record.text ?? record.value;
    if (pick != null && (typeof pick === 'string' || typeof pick === 'number')) return String(pick);
    return '';
  }
  return String(value);
}

/** `String(someRow)`. A renderer handed the wrong argument produces this. */
const OBJECT_STRINGIFICATION = /\[object [A-Za-z]+\]/;

/**
 * Host elements whose entire content is a URL they were handed. A missing one
 * is a visible defect — the broken-image glyph, or a link that goes nowhere —
 * not a styling choice, so these are the only childless tags judged empty.
 */
const URL_ELEMENTS: Record<string, string> = {
  a: 'href',
  audio: 'src',
  embed: 'src',
  iframe: 'src',
  img: 'src',
  source: 'src',
  track: 'src',
  video: 'src',
};

/**
 * Does this node put anything on the page?
 *
 * The reason request 71 shipped five `src=null, alt=null, naturalWidth=0`
 * thumbnails is that `invokeRender` treated "the renderer returned truthy JSX"
 * as "the renderer worked". `<img src={undefined} alt={undefined} />` is truthy
 * JSX. So the wrong-argument branch below could never be reached by the `??`
 * fallback, and the failure was silent by construction.
 *
 * Deliberately conservative in one direction: a *custom* component with no
 * children is assumed to render something, because we cannot see inside it.
 * Only intrinsic elements are judged, and only on evidence.
 */
function hasRenderableContent(node: React.ReactNode, depth = 0): boolean {
  if (node == null || node === false || node === true || node === '') return false;
  if (depth > 8) return true;
  if (Array.isArray(node)) {
    return node.some((child) => hasRenderableContent(child as React.ReactNode, depth + 1));
  }
  if (typeof node === 'string' || typeof node === 'number') {
    const text = String(node).trim();
    return text !== '' && !OBJECT_STRINGIFICATION.test(text);
  }
  if (React.isValidElement(node)) {
    const props = (node.props ?? {}) as Record<string, unknown>;
    // Children were supplied and every one of them is empty: the element is a
    // wrapper around nothing, whatever its type.
    if ('children' in props) {
      return hasRenderableContent(props.children as React.ReactNode, depth + 1);
    }
    const urlProp = typeof node.type === 'string' ? URL_ELEMENTS[node.type] : undefined;
    if (urlProp) return String(props[urlProp] ?? '').trim() !== '';
    return true;
  }
  // A bare object where a node belongs is React #31 waiting to happen, and it is
  // the signature of a value formatter that was handed the whole row.
  return false;
}

/** The cell context TanStack hands its own `cell`, for `({ row }) => …`. */
function cellContext(row: Record<string, unknown>, value: unknown) {
  return { row, value, getValue: () => value };
}

/**
 * Call a column's `render` with the argument it actually meant.
 *
 * **Arity is not the signal.** Every shape below declares one parameter, and
 * they mean three different things. Measured over the 71 `render:` call sites in
 * the generated workspaces under `/app/data/preview-apps`:
 *
 * | shape                              | sites | means      |
 * |------------------------------------|------:|------------|
 * | `(row) => …`, `(row: T) => …`      |    51 | the row    |
 * | `({ painting, imageUrl }) => …`    |     2 | the row    |
 * | `({ row }) => …`                   |    14 | a context  |
 * | `(value: unknown) => …`            |     2 | the value  |
 * | `() => …`                          |     2 | —          |
 * | `(value, row) => …`                |     0 | —          |
 *
 * So the rule is: **try the declared contract first, then judge the result.**
 * The row is first because the type declaration above says the first parameter
 * is the row, that is what the model is shown, and it is 53 of 71 sites. The
 * two-argument value-first shape the old comment claimed codegen emits does not
 * appear in a single workspace; the declared `(row, fullRow?)` is honoured
 * instead, and the legacy order is kept as a second attempt.
 *
 * What makes trying the row first *safe* rather than a coin flip is
 * `hasRenderableContent`: the two ways a renderer fails on the wrong argument —
 * reading fields off a primitive, and stringifying an object — both produce a
 * result this can see. Request 71's `(row) => <img src={row.image} />` given the
 * string produced an element with no `src`; `(value) => String(value)` given the
 * row produces `[object Object]`. Neither reads as success any more.
 */
function invokeRender(
  render: DataTableColumn['render'],
  row: Record<string, unknown>,
  value: unknown
): React.ReactNode {
  if (!render) return cellContent(value);
  const fn = render as (...args: unknown[]) => React.ReactNode;
  const attempts: Array<() => React.ReactNode> =
    fn.length >= 2
      ? [() => fn(row, row), () => fn(value, row)]
      : [() => fn(row), () => fn(cellContext(row, value)), () => fn(value)];

  let structureWithoutContent = false;
  for (const attempt of attempts) {
    let out: React.ReactNode;
    try {
      out = attempt();
    } catch {
      continue;
    }
    if (hasRenderableContent(out)) return out;
    // `=> null` is a deliberately empty cell and says nothing is wrong. An
    // element that came back holding nothing is the defect worth reporting.
    if (out != null && out !== false) structureWithoutContent = true;
  }
  if (structureWithoutContent) {
    console.warn(
      '[DataTable] a column renderer returned an element with no content for every ' +
        'call shape; showing the raw cell value instead.'
    );
  }
  return cellContent(value);
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
      columns.map((column, index) => {
        const key = column.key ?? column.accessor ?? `col-${index}`;
        return {
          id: key,
          accessorKey: key,
          header: column.header,
          cell: (info) =>
            column.render
              ? invokeRender(column.render, info.row.original, info.getValue())
              : cellContent(info.getValue()),
        };
      }),
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
          <thead className="bg-[color-mix(in_srgb,var(--color-brand)_6%,var(--color-background))] text-[11px] tracking-[0.08em] text-muted uppercase">
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
                    'border-t border-border-subtle text-foreground hover:bg-[color-mix(in_srgb,var(--color-brand)_5%,var(--color-background))]',
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
