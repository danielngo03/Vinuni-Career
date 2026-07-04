"use client";

import { useTranslations } from "next-intl";
import { ClipboardText, Eye, EyeSlash, Star } from "@phosphor-icons/react";
import { StatusBadge } from "@/components/ui";
import type { PipelineCard, PipelineColumn } from "@/lib/api";
import { PipelineCardView } from "./pipeline-card";

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
  /** Advance gate for this stage (`scorecard` / `score_threshold` / `manual`). */
  requiredAction: string | null;
  hasPriorStage: (stageId: string | null) => boolean;
  locale: string;
  statusTone: (status: string) => Parameters<typeof StatusBadge>[0]["tone"];
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

  const gateLabel =
    requiredAction === "scorecard"
      ? t("gateScorecard")
      : requiredAction === "score_threshold"
        ? t("gateThreshold")
        : requiredAction === "manual"
          ? t("gateManual")
          : null;

  return (
    <section
      role="listitem"
      aria-label={t("columnAria", { name: column.name, count: column.count })}
      className="flex w-72 shrink-0 flex-col rounded-2xl border border-[var(--border-default)] bg-white "
    >
      {/* Stage progress strip — one segment per stage, filled up to current */}
      {totalStages > 1 && (
        <div className="flex rounded-t-2xl overflow-hidden" aria-hidden>
          {Array.from({ length: totalStages }).map((_, i) => (
            <span
              key={i}
              className={`h-0.5 flex-1 transition-colors ${
                i <= stageIndex
                  ? isLastStage
                    ? "bg-emerald-400"
                    : "bg-[var(--brand-primary)]"
                  : "bg-white/30"
              }`}
            />
          ))}
        </div>
      )}

      <header className="flex items-center justify-between gap-2 border-b border-[var(--border-default)] px-3.5 py-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate text-sm font-bold text-[var(--text-primary)]">
              {column.name}
            </h2>
            <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
              {column.count}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[var(--text-muted)]">
              {t("stageOf", { n: stageIndex + 1, total: totalStages })}
            </span>
            {gateLabel && (
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--amber-600)]/30 bg-[var(--amber-100)]/60 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--amber-700)]">
                {requiredAction === "scorecard" || requiredAction === "score_threshold" ? (
                  <ClipboardText aria-hidden weight="duotone" className="size-2.5" />
                ) : (
                  <Star aria-hidden weight="duotone" className="size-2.5" />
                )}
                {gateLabel}
              </span>
            )}
          </div>
        </div>
        <span
          className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--text-muted)] shrink-0"
          title={column.candidate_visible ? t("visibleHint") : t("hiddenHint")}
        >
          {column.candidate_visible ? (
            <Eye aria-hidden weight="duotone" className="size-3.5" />
          ) : (
            <EyeSlash aria-hidden weight="duotone" className="size-3.5" />
          )}
          {column.candidate_visible ? t("visible") : t("hidden")}
        </span>
      </header>

      <div className="flex flex-1 flex-col gap-2.5 p-2.5">
        {column.candidates.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
            {t("columnEmpty")}
          </p>
        ) : (
          column.candidates.map((card) => (
            <PipelineCardView
              key={card.application_id}
              card={card}
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
          ))
        )}
      </div>
    </section>
  );
}
