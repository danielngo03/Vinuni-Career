"use client";

import { useTranslations } from "next-intl";
import { StatusBadge } from "@/components/ui";
import {
  SCORECARD_RECOMMENDATIONS,
  type ScorecardListResult,
  type ScorecardRecommendation,
} from "@/lib/api";
import { RECOMMENDATION_TONE } from "./utils";

export function AggregateView({
  data,
  criterionLabel,
  recommendationLabel,
}: {
  data: ScorecardListResult;
  criterionLabel: (key: string, serverLabel?: string | null) => string;
  recommendationLabel: (rec: ScorecardRecommendation) => string;
}) {
  const t = useTranslations("scorecards");
  const agg = data.aggregate;
  const others = data.scorecards;

  const recEntries = SCORECARD_RECOMMENDATIONS.map((rec) => ({
    rec,
    count: agg.recommendation_summary[rec] ?? 0,
  })).filter((e) => e.count > 0);

  const criterionEntries = Object.entries(agg.by_criterion);

  return (
    <div className="rounded-xl border border-white/60 bg-white/72 p-3.5 backdrop-blur-sm">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        {t("aggregateTitle")}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <span className="text-sm text-[var(--text-secondary)]">
          {agg.avg_overall != null
            ? t("avgOverall", { score: agg.avg_overall.toFixed(1) })
            : t("avgOverallNone")}
        </span>
        {recEntries.length > 0 && (
          <span className="flex flex-wrap gap-1.5">
            {recEntries.map(({ rec, count }) => (
              <span
                key={rec}
                className="inline-flex items-center gap-1 rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]"
              >
                {recommendationLabel(rec)}: {count}
              </span>
            ))}
          </span>
        )}
      </div>

      {criterionEntries.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-1.5">
          {criterionEntries.map(([key, avg]) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-lg bg-white/80 px-2.5 py-1.5"
            >
              <dt className="truncate text-xs text-[var(--text-secondary)]">
                {criterionLabel(key)}
              </dt>
              <dd className="ml-2 shrink-0 text-sm font-bold text-[var(--text-primary)]">
                {avg.toFixed(1)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {others.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-[var(--text-muted)]">
            {t("otherReviewers", { count: others.length })}
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {others.map((sc) => (
              <li
                key={sc.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/80 px-2.5 py-1.5"
              >
                <span className="text-xs text-[var(--text-secondary)]">
                  {sc.overall_score != null
                    ? t("overall", { score: sc.overall_score.toFixed(1) })
                    : t("reviewerNoScore")}
                </span>
                <StatusBadge
                  tone={
                    RECOMMENDATION_TONE[
                      sc.recommendation as ScorecardRecommendation
                    ] ?? "info"
                  }
                >
                  {recommendationLabel(
                    sc.recommendation as ScorecardRecommendation,
                  )}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
