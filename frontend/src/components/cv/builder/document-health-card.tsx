"use client";

import { useTranslations } from "next-intl";
import { LightbulbFilament, Sparkle } from "@phosphor-icons/react";
import { isSectionEmpty } from "@/lib/cv/sections";
import type { CvSection } from "@/lib/api";

/** Derives AI-styled "document health" hints purely from the live section state. */
function buildHealthInsights(
  sections: CvSection[],
  t: ReturnType<typeof import("next-intl").useTranslations>,
): string[] {
  const visible = sections.filter((s) => s.is_visible);
  const emptySections = visible.filter((s) => isSectionEmpty(s));
  const hasSummary = sections.some(
    (s) => s.section_type === "summary" || s.section_type === "objective",
  );
  const insights: string[] = [];
  if (visible.length === 0) {
    insights.push(t("builder.healthNoVisible"));
  } else {
    if (emptySections.length > 0) {
      insights.push(t("builder.healthEmptySections", { count: emptySections.length }));
    }
    if (!hasSummary && visible.length >= 2) {
      insights.push(t("builder.healthNoSummary"));
    }
    if (visible.length < 3 && emptySections.length === 0) {
      insights.push(t("builder.healthFewSections"));
    }
    if (visible.length >= 4 && emptySections.length === 0) {
      insights.push(t("builder.healthLooksGood"));
    }
  }
  return insights;
}

/** AI Document Health panel — shown when there is at least one live insight. */
export function DocumentHealthCard({ sections }: { sections: CvSection[] }) {
  const t = useTranslations("cv");
  if (sections.length === 0) return null;

  const insights = buildHealthInsights(sections, t);
  if (insights.length === 0) return null;

  return (
    <div className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] p-3.5 backdrop-blur-xl">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
        </span>
        <span className="text-xs font-bold uppercase tracking-wide text-[var(--ai-accent)]">
          {t("builder.healthTitle")}
        </span>
      </div>
      <ul className="space-y-1.5">
        {insights.map((insight, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
            <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
            {insight}
          </li>
        ))}
      </ul>
    </div>
  );
}
