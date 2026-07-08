import type { Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export type StateKind = "empty" | "error" | "permission" | "auth" | "offline";

export interface EmptyStateProps {
  kind?: StateKind;
  icon?: Icon;
  title: string;
  description?: string;
  /** Primary action (e.g. retry, log in). Rendered as-is. */
  action?: React.ReactNode;
  className?: string;
}

const ICON_TONE: Record<StateKind, string> = {
  empty: "text-[var(--text-muted)] bg-[var(--bg-muted)]",
  error: "icon-chip-danger",
  permission: "icon-chip-warning",
  auth: "icon-chip-primary",
  offline: "icon-chip-neutral",
};

/**
 * Unified non-data state. Every data surface must render one of these for
 * loading/empty/error/permission cases (UI_QUALITY_BAR.md, frontend rules).
 */
export function EmptyState({
  kind = "empty",
  icon: IconCmp,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border-strong)]/60 bg-[var(--surface-card)]/60 px-6 py-12 text-center",
        className,
      )}
    >
      {IconCmp && (
        <span
          className={cn(
            "mb-4 flex size-12 items-center justify-center rounded-2xl",
            ICON_TONE[kind],
          )}
        >
          <IconCmp aria-hidden weight="duotone" className="size-6" />
        </span>
      )}
      <h3 className="text-base font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-[var(--text-secondary)]">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
