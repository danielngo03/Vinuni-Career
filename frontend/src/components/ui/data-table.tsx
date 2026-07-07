"use client";

import { Skeleton } from "./skeleton";
import { EmptyState, type EmptyStateProps } from "./empty-state";
import { cn } from "@/lib/utils";

export interface Column<Row> {
  key: string;
  header: string;
  /** Cell renderer. Defaults to String(row[key]). */
  cell?: (row: Row) => React.ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}

export interface DataTableProps<Row> {
  columns: Column<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  loading?: boolean;
  /** Number of skeleton rows while loading. */
  skeletonRows?: number;
  /** Shown when rows is empty and not loading. */
  empty?: EmptyStateProps;
  caption?: string;
  className?: string;
}

const ALIGN = {
  left: "text-left",
  right: "text-right",
  center: "text-center",
} as const;

/**
 * Lightweight, accessible table with built-in loading and empty states.
 * Stable column layout (UI_QUALITY_BAR.md). For server-side sorting/large
 * datasets, TanStack Table can be layered on later phases.
 */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  loading = false,
  skeletonRows = 5,
  empty,
  caption,
  className,
}: DataTableProps<Row>) {
  if (!loading && rows.length === 0 && empty) {
    return <EmptyState {...empty} />;
  }

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)]",
        className,
      )}
    >
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-[var(--border-default)] bg-[var(--bg-subtle)]">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "px-3.5 py-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]",
                  ALIGN[col.align ?? "left"],
                  col.className,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr
                  key={`sk-${i}`}
                  className="border-b border-[var(--border-subtle)] last:border-0"
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-3.5 py-2.5">
                      <Skeleton className="h-4 w-full max-w-[160px]" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={getRowId(row)}
                  className="border-b border-[var(--border-subtle)] align-middle transition-colors last:border-0 hover:bg-[var(--surface-hover)]"
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-3.5 py-2.5 text-[var(--text-primary)]",
                        ALIGN[col.align ?? "left"],
                        col.className,
                      )}
                    >
                      {col.cell
                        ? col.cell(row)
                        : String(
                            (row as Record<string, unknown>)[col.key] ?? "",
                          )}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
