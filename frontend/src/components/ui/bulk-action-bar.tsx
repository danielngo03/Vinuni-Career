"use client";

import { X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export interface BulkActionBarProps {
  count: number;
  onClear: () => void;
  /** Localized selection label, e.g. "3 đã chọn" / "3 selected". */
  selectionLabel: string;
  /** Localized aria-label for the clear button. */
  clearLabel: string;
  /** Action buttons (Button components) for the selection. */
  children: React.ReactNode;
  className?: string;
}

/**
 * Floating, sticky action bar shown when rows are selected. One shared surface
 * for bulk workflows (candidates, moderation, users) instead of per-feature
 * bars. Renders nothing at zero selection; text is caller-localized.
 */
export function BulkActionBar({
  count,
  onClear,
  selectionLabel,
  clearLabel,
  children,
  className,
}: BulkActionBarProps) {
  if (count === 0) return null;
  return (
    <div
      role="region"
      aria-label={selectionLabel}
      className={cn(
        "sticky bottom-4 z-30 mx-auto flex w-fit max-w-[calc(100vw-2rem)] flex-wrap items-center gap-3 rounded-full border border-[var(--border-strong)] bg-[var(--surface-card)] px-3 py-2 pl-4 shadow-[var(--shadow-lg)]",
        className,
      )}
    >
      <span className="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
        {selectionLabel}
      </span>
      <span aria-hidden className="h-4 w-px bg-[var(--border-default)]" />
      <div className="flex flex-wrap items-center gap-1.5">{children}</div>
      <button
        type="button"
        onClick={onClear}
        aria-label={clearLabel}
        className="ml-1 rounded-full p-1.5 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <X aria-hidden weight="bold" className="size-4" />
      </button>
    </div>
  );
}
