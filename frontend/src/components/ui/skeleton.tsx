import { cn } from "@/lib/utils";

/** Loading placeholder. Uses stable dimensions (UI_QUALITY_BAR.md). */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={cn(
        "animate-skeleton rounded-lg bg-[var(--bg-muted)]",
        className,
      )}
      {...props}
    >
      <span className="sr-only">Loading</span>
    </div>
  );
}

/** Common card skeleton for dashboard tiles. */
export function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-sm)]">
      <Skeleton className="h-8 w-8 rounded-xl" />
      <Skeleton className="mt-4 h-9 w-24" />
      <Skeleton className="mt-2 h-4 w-32" />
    </div>
  );
}
