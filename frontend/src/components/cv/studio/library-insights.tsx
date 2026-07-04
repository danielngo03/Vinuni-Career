"use client";

import { useTranslations } from "next-intl";
import { LightbulbFilament } from "@phosphor-icons/react";
import type { CvLibraryMeta, CvSummary } from "@/lib/api";

type CvStudioInsightKey =
  | "insightNoPrimary"
  | "insightQuotaFull"
  | "insightQuotaHigh"
  | "insightHasDrafts"
  | "insightUploadImport";

function deriveInsights(
  rows: CvSummary[],
  meta: CvLibraryMeta | null,
): CvStudioInsightKey[] {
  const insights: CvStudioInsightKey[] = [];
  const hasPrimary = rows.some((r) => r.is_primary);
  const hasDrafts = rows.some((r) => r.status === "draft");
  const hasUpload = rows.some(
    (r) => r.source_type === "upload" || r.source_type === "import",
  );
  if (meta && !meta.can_create) insights.push("insightQuotaFull");
  else if (meta && meta.active_cv_limit > 0 && meta.active_cv_used / meta.active_cv_limit >= 0.8)
    insights.push("insightQuotaHigh");
  if (!hasPrimary) insights.push("insightNoPrimary");
  if (hasDrafts) insights.push("insightHasDrafts");
  if (hasUpload) insights.push("insightUploadImport");
  return insights.slice(0, 3);
}

/** CV Library Guidance — deterministic product rules, not AI. */
export function LibraryInsights({
  rows,
  meta,
}: {
  rows: CvSummary[];
  meta: CvLibraryMeta | null;
}) {
  const t = useTranslations("cv");
  const shown = deriveInsights(rows, meta);
  if (shown.length === 0) return null;

  return (
    <section
      aria-label={t("list.aiInsightsTitle")}
      className="mb-4 rounded-[16px] border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_8px_24px_rgba(11,34,57,0.06)]"
    >
      <div className="mb-3 flex items-center gap-2">
        <span className="flex size-6 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--brand-primary)] to-[var(--teal-600)] shadow-sm">
          <LightbulbFilament aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("list.aiInsightsTitle")}
        </p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {shown.map((key) => (
          <li key={key} className="flex items-start gap-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
            <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--brand-primary)]" />
            {t(`list.${key}`)}
          </li>
        ))}
      </ul>
    </section>
  );
}
