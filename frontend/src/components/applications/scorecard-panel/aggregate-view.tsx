"use client";

import { useTranslations } from "next-intl";
import { StatusChip } from "@/components/kit";
import {
  SCORECARD_RECOMMENDATIONS,
  type ScorecardListResult,
  type ScorecardRecommendation,
} from "@/lib/api";
import { RECOMMENDATION_CHIP } from "../chip-tones";

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
    <div className="rounded-lg border border-border bg-[var(--bg-subtle)] p-3.5">
      <p className="type-small font-semibold text-foreground">{t("aggregateTitle")}</p>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <span className="type-small text-muted-foreground">
          {agg.avg_overall != null
            ? t("avgOverall", { score: agg.avg_overall.toFixed(1) })
            : t("avgOverallNone")}
        </span>
        {recEntries.length > 0 && (
          <span className="flex flex-wrap gap-1.5">
            {recEntries.map(({ rec, count }) => (
              <span
                key={rec}
                className="inline-flex items-center gap-1 rounded-full bg-card px-2 py-0.5 type-caption font-medium text-muted-foreground"
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
              className="flex items-center justify-between rounded-md bg-card px-2.5 py-1.5"
            >
              <dt className="truncate type-caption text-muted-foreground">{criterionLabel(key)}</dt>
              <dd className="ml-2 shrink-0 type-small font-bold tabular-nums text-foreground">
                {avg.toFixed(1)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {others.length > 0 && (
        <div className="mt-3">
          <p className="type-caption text-muted-foreground">
            {t("otherReviewers", { count: others.length })}
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {others.map((sc) => (
              <li
                key={sc.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-card px-2.5 py-1.5"
              >
                <span className="type-caption text-muted-foreground">
                  {sc.overall_score != null
                    ? t("overall", { score: sc.overall_score.toFixed(1) })
                    : t("reviewerNoScore")}
                </span>
                <StatusChip tone={RECOMMENDATION_CHIP[sc.recommendation] ?? "neutral"}>
                  {recommendationLabel(sc.recommendation as ScorecardRecommendation)}
                </StatusChip>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
