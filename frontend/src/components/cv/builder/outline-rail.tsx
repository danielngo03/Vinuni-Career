"use client";

import { useTranslations } from "next-intl";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeSlash,
  ListBullets,
  Plus,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { CvSection } from "@/lib/api";

/**
 * Left document-outline rail (desktop lg+). A navigable, keyboard-accessible
 * mirror of the section list: click to select/scroll a section on the canvas,
 * move it up/down, and show/hide it. This is the required keyboard path for
 * reorder + visibility (the on-canvas affordances are the pointer enhancement).
 */
export function OutlineRail({
  sections,
  visibleCount,
  activeTemplateName,
  addingSection,
  selectedSectionId,
  sectionLabel,
  onSelect,
  onMove,
  onToggleVisible,
  onAddSection,
}: {
  sections: CvSection[];
  visibleCount: number;
  activeTemplateName: string | null;
  addingSection: boolean;
  selectedSectionId: string | null;
  sectionLabel: (s: CvSection) => string;
  onSelect: (id: string) => void;
  onMove: (id: string, direction: "up" | "down") => void;
  onToggleVisible: (id: string, visible: boolean) => void;
  onAddSection: () => void;
}) {
  const t = useTranslations("cv");

  return (
    <aside
      aria-label={t("builder.outlineTitle")}
      className="hidden lg:sticky lg:top-4 lg:block"
    >
      <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] shadow-[var(--shadow-sm)] backdrop-blur-md">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--glass-border)] px-3.5 py-2.5">
          <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-[var(--text-secondary)]">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-primary shadow-sm">
              <ListBullets aria-hidden weight="duotone" className="size-3 text-white" />
            </span>
            {t("builder.outlineTitle")}
          </span>
          <span className="rounded-full bg-[var(--glass-surface-light)] px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
            {visibleCount}/{sections.length}
          </span>
        </div>
        <nav className="max-h-[calc(100vh-14rem)] overflow-y-auto p-1.5">
          <ul className="space-y-0.5">
            {sections.map((s, i) => {
              const selected = selectedSectionId === s.id;
              return (
                <li
                  key={s.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-lg px-1.5 py-1 transition-colors",
                    selected
                      ? "bg-[var(--brand-primary)]/10"
                      : "hover:bg-[var(--glass-surface-light)]",
                  )}
                >
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onSelect(s.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-0.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                  >
                    <span className="w-4 shrink-0 text-center text-[11px] font-semibold tabular-nums text-[var(--text-muted)]">
                      {i + 1}
                    </span>
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate text-sm font-medium",
                        selected
                          ? "text-[var(--brand-primary)]"
                          : s.is_visible
                            ? "text-[var(--text-primary)]"
                            : "text-[var(--text-muted)]",
                      )}
                    >
                      {sectionLabel(s)}
                    </span>
                  </button>
                  <span className="flex shrink-0 items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 aria-[current]:opacity-100">
                    <button
                      type="button"
                      aria-label={t("editor.moveUp")}
                      disabled={i === 0}
                      onClick={() => onMove(s.id, "up")}
                      className="rounded p-0.5 text-[var(--text-muted)] outline-none hover:text-[var(--text-primary)] disabled:opacity-25 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                    >
                      <ArrowUp aria-hidden weight="bold" className="size-3" />
                    </button>
                    <button
                      type="button"
                      aria-label={t("editor.moveDown")}
                      disabled={i === sections.length - 1}
                      onClick={() => onMove(s.id, "down")}
                      className="rounded p-0.5 text-[var(--text-muted)] outline-none hover:text-[var(--text-primary)] disabled:opacity-25 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                    >
                      <ArrowDown aria-hidden weight="bold" className="size-3" />
                    </button>
                    <button
                      type="button"
                      aria-pressed={s.is_visible}
                      aria-label={s.is_visible ? t("editor.hide") : t("editor.show")}
                      onClick={() => onToggleVisible(s.id, !s.is_visible)}
                      className="rounded p-0.5 text-[var(--text-muted)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                    >
                      {s.is_visible ? (
                        <Eye aria-hidden weight="duotone" className="size-3.5" />
                      ) : (
                        <EyeSlash aria-hidden weight="duotone" className="size-3.5" />
                      )}
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="border-t border-[var(--glass-border)] p-2.5">
          <Button
            variant="ghost"
            size="sm"
            fullWidth
            loading={addingSection}
            onClick={onAddSection}
          >
            <Plus aria-hidden weight="bold" className="size-4" />
            {t("builder.addSection")}
          </Button>
          <p className="mt-1.5 px-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {activeTemplateName
              ? t("builder.outlineTemplate", { name: activeTemplateName })
              : t("builder.outlineNoTemplate")}
          </p>
        </div>
      </div>
    </aside>
  );
}
