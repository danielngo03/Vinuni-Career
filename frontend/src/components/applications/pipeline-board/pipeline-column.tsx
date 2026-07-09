"use client";

import { useTranslations } from "next-intl";
import { ClipboardList, Eye, EyeOff, Star } from "lucide-react";
import { KanbanColumn, StatusChip, type ChipTone } from "@/components/kit";
import type { PipelineCard, PipelineColumn } from "@/lib/api";
import { PipelineCardView } from "./pipeline-card";
import { NEW_COLUMN_ID } from "./utils";

export function PipelineColumnView({
  column,
  stageIndex,
  totalStages,
  canAdvance,
  jobId,
  requiredAction,
  hasPriorStage,
  locale,
  statusTone,
  statusLabel,
  advancePendingId,
  selected,
  onToggleSelect,
  onAdvance,
  onRollback,
  t,
}: {
  column: PipelineColumn;
  stageIndex: number;
  totalStages: number;
  canAdvance: boolean;
  jobId: string;
  requiredAction: string | null;
  hasPriorStage: (stageId: string | null) => boolean;
  locale: string;
  statusTone: (status: string) => ChipTone;
  statusLabel: (status: string, label?: string | null) => string;
  advancePendingId: string | null;
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onAdvance: (id: string) => void;
  onRollback: (card: PipelineCard) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const isNewBucket = column.stage_id === null;
  const isLastStage = stageIndex === totalStages - 1;
  const columnId = column.stage_id ?? NEW_COLUMN_ID;
  const isGate = requiredAction === "scorecard" || requiredAction === "score_threshold";

  const accent = isNewBucket
    ? "var(--viz-sky)"
    : isLastStage
      ? "var(--viz-emerald)"
      : isGate
        ? "var(--viz-amber)"
        : "var(--viz-indigo)";

  const gateLabel =
    requiredAction === "scorecard"
      ? t("gateScorecard")
      : requiredAction === "score_threshold"
        ? t("gateThreshold")
        : requiredAction === "manual"
          ? t("gateManual")
          : null;

  return (
    <KanbanColumn
      id={columnId}
      title={column.name}
      count={column.count}
      accent={accent}
      progress={totalStages > 1 ? (stageIndex + 1) / totalStages : undefined}
      meta={
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="type-caption text-muted-foreground">
            {t("stageOf", { n: stageIndex + 1, total: totalStages })}
          </span>
          {gateLabel && (
            <StatusChip tone={isGate ? "amber" : "neutral"} size="sm">
              {isGate ? (
                <ClipboardList aria-hidden className="size-2.5" strokeWidth={2} />
              ) : (
                <Star aria-hidden className="size-2.5" strokeWidth={2} />
              )}
              {gateLabel}
            </StatusChip>
          )}
        </div>
      }
      aside={
        <span
          className="inline-flex items-center gap-1 type-caption font-medium text-muted-foreground"
          title={column.candidate_visible ? t("visibleHint") : t("hiddenHint")}
        >
          {column.candidate_visible ? (
            <Eye aria-hidden className="size-3.5" strokeWidth={1.8} />
          ) : (
            <EyeOff aria-hidden className="size-3.5" strokeWidth={1.8} />
          )}
          {column.candidate_visible ? t("visible") : t("hidden")}
        </span>
      }
      empty={
        <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center type-caption text-muted-foreground">
          {t("columnEmpty")}
        </p>
      }
    >
      {column.candidates.map((card) => (
        <PipelineCardView
          key={card.application_id}
          card={card}
          columnId={columnId}
          isNewBucket={isNewBucket}
          canAdvance={canAdvance}
          jobId={jobId}
          requiredAction={requiredAction}
          canRollback={hasPriorStage(card.stage_id)}
          locale={locale}
          statusTone={statusTone}
          statusLabel={statusLabel}
          advancePending={advancePendingId === card.application_id}
          isSelected={selected.has(card.application_id)}
          onToggleSelect={() => onToggleSelect(card.application_id)}
          onAdvance={() => onAdvance(card.application_id)}
          onRollback={() => onRollback(card)}
          t={t}
        />
      ))}
    </KanbanColumn>
  );
}
