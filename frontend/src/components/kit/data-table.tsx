"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import {
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowUp, ArrowDown, ChevronsUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

export type { ColumnDef } from "@tanstack/react-table";
import type { RowData } from "@tanstack/react-table";

// Column alignment via `meta: { align }` — augment TanStack's ColumnMeta so the
// DataTable can right-align numeric columns type-safely.
declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    align?: "left" | "right" | "center";
  }
}

export interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  getRowId?: (row: T) => string;
  /** Skeleton rows while loading. */
  loading?: boolean;
  /** Rendered when there is no data (and not loading). */
  empty?: React.ReactNode;
  onRowClick?: (row: T) => void;
  /** Highlight the row matching this id (e.g. the record open in a DetailSheet). */
  activeRowId?: string;
  /** Adds a leading checkbox column + selection state. */
  enableSelection?: boolean;
  /** Renders a bulk-action bar above the table when rows are selected. */
  bulkActions?: (selected: T[], clear: () => void) => React.ReactNode;
  /** Enables client pagination at this page size (omit = no pagination). */
  pageSize?: number;
  /** Controlled global filter string (wire to a FilterBar search). */
  globalFilter?: string;
  initialSort?: SortingState;
  className?: string;
}

/**
 * DataTable — the v10 tabular primitive (TanStack Table). Client sorting,
 * global filtering, optional row selection + bulk-action bar, optional
 * pagination, and honest empty/loading states. Cells are supplied by the
 * caller's `columns` (avatar+name, status chips, inline %-bars, right-aligned
 * tabular numbers). Right-align numeric columns via `meta: { align: "right" }`.
 */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  loading = false,
  empty,
  onRowClick,
  activeRowId,
  enableSelection = false,
  bulkActions,
  pageSize,
  globalFilter,
  initialSort = [],
  className,
}: DataTableProps<T>) {
  const t = useTranslations("common");
  const [sorting, setSorting] = React.useState<SortingState>(initialSort);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});

  const allColumns = React.useMemo<ColumnDef<T, unknown>[]>(() => {
    if (!enableSelection) return columns;
    const selectCol: ColumnDef<T, unknown> = {
      id: "__select",
      enableSorting: false,
      size: 40,
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected()
              ? true
              : table.getIsSomePageRowsSelected()
                ? "indeterminate"
                : false
          }
          onCheckedChange={(v) => table.toggleAllPageRowsSelected(!!v)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(!!v)}
          onClick={(e) => e.stopPropagation()}
          aria-label="Select row"
        />
      ),
    };
    return [selectCol, ...columns];
  }, [columns, enableSelection]);

  const table = useReactTable({
    data,
    columns: allColumns,
    state: { sorting, rowSelection, ...(globalFilter !== undefined ? { globalFilter } : {}) },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getRowId: getRowId ? (row) => getRowId(row) : undefined,
    enableRowSelection: enableSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    ...(pageSize
      ? { getPaginationRowModel: getPaginationRowModel(), initialState: { pagination: { pageSize } } }
      : {}),
  });

  const selectedRows = table.getSelectedRowModel().rows.map((r) => r.original);
  const colCount = allColumns.length;

  function alignClass(meta: unknown): string {
    const align = (meta as { align?: "right" | "center" } | undefined)?.align;
    return align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  }

  return (
    <div className={cn("overflow-hidden rounded-xl border border-border bg-card", className)}>
      {/* Bulk action bar */}
      {enableSelection && selectedRows.length > 0 && bulkActions && (
        <div className="flex items-center gap-3 border-b border-border bg-[var(--bg-subtle)] px-4 py-2.5">
          <span className="text-[0.8125rem] font-semibold text-foreground">
            {t("tableSelected", { count: selectedRows.length })}
          </span>
          <button
            type="button"
            onClick={() => table.resetRowSelection()}
            className="text-[0.8125rem] font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {t("tableClear")}
          </button>
          <div className="ml-auto flex items-center gap-2">
            {bulkActions(selectedRows, () => table.resetRowSelection())}
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-border">
                {hg.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={cn(
                        "whitespace-nowrap bg-[var(--bg-subtle)] px-4 py-2.5 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-muted-foreground",
                        alignClass(header.column.columnDef.meta),
                      )}
                      style={header.getSize() ? { width: header.getSize() } : undefined}
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="inline-flex items-center gap-1 outline-none hover:text-foreground focus-visible:text-foreground"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sorted === "asc" ? (
                            <ArrowUp className="size-3" strokeWidth={2.2} />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="size-3" strokeWidth={2.2} />
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-50" strokeWidth={2} />
                          )}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: colCount }).map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <span className="animate-skeleton block h-4 w-full max-w-[10rem] rounded bg-[var(--bg-muted)]" />
                    </td>
                  ))}
                </tr>
              ))
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="px-4 py-10 text-center">
                  {empty ?? (
                    <span className="text-sm text-muted-foreground">{t("tableNoResults")}</span>
                  )}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const active = activeRowId != null && row.id === activeRowId;
                return (
                  <tr
                    key={row.id}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    className={cn(
                      "transition-colors",
                      onRowClick && "cursor-pointer",
                      active ? "bg-[var(--bg-subtle)]" : "hover:bg-[var(--bg-subtle)]",
                    )}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td
                        key={cell.id}
                        className={cn(
                          "px-4 py-3 align-middle text-foreground",
                          alignClass(cell.column.columnDef.meta),
                        )}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pageSize && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-2.5">
          <span className="type-small text-muted-foreground">
            {t("tablePage", {
              page: table.getState().pagination.pageIndex + 1,
              pages: table.getPageCount(),
            })}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              aria-label={t("tablePrev")}
              className="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="size-4" strokeWidth={1.8} />
            </button>
            <button
              type="button"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              aria-label={t("tableNext")}
              className="inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronRight className="size-4" strokeWidth={1.8} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
