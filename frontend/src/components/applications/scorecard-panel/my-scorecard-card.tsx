"use client";

import { useTranslations } from "next-intl";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui";
import { StatusChip } from "@/components/kit";
import { useScorecardLabels } from "@/lib/applications/labels";
import type { Scorecard } from "@/lib/api";
import { RECOMMENDATION_CHIP } from "../chip-tones";

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
  const recTone = RECOMMENDATION_CHIP[mine.recommendation] ?? "neutral";

  return (
    <div
      className="rounded-lg border p-3.5"
      style={{ borderColor: "var(--brand-primary)", background: "color-mix(in srgb, var(--brand-primary) 5%, transparent)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="type-small font-semibold text-foreground">{t("yourEvaluation")}</p>
        <StatusChip tone={recTone}>
          {labels.recommendation(mine.recommendation, mine.recommendation_label)}
        </StatusChip>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2">
        {mine.scores.map((s) => (
          <div
            key={s.criterion_key}
            className="flex items-center justify-between rounded-md bg-[var(--bg-subtle)] px-2.5 py-1.5"
          >
            <dt className="truncate type-caption text-muted-foreground">
              {labels.criterion(s.criterion_key, s.label)}
            </dt>
            <dd className="ml-2 shrink-0 type-small font-bold tabular-nums text-foreground">
              {s.score != null ? t("scoreOutOf", { score: s.score }) : "—"}
            </dd>
          </div>
        ))}
      </dl>

      {mine.overall_score != null && (
        <p className="mt-2 type-caption text-muted-foreground">
          {t("overall", { score: mine.overall_score.toFixed(1) })}
        </p>
      )}

      {mine.comment && (
        <p className="mt-2 whitespace-pre-wrap rounded-md bg-[var(--bg-subtle)] p-2.5 type-small text-muted-foreground">
          {mine.comment}
        </p>
      )}

      {canSubmit && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onEdit}>
            <Pencil aria-hidden className="size-4" strokeWidth={1.8} />
            {t("edit")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onWithdraw}>
            <Trash2 aria-hidden className="size-4" strokeWidth={1.8} />
            {t("withdraw")}
          </Button>
        </div>
      )}
    </div>
  );
}
