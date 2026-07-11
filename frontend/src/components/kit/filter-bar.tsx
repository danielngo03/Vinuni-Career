"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * FilterBar — the standard toolbar above a DataTable/list: a search field on
 * the left, arbitrary filter controls (selects/popovers/segmented), and a
 * right-aligned actions slot. Uses the system input focus treatment.
 */
export function FilterBar({
  search,
  children,
  actions,
  className,
}: {
  /** Optional search field. Controlled. */
  search?: {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    ariaLabel?: string;
  };
  /** Filter controls (Select / Popover / SegmentedControl). */
  children?: React.ReactNode;
  /** Right-aligned actions (primary CTA, export, view toggle). */
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {search && (
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            strokeWidth={1.8}
          />
          <input
            type="search"
            value={search.value}
            onChange={(e) => search.onChange(e.target.value)}
            placeholder={search.placeholder}
            aria-label={search.ariaLabel ?? search.placeholder}
            className="h-9 w-full rounded-lg border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground"
          />
        </div>
      )}
      {children}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  );
}
