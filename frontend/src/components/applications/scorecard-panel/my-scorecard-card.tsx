"use client";

import { useTranslations } from "next-intl";
import { PencilSimple, Trash } from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import { useScorecardLabels } from "@/lib/applications/labels";
import type { Scorecard, ScorecardRecommendation } from "@/lib/api";
import { RECOMMENDATION_TONE } from "./utils";

export function MyScorecardCard({
  mine,
  canSubmit,
  onEdit,
  onWithdraw,
}: {
  mine: Scorecard;
  canSubmit: boolean;
  onEdit: () => void;
  onWithdraw: () => void;
}) {
  const t = useTranslations("scorecards");
  const labels = useScorecardLabels();
  const recTone =
    RECOMMENDATION_TONE[mine.recommendation as ScorecardRecommendation] ??
    "info";

  return (
    <div className="rounded-xl border border-[var(--brand-primary)]/30 bg-[var(--brand-primary)]/5 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("yourEvaluation")}
        </p>
        <StatusBadge tone={recTone}>
          {labels.recommendation(mine.recommendation, mine.recommendation_label)}
        </StatusBadge>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2">
        {mine.scores.map((s) => (
          <div
            key={s.criterion_key}
            className="flex items-center justify-between rounded-lg bg-[var(--glass-surface)] px-2.5 py-1.5"
          >
            <dt className="truncate text-xs text-[var(--text-secondary)]">
              {labels.criterion(s.criterion_key, s.label)}
            </dt>
            <dd className="ml-2 shrink-0 text-sm font-bold text-[var(--text-primary)]">
              {s.score != null ? t("scoreOutOf", { score: s.score }) : "—"}
            </dd>
          </div>
        ))}
      </dl>

      {mine.overall_score != null && (
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          {t("overall", { score: mine.overall_score.toFixed(1) })}
        </p>
      )}

      {mine.comment && (
        <p className="mt-2 whitespace-pre-wrap rounded-lg bg-[var(--glass-surface)] p-2.5 text-sm text-[var(--text-secondary)]">
          {mine.comment}
        </p>
      )}

      {canSubmit && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onEdit}>
            <PencilSimple aria-hidden weight="bold" className="size-4" />
            {t("edit")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onWithdraw}>
            <Trash aria-hidden weight="bold" className="size-4" />
            {t("withdraw")}
          </Button>
        </div>
      )}
    </div>
  );
}
