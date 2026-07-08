"use client";

import { cn } from "@/lib/utils";
import {
  analyzeColumns,
  shouldRenderBars,
  type ColumnAlign,
  type ColumnStat,
  type ParsedTable,
} from "./markdown-table";

/** Column alignment: explicit separator alignment wins, else numeric → right. */
function resolveAlign(explicit: ColumnAlign, stat: ColumnStat | undefined): ColumnAlign {
  if (explicit) return explicit;
  if (stat?.numeric) return "right";
  return "left";
}

function alignClass(align: ColumnAlign): string {
  if (align === "right") return "text-right";
  if (align === "center") return "text-center";
  return "text-left";
}

/**
 * Render a parsed table as a clean v9 Monochrome `<table>`. Fully-numeric
 * columns get a subtle inline bar (ink fill on a muted track) scaled to the
 * column max, giving a lightweight "column chart" feel inline. The wrapper
 * scrolls horizontally so wide tables never overflow the message column.
 *
 * Shared by the assistant markdown-table renderer and the structured
 * `analyze_attachment` tables so both look identical.
 */
export function DataTable({
  table,
  caption,
}: {
  table: ParsedTable;
  caption?: string;
}) {
  const stats = analyzeColumns(table);

  return (
    <div className="my-1 overflow-x-auto rounded-lg border border-[var(--border-default)]">
      <table className="w-full border-collapse text-xs text-[var(--text-primary)]">
        {caption ? (
          <caption className="px-2.5 pt-2 pb-1 text-left text-[11px] font-semibold text-[var(--text-secondary)]">
            {caption}
          </caption>
        ) : null}
        <thead>
          <tr>
            {table.headers.map((header, c) => (
              <th
                key={c}
                scope="col"
                className={cn(
                  "whitespace-nowrap border-b border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]",
                  alignClass(resolveAlign(table.aligns[c] ?? null, stats[c])),
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r} className={r % 2 === 1 ? "bg-[var(--bg-subtle)]/50" : undefined}>
              {table.headers.map((_, c) => {
                const stat = stats[c];
                const align = resolveAlign(table.aligns[c] ?? null, stat);
                const cell = row[c] ?? "";
                const value = stat?.values[r] ?? null;
                const withBar =
                  stat !== undefined && shouldRenderBars(stat) && value !== null;
                const pct =
                  withBar && stat && value !== null && value > 0
                    ? Math.max(3, (value / stat.max) * 100)
                    : 0;
                return (
                  <td
                    key={c}
                    className={cn(
                      "border-t border-[var(--border-subtle)] px-2.5 py-1.5 align-middle",
                      alignClass(align),
                      align === "right" ? "tabular-nums" : undefined,
                    )}
                  >
                    <span>{cell}</span>
                    {withBar && (
                      <span
                        aria-hidden
                        className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
                      >
                        <span
                          className="block h-full rounded-full bg-[var(--text-primary)]/70"
                          style={{ width: `${pct}%` }}
                        />
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
