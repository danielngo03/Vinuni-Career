import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * PageHeader (v10) — the standard surface header: optional breadcrumb slot,
 * title, subtitle, an inline meta row (small stats/status), and a right-aligned
 * actions cluster (⌘K, filters, primary CTA). Backward-compatible with the
 * legacy `{ title, description?, actions? }` API — `description` is an alias
 * for `subtitle`.
 */
export function PageHeader({
  title,
  subtitle,
  description,
  meta,
  breadcrumb,
  actions,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Legacy alias for {@link subtitle}. */
  description?: React.ReactNode;
  /** Inline metadata row under the title (counts, status chips, updated-at). */
  meta?: React.ReactNode;
  /** Optional breadcrumb node rendered above the title. */
  breadcrumb?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  const sub = subtitle ?? description;
  return (
    <div
      className={cn(
        "mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {breadcrumb && <div className="mb-1.5">{breadcrumb}</div>}
        <h1 className="type-h1 text-balance text-foreground">{title}</h1>
        {sub && <p className="type-small mt-1 max-w-2xl text-muted-foreground">{sub}</p>}
        {meta && (
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[0.8125rem] text-muted-foreground">
            {meta}
          </div>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
