"use client";

import { useTranslations } from "next-intl";
import { ArrowRight, Crown } from "@phosphor-icons/react";
import type { CvTemplate } from "@/lib/api";

export function TemplateShelf({
  templates,
  canCreate,
  limitHint,
  onSelect,
}: {
  templates: CvTemplate[];
  canCreate: boolean;
  limitHint?: string;
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
        {templates.map((tpl) => (
          <li key={tpl.id} className="shrink-0 snap-start">
            <button
              type="button"
              onClick={() => onSelect(tpl.id)}
              disabled={!canCreate}
              title={!canCreate ? limitHint : undefined}
              className="group flex w-[152px] flex-col overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] text-left shadow-sm outline-none transition-all hover:border-[var(--brand-primary)]/50 hover:shadow-[0_8px_26px_rgba(11,34,57,0.12)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {/* Faux A4 document thumbnail */}
              <span
                aria-hidden
                className="relative block aspect-[210/297] w-full overflow-hidden bg-white"
                style={
                  tpl.preview_url
                    ? {
                        backgroundImage: `url(${tpl.preview_url})`,
                        backgroundSize: "cover",
                        backgroundPosition: "top center",
                      }
                    : undefined
                }
              >
                {!tpl.preview_url && (
                  <span className="block h-full p-3">
                    <span className="block h-1.5 w-2/3 rounded-full bg-[var(--brand-primary)]" />
                    <span className="mt-1 block h-1 w-1/3 rounded-full bg-[var(--gray-200)]" />
                    <span className="mt-3 block h-px w-full bg-[var(--gray-200)]" />
                    <span className="mt-2 block space-y-1">
                      {[0, 1, 2, 3, 4].map((n) => (
                        <span
                          key={n}
                          className="block h-1 rounded-full bg-[var(--gray-100)]"
                          style={{ width: `${[90, 75, 85, 60, 80][n]}%` }}
                        />
                      ))}
                    </span>
                  </span>
                )}
                {tpl.is_premium && (
                  <span className="absolute right-1.5 top-1.5 inline-flex items-center gap-1 rounded bg-[var(--amber-100)] px-1.5 py-0.5 text-[10px] font-bold uppercase text-[var(--amber-700)]">
                    <Crown aria-hidden weight="fill" className="size-3" />
                    {t("create.premium")}
                  </span>
                )}
              </span>
              <span className="flex items-center justify-between gap-1 border-t border-[var(--border-default)] px-2.5 py-2">
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
        ))}
      </ul>
    </section>
  );
}
