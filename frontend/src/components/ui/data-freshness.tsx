"use client";

import { cn } from "@/lib/utils";

export type FreshnessTone = "fresh" | "stale" | "unavailable";

export interface DataFreshnessProps {
  /** fresh = live, stale = data older than the surface's threshold,
   *  unavailable = read model missing / not yet computed. */
  tone?: FreshnessTone;
  /** Localized text, e.g. "Cập nhật 2 phút trước" or "Dữ liệu chưa sẵn sàng". */
  children: React.ReactNode;
  className?: string;
}

/**
 * Honest data-freshness chip for dashboards and read-model-backed metrics
 * (PRODUCT_OPERATING_MODEL §6: "every metric must name its source and
 * stale/error state"). Presentational only — the caller supplies localized
 * copy and decides the threshold. A dot + text carries meaning without relying
 * on color alone (the copy already states the state).
 */
export function DataFreshness({ tone = "fresh", children, className }: DataFreshnessProps) {
  const dot =
    tone === "unavailable"
      ? "bg-[var(--text-muted)]"
      : tone === "stale"
        ? "bg-[var(--color-warning)]"
        : "bg-[var(--color-success)]";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)]",
        className,
      )}
    >
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", dot)} />
      {children}
    </span>
  );
}
