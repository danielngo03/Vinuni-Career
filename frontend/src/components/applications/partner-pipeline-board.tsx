"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ShieldWarning,
  SignIn,
  Sparkle,
  LightbulbFilament,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, StatusBadge } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  APPLICATION_STATUS_TONE,
  useApplicationLabels,
} from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  newIdempotencyKey,
  type BulkAdvanceResult,
  type PipelineCard,
  type PipelineColumn,
  type PipelineStage,
  type RejectionReason,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useToast } from "@/components/ui";
import { PipelineColumnView } from "./pipeline-board/pipeline-column";
import { BulkActionBar } from "./pipeline-board/bulk-action-bar";
import { BulkRejectModal } from "./pipeline-board/bulk-reject-modal";
import { BulkAdvanceModal } from "./pipeline-board/bulk-advance-modal";
import { RollbackModal } from "./pipeline-board/rollback-modal";
import { BoardSkeleton } from "./pipeline-board/board-skeleton";
import { cardHandle, groupBulkAdvance, MIN_REASON, STALE_DAYS } from "./pipeline-board/utils";

type RollbackTarget = {
  applicationId: string;
  stageId: string | null;
  handle: string;
};

export function PartnerPipelineBoard({ jobId }: { jobId: string }) {
  const t = useTranslations("pipeline");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useApplicationLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();

  const boardKey = useMemo(
    () => ["applications", "pipeline", jobId] as const,
    [jobId],
  );

  const query = useQuery({
    queryKey: boardKey,
    queryFn: () => applicationsApi.pipelineBoard(jobId),
    retry: false,
  });

  const board = query.data;

  /* ------------------------------ bulk selection ----------------------------- */
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkRejectOpen, setBulkRejectOpen] = useState(false);
  const [bulkReason, setBulkReason] = useState<RejectionReason>("not_qualified");
  const [bulkNote, setBulkNote] = useState("");
  const [bulkAdvanceOpen, setBulkAdvanceOpen] = useState(false);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelected(new Set());
  }

  const bulkReviewMutation = useMutation({
    mutationFn: () =>
      applicationsApi.bulkReview(jobId, Array.from(selected)),
    onSuccess: (data) => {
      clearSelection();
      refetchBoard();
      toast.show({
        tone: "success",
        title: t("bulkReviewedToast", {
          count: data.reviewed,
          skipped: data.skipped,
        }),
      });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const bulkRejectMutation = useMutation({
    mutationFn: () =>
      applicationsApi.bulkReject(jobId, {
        application_ids: Array.from(selected),
        reason: bulkReason,
        note: bulkNote.trim() || null,
      }),
    onSuccess: (data) => {
      setBulkRejectOpen(false);
      clearSelection();
      setBulkNote("");
      refetchBoard();
      toast.show({
        tone: "success",
        title: t("bulkRejectedToast", {
          count: data.rejected,
          skipped: data.skipped,
        }),
      });
    },
    onError: (e) => {
      setBulkRejectOpen(false);
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  /**
   * Compose an honest, localized bulk-advance summary from the batch result:
   * "N advanced · M need a scorecard · ..." (BUSINESS_LOGIC §3.6). The backend
   * advances only eligible candidates; blocked/skipped ones are reported, never
   * force-advanced.
   */
  function summarizeBulkAdvance(result: BulkAdvanceResult): string {
    const b = groupBulkAdvance(result);
    const parts: string[] = [];
    if (b.advanced > 0)
      parts.push(t("bulkAdvanceAdvanced", { count: b.advanced }));
    if (b.scorecardBlocked > 0)
      parts.push(t("bulkAdvanceBlockedScorecard", { count: b.scorecardBlocked }));
    if (b.thresholdBlocked > 0)
      parts.push(t("bulkAdvanceBlockedThreshold", { count: b.thresholdBlocked }));
    if (b.otherBlocked > 0)
      parts.push(t("bulkAdvanceBlockedOther", { count: b.otherBlocked }));
    if (b.skipped > 0) parts.push(t("bulkAdvanceSkipped", { count: b.skipped }));
    if (b.errors > 0) parts.push(t("bulkAdvanceErrors", { count: b.errors }));
    return parts.length > 0 ? parts.join(" · ") : t("bulkAdvanceNone");
  }

  const bulkAdvanceMutation = useMutation({
    mutationFn: () => applicationsApi.bulkAdvance(jobId, Array.from(selected)),
    onSuccess: (data) => {
      setBulkAdvanceOpen(false);
      clearSelection();
      refetchBoard();
      toast.show({
        tone: data.advanced > 0 ? "success" : "warning",
        title: summarizeBulkAdvance(data),
      });
    },
    onError: (e) => {
      setBulkAdvanceOpen(false);
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  /* ------------------------------ rollback modal ----------------------------- */
  const [rollbackTarget, setRollbackTarget] = useState<RollbackTarget | null>(
    null,
  );
  const [rollbackStageId, setRollbackStageId] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [rollbackFieldError, setRollbackFieldError] = useState<string | null>(
    null,
  );

  function refetchBoard() {
    void qc.invalidateQueries({ queryKey: boardKey });
  }

  /** 409 (stale version / illegal transition) → friendly toast + refetch. */
  function handleConflict(e: unknown): boolean {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "warning", title: t("conflictToast") });
      refetchBoard();
      return true;
    }
    return false;
  }

  const advanceMutation = useMutation({
    mutationFn: (id: string) =>
      applicationsApi.advance(id, { idempotencyKey: newIdempotencyKey() }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("advancedToast") });
      refetchBoard();
    },
    onError: (e) => {
      // A `scorecard` stage blocks advance until a scorecard is submitted: the
      // server returns 409 `scorecard_required` with {submitted, required}. Show
      // the precise blocked reason instead of the generic conflict toast, and
      // refetch so the card's "scorecard required" indicator stays accurate.
      if (
        e instanceof ApiError &&
        e.isConflict &&
        e.details?.reason === "scorecard_required"
      ) {
        const submitted =
          typeof e.details.submitted === "number" ? e.details.submitted : 0;
        const required =
          typeof e.details.required === "number" ? e.details.required : 1;
        toast.show({
          tone: "warning",
          title: t("scorecardBlockedToast", { submitted, required }),
        });
        refetchBoard();
        return;
      }
      // A `score_threshold` stage blocks advance once all assigned reviewers have
      // submitted but the average score is below the stage threshold: 409
      // `score_below_threshold` with {avg_overall, threshold} (ADR-0006).
      if (
        e instanceof ApiError &&
        e.isConflict &&
        e.details?.reason === "score_below_threshold"
      ) {
        const avg =
          typeof e.details.avg_overall === "number"
            ? e.details.avg_overall.toFixed(1)
            : "—";
        const threshold =
          typeof e.details.threshold === "number"
            ? e.details.threshold.toFixed(1)
            : "—";
        toast.show({
          tone: "warning",
          title: t("scoreBelowThresholdToast", { avg, threshold }),
        });
        refetchBoard();
        return;
      }
      if (!handleConflict(e)) {
        toast.show({ tone: "error", title: apiError(e) });
      }
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (vars: {
      id: string;
      target_stage_id: string;
      reason: string;
    }) =>
      applicationsApi.rollback(vars.id, {
        target_stage_id: vars.target_stage_id,
        reason: vars.reason.trim(),
      }),
    onSuccess: () => {
      closeRollback();
      toast.show({ tone: "success", title: t("rolledBackToast") });
      refetchBoard();
    },
    onError: (e) => {
      // 422 → keep the modal open, surface inline; 409 → close + reload.
      if (e instanceof ApiError && e.isValidation) {
        setRollbackFieldError(t("reasonTooShort", { min: MIN_REASON }));
        return;
      }
      closeRollback();
      if (!handleConflict(e)) {
        toast.show({ tone: "error", title: apiError(e) });
      }
    },
  });

  function openRollback(card: PipelineCard) {
    setRollbackTarget({
      applicationId: card.application_id,
      stageId: card.stage_id,
      handle: cardHandle(card),
    });
    setRollbackStageId("");
    setRollbackReason("");
    setRollbackFieldError(null);
  }

  function closeRollback() {
    setRollbackTarget(null);
    setRollbackStageId("");
    setRollbackReason("");
    setRollbackFieldError(null);
  }

  /** Prior stages for a given stage id (sort_order strictly less). */
  const priorStagesFor = useMemo(() => {
    const stages = board?.stages ?? [];
    return (stageId: string | null): PipelineStage[] => {
      if (!stageId) return [];
      const current = stages.find((s) => s.id === stageId);
      if (!current) return [];
      return stages
        .filter((s) => s.sort_order < current.sort_order)
        .sort((a, b) => a.sort_order - b.sort_order);
    };
  }, [board]);

  /** Prior stages for the card currently targeted by the rollback modal. */
  const priorStages: PipelineStage[] = priorStagesFor(
    rollbackTarget?.stageId ?? null,
  );

  /** Map of stage id → required_action (drives the scorecard-gate indicator). */
  const requiredActionByStage = useMemo(() => {
    const map = new Map<string, string>();
    for (const stage of board?.stages ?? []) {
      if (stage.required_action) map.set(stage.id, stage.required_action);
    }
    return map;
  }, [board]);

  function submitRollback() {
    if (!rollbackTarget) return;
    if (!rollbackStageId) {
      setRollbackFieldError(t("targetRequired"));
      return;
    }
    if (rollbackReason.trim().length < MIN_REASON) {
      setRollbackFieldError(t("reasonTooShort", { min: MIN_REASON }));
      return;
    }
    rollbackMutation.mutate({
      id: rollbackTarget.applicationId,
      target_stage_id: rollbackStageId,
      reason: rollbackReason,
    });
  }

  const backLink = (
    <Link
      href={`/partner/jobs/${jobId}`}
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToJob")}
    </Link>
  );

  /* ------------------------------- gates --------------------------------- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {backLink}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError
                ? tStates("permissionBody")
                : tStates("authBody")
            }
          />
        </>
      );
    }
    if (err.isNotFound) {
      return (
        <>
          {backLink}
          <EmptyState
            kind="empty"
            icon={Users}
            title={t("notFoundTitle")}
            description={t("notFoundBody")}
            action={
              <Link href={`/partner/jobs/${jobId}`}>
                <Button variant="secondary">{t("backToJob")}</Button>
              </Link>
            }
          />
        </>
      );
    }
    return (
      <>
        {backLink}
        <EmptyState
          kind={err.code === "NETWORK_ERROR" ? "offline" : "error"}
          icon={WarningCircle}
          title={
            err.code === "NETWORK_ERROR"
              ? tStates("offlineTitle")
              : tStates("errorTitle")
          }
          description={
            err.code === "NETWORK_ERROR"
              ? tStates("offlineBody")
              : tStates("errorBody")
          }
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const subnav = (
    <Link
      href={`/partner/jobs/${jobId}/applications`}
      className="inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <Users aria-hidden weight="duotone" className="size-4" />
      {t("listView")}
    </Link>
  );

  /* ------------------------------ loading -------------------------------- */
  if (query.isPending || !board) {
    return (
      <>
        {backLink}
        <PageHeader title={t("title")} description={t("subtitle")} />
        <BoardSkeleton />
      </>
    );
  }

  const totalVisible = board.columns.reduce((sum, c) => sum + c.count, 0);
  const allEmpty =
    totalVisible === 0 &&
    (board.summary.rejected ?? 0) === 0 &&
    (board.summary.withdrawn ?? 0) === 0;

  return (
    <>
      {backLink}
      <PageHeader
        title={board.job.title || t("title")}
        description={t("subtitle")}
        actions={subnav}
      />

      {/* Board-safe summary chips */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-[var(--text-muted)]">
          {t("inPipeline", { count: totalVisible })}
        </span>
        <StatusBadge tone="rejected">
          {t("rejectedCount", { count: board.summary.rejected ?? 0 })}
        </StatusBadge>
        <StatusBadge tone="closed">
          {t("withdrawnCount", { count: board.summary.withdrawn ?? 0 })}
        </StatusBadge>
      </div>

      {/* AI Pipeline Health panel — shown when there are candidates in the pipeline */}
      {totalVisible > 0 && (() => {
        const now = Date.now();
        const allCandidates = board.columns.flatMap((c) => c.candidates);
        const staleCount = allCandidates.filter((card) => {
          if (!card.entered_at) return false;
          const days = (now - new Date(card.entered_at).getTime()) / 86_400_000;
          return days >= STALE_DAYS;
        }).length;
        const gateBlockedCount = allCandidates.filter(
          (card) => card.evaluation && card.evaluation.gate_met === false
        ).length;
        const busiestCol = board.columns
          .filter((c) => c.stage_id !== null)
          .reduce<PipelineColumn | null>(
            (best, c) => (best === null || c.count > best.count ? c : best),
            null,
          );
        const insights: string[] = [];
        if (staleCount > 0) insights.push(t("aiInsightStale", { count: staleCount }));
        if (gateBlockedCount > 0) insights.push(t("aiInsightGateBlocked", { count: gateBlockedCount }));
        if (busiestCol && busiestCol.count > 0) insights.push(t("aiInsightBusiestStage", { stage: busiestCol.name, count: busiestCol.count }));
        if (insights.length === 0) insights.push(t("aiInsightFlowing"));
        return (
          <div className="mb-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 ">
            <p className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiPipelineTitle")}
            </p>
            <ul className="space-y-1.5">
              {insights.map((text, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {text}
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {board.truncated && (
        <p
          role="status"
          className="mb-4 flex items-start gap-2 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] px-3.5 py-2.5 text-xs text-[var(--amber-700)]"
        >
          <ShieldWarning aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
          {t("truncatedNote", { cap: board.candidate_cap })}
        </p>
      )}

      {allEmpty ? (
        <EmptyState
          kind="empty"
          icon={Users}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <div
          role="list"
          aria-label={t("boardAriaLabel")}
          className="flex gap-4 overflow-x-auto pb-4"
        >
          {board.columns.map((column, index) => {
            const isLast = index === board.columns.length - 1;
            return (
              <PipelineColumnView
                key={column.stage_id ?? "__new__"}
                column={column}
                stageIndex={index}
                totalStages={board.columns.length}
                canAdvance={!isLast}
                jobId={jobId}
                requiredAction={
                  column.stage_id
                    ? requiredActionByStage.get(column.stage_id) ?? null
                    : null
                }
                hasPriorStage={(stageId) => priorStagesFor(stageId).length > 0}
                locale={locale}
                statusTone={(s) => APPLICATION_STATUS_TONE[s] ?? "info"}
                statusLabel={(s, l) => labels.status(s, l)}
                advancePendingId={
                  advanceMutation.isPending
                    ? (advanceMutation.variables ?? null)
                    : null
                }
                selected={selected}
                onToggleSelect={toggleSelect}
                onAdvance={(id) => advanceMutation.mutate(id)}
                onRollback={openRollback}
                t={t}
              />
            );
          })}
        </div>
      )}

      {/* Bulk action toolbar — floats at the bottom when cards are selected */}
      {selected.size > 0 && (
        <BulkActionBar
          count={selected.size}
          reviewPending={bulkReviewMutation.isPending}
          advancePending={bulkAdvanceMutation.isPending}
          rejectPending={bulkRejectMutation.isPending}
          onReview={() => bulkReviewMutation.mutate()}
          onAdvance={() => setBulkAdvanceOpen(true)}
          onReject={() => setBulkRejectOpen(true)}
          onClear={clearSelection}
          t={t}
        />
      )}

      {/* Bulk reject modal */}
      <BulkRejectModal
        open={bulkRejectOpen}
        count={selected.size}
        reason={bulkReason}
        note={bulkNote}
        loading={bulkRejectMutation.isPending}
        onReasonChange={setBulkReason}
        onNoteChange={setBulkNote}
        onClose={() => setBulkRejectOpen(false)}
        onSubmit={() => bulkRejectMutation.mutate()}
        t={t}
      />

      {/* Bulk advance confirm */}
      <BulkAdvanceModal
        open={bulkAdvanceOpen}
        count={selected.size}
        loading={bulkAdvanceMutation.isPending}
        onClose={() => setBulkAdvanceOpen(false)}
        onSubmit={() => bulkAdvanceMutation.mutate()}
        t={t}
      />

      <RollbackModal
        open={!!rollbackTarget}
        handle={rollbackTarget?.handle ?? ""}
        stages={priorStages}
        stageId={rollbackStageId}
        onStageChange={(v) => {
          setRollbackStageId(v);
          if (v) setRollbackFieldError(null);
        }}
        reason={rollbackReason}
        onReasonChange={(v) => {
          setRollbackReason(v);
          if (v.trim().length >= MIN_REASON) setRollbackFieldError(null);
        }}
        fieldError={rollbackFieldError}
        minReason={MIN_REASON}
        loading={rollbackMutation.isPending}
        onClose={closeRollback}
        onSubmit={submitRollback}
      />
    </>
  );
}
