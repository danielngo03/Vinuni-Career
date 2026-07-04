"use client";

import { Plus, type Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";

/**
 * Single-level container for a profile child collection (no card-in-card).
 * Header holds the title + an "Add" action; the body renders the list or an
 * inline empty hint.
 */
export function SectionShell({
  title,
  description,
  icon: IconCmp,
  iconGradient,
  addLabel,
  onAdd,
  children,
}: {
  title: string;
  description?: string;
  /** Optional phosphor icon in a gradient square before the title. */
  icon?: Icon;
  iconGradient?: string;
  addLabel: string;
  onAdd: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-6 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {IconCmp && iconGradient && (
            <span
              className={cn(
                "flex size-8 shrink-0 items-center justify-center rounded-xl shadow-sm",
                iconGradient,
              )}
            >
              <IconCmp aria-hidden weight="duotone" className="size-4 text-white" />
            </span>
          )}
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            {description && (
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {description}
              </p>
            )}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={onAdd}>
          <Plus aria-hidden weight="bold" className="size-4" />
          {addLabel}
        </Button>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

/** Row action buttons (edit + delete) shared by list items. */
export function RowActions({
  editLabel,
  deleteLabel,
  onEdit,
  onDelete,
}: {
  editLabel: string;
  deleteLabel: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <Button variant="ghost" size="sm" onClick={onEdit}>
        {editLabel}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-[var(--brand-red)] hover:bg-[var(--red-50)] hover:text-[var(--brand-red)]"
        onClick={onDelete}
      >
        {deleteLabel}
      </Button>
    </div>
  );
}

export function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-xl border border-dashed border-[var(--glass-border)] px-4 py-6 text-center text-sm text-[var(--text-muted)]">
      {children}
    </p>
  );
}
