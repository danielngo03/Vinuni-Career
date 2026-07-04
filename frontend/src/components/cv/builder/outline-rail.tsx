"use client";

import { useTranslations } from "next-intl";
import { CaretRight, Eye, EyeSlash, ListBullets, Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { CvSection } from "@/lib/api";

/**
 * Left document-outline rail (desktop xl+). Navigation-only mirror of the
 * section list so the builder reads like a document editor, not a stacked
 * form. Form controls (template/primary) stay single-instance in the editor.
 */
export function OutlineRail({
  sections,
  visibleCount,
  activeTemplateName,
  addingSection,
  sectionLabel,
  onScrollTo,
  onAddSection,
}: {
  sections: CvSection[];
  visibleCount: number;
  activeTemplateName: string | null;
  addingSection: boolean;
  sectionLabel: (s: CvSection) => string;
  onScrollTo: (id: string) => void;
  onAddSection: () => void;
}) {
  const t = useTranslations("cv");

  return (
    <aside
      aria-label={t("builder.outlineTitle")}
      className="hidden xl:sticky xl:top-4 xl:block"
    >
      <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md shadow-[var(--shadow-sm)]">
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
        <nav className="max-h-[calc(100vh-13rem)] overflow-y-auto p-1.5">
          <ul className="space-y-0.5">
            {sections.map((s, i) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onScrollTo(s.id)}
                  className="group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left outline-none transition-colors hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  <span className="w-4 shrink-0 text-center text-[11px] font-semibold tabular-nums text-[var(--text-muted)]">
                    {i + 1}
                  </span>
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-sm font-medium",
                      s.is_visible
                        ? "text-[var(--text-primary)]"
                        : "text-[var(--text-muted)]",
                    )}
                  >
                    {sectionLabel(s)}
                  </span>
                  {s.is_visible ? (
                    <Eye
                      aria-hidden
                      weight="duotone"
                      className="size-3.5 shrink-0 text-[var(--text-muted)]"
                    />
                  ) : (
                    <EyeSlash
                      aria-hidden
                      weight="duotone"
                      className="size-3.5 shrink-0 text-[var(--text-muted)]"
                    />
                  )}
                  <CaretRight
                    aria-hidden
                    weight="bold"
                    className="size-3 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
                  />
                </button>
              </li>
            ))}
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
