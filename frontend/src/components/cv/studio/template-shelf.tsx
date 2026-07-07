"use client";

import { useTranslations } from "next-intl";
import { ArrowRight } from "@phosphor-icons/react";
import type { CvTemplate } from "@/lib/api";
import { CvDocument, SAMPLE_CV, themeForTemplate } from "@/components/cv/render";

/** Scale so the 794px A4 page fits the 152px card thumbnail (152 / 794 ≈ 0.19). */
const THUMB_SCALE = 152 / 794;

export function TemplateShelf({
  templates,
  onSelect,
}: {
  templates: CvTemplate[];
  onSelect: (templateId: string) => void;
}) {
  const t = useTranslations("cv");
  if (templates.length === 0) return null;

  return (
    <section aria-label={t("list.shelfTitle")} className="mb-6">
      <div className="mb-2.5 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {t("list.shelfTitle")}
          </h2>
          <p className="text-xs text-[var(--text-secondary)]">
            {t("list.shelfHint")}
          </p>
        </div>
      </div>
      <ul className="flex snap-x gap-3 overflow-x-auto pb-2">
        {templates.map((tpl) => {
          const theme = themeForTemplate(tpl);
          return (
            <li key={tpl.id} className="shrink-0 snap-start">
              <button
                type="button"
                onClick={() => onSelect(tpl.id)}
                className="group flex w-[152px] flex-col overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] text-left shadow-sm outline-none transition-all hover:border-[var(--brand-primary)]/50 hover:shadow-[0_8px_26px_rgba(0,0,0,0.12)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
              >
                {/* Live A4 document thumbnail — the same renderer as the preview. */}
                <span
                  aria-hidden
                  className="relative block aspect-[210/297] w-full overflow-hidden border-b border-[var(--border-subtle)] bg-white"
                >
                  <CvDocument
                    content={SAMPLE_CV}
                    theme={theme}
                    scale={THUMB_SCALE}
                    ariaLabel={t("create.templatePreviewLabel", { name: tpl.name })}
                  />
                </span>
                <span className="flex items-center justify-between gap-1 px-2.5 py-2">
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold text-[var(--text-primary)]">
                      {tpl.name}
                    </span>
                    <span className="block truncate text-[11px] text-[var(--text-muted)]">
                      {tpl.category}
                    </span>
                  </span>
                  <ArrowRight
                    aria-hidden
                    weight="bold"
                    className="size-3.5 shrink-0 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--brand-primary)]"
                  />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
