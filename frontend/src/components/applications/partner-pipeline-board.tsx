"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Lightbulb,
  LogIn,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, useToast } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  KanbanBoard,
  StatusChip,
  type KanbanMoveEvent,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { useApplicationLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  newIdempotencyKey,
  type PipelineCard,
  type PipelineColumn,
  type PipelineStage,
  type RejectionReason,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { PipelineColumnView } from "./pipeline-board/pipeline-column";
import { BulkActionBar } from "./pipeline-board/bulk-action-bar";
import { BulkRejectModal } from "./pipeline-board/bulk-reject-modal";
import { RollbackModal } from "./pipeline-board/rollback-modal";
import { BoardSkeleton } from "./pipeline-board/board-skeleton";
import {
  APPLICATION_CHIP_TONE,
  cardHandle,
  MIN_REASON,
  NEW_COLUMN_ID,
  STALE_DAYS,
} from "./pipeline-board/utils";

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

  const boardKey = useMemo(() => ["applications", "pipeline", jobId] as const, [jobId]);

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
    mutationFn: () => applicationsApi.bulkReview(jobId, Array.from(selected)),
    onSuccess: (data) => {
      clearSelection();
      refetchBoard();
      toast.show({
        tone: "success",
        title: t("bulkReviewedToast", { count: data.reviewed, skipped: data.skipped }),
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
        title: t("bulkRejectedToast", { count: data.rejected, skipped: data.skipped }),
      });
    },
    onError: (e) => {
      setBulkRejectOpen(false);
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  /* ------------------------------ rollback modal ----------------------------- */
  const [rollbackTarget, setRollbackTarget] = useState<RollbackTarget | null>(null);
  const [rollbackStageId, setRollbackStageId] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [rollbackFieldError, setRollbackFieldError] = useState<string | null>(null);

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
      if (e instanceof ApiError && e.isConflict && e.details?.reason === "scorecard_required") {
        const submitted = typeof e.details.submitted === "number" ? e.details.submitted : 0;
        const required = typeof e.details.required === "number" ? e.details.required : 1;
        toast.show({ tone: "warning", title: t("scorecardBlockedToast", { submitted, required }) });
        refetchBoard();
        return;
      }
      if (e instanceof ApiError && e.isConflict && e.details?.reason === "score_below_threshold") {
        const avg =
          typeof e.details.avg_overall === "number" ? e.details.avg_overall.toFixed(1) : "—";
        const threshold =
          typeof e.details.threshold === "number" ? e.details.threshold.toFixed(1) : "—";
        toast.show({ tone: "warning", title: t("scoreBelowThresholdToast", { avg, threshold }) });
        refetchBoard();
        return;
      }
      if (!handleConflict(e)) {
        toast.show({ tone: "error", title: apiError(e) });
      }
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: (vars: { id: string; target_stage_id: string; reason: string }) =>
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

  function openRollback(card: PipelineCard, presetStageId?: string) {
    setRollbackTarget({
      applicationId: card.application_id,
      stageId: card.stage_id,
      handle: cardHandle(card),
    });
    setRollbackStageId(presetStageId ?? "");
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

  const priorStages: PipelineStage[] = priorStagesFor(rollbackTarget?.stageId ?? null);

  const requiredActionByStage = useMemo(() => {
    const map = new Map<string, string>();
    for (const stage of board?.stages ?? []) {
      if (stage.required_action) map.set(stage.id, stage.required_action);
    }
    return map;
  }, [board]);

  /** Fast lookup of every board card by application id (for drag-to-move). */
  const cardsById = useMemo(() => {
    const map = new Map<string, PipelineCard>();
    for (const col of board?.columns ?? []) {
      for (const c of col.candidates) map.set(c.application_id, c);
    }
    return map;
  }, [board]);

  /** Column droppable id → its index in the ordered board. */
  const columnIndexById = useMemo(() => {
    const map = new Map<string, number>();
    (board?.columns ?? []).forEach((c, i) => map.set(c.stage_id ?? NEW_COLUMN_ID, i));
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

  /**
   * Drag-to-move: forward drop = advance one stage; backward drop = open the
   * rollback modal with the target stage preselected (reason ≥ 20 chars still
   * required). Dropping onto the pre-pipeline "new" bucket is not a rollback
   * target — surface a hint instead of a silent no-op.
   */
  function handleMove(ev: KanbanMoveEvent) {
    const fromIdx = columnIndexById.get(ev.fromColumnId);
    const toIdx = columnIndexById.get(ev.toColumnId);
    if (fromIdx == null || toIdx == null || fromIdx === toIdx) return;
    const card = cardsById.get(ev.cardId);
    if (!card) return;

    if (toIdx > fromIdx) {
      advanceMutation.mutate(ev.cardId);
      return;
    }
    // Backward: the target must be a real prior stage.
    if (ev.toColumnId === NEW_COLUMN_ID) {
      toast.show({ tone: "warning", title: t("rollbackNeedsStage") });
      return;
    }
    openRollback(card, ev.toColumnId);
  }

  const backLink = (
    <Link
      href={`/partner/jobs/${jobId}`}
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <ArrowLeft aria-hidden className="size-4" strokeWidth={1.8} />
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
            icon={err.isPermissionError ? ShieldAlert : LogIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
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
          icon={AlertCircle}
          title={err.code === "NETWORK_ERROR" ? tStates("offlineTitle") : tStates("errorTitle")}
          description={err.code === "NETWORK_ERROR" ? tStates("offlineBody") : tStates("errorBody")}
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
    <Link href={`/partner/jobs/${jobId}/applications`}>
      <Button variant="secondary" size="sm">
        <Users aria-hidden className="size-4" strokeWidth={1.8} />
        {t("listView")}
      </Button>
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
      <PageHeader title={board.job.title || t("title")} description={t("subtitle")} actions={subnav} />

      {/* Board-safe summary chips */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusChip tone="indigo" dot>{t("inPipeline", { count: totalVisible })}</StatusChip>
        <StatusChip tone="danger" dot>{t("rejectedCount", { count: board.summary.rejected ?? 0 })}</StatusChip>
        <StatusChip tone="neutral" dot>{t("withdrawnCount", { count: board.summary.withdrawn ?? 0 })}</StatusChip>
      </div>

      {/* AI pipeline health */}
      {totalVisible > 0 &&
        (() => {
          const now = Date.now();
          const allCandidates = board.columns.flatMap((c) => c.candidates);
          const staleCount = allCandidates.filter((card) => {
            if (!card.entered_at) return false;
            const days = (now - new Date(card.entered_at).getTime()) / 86_400_000;
            return days >= STALE_DAYS;
          }).length;
          const gateBlockedCount = allCandidates.filter(
            (card) => card.evaluation && card.evaluation.gate_met === false,
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
          if (busiestCol && busiestCol.count > 0)
            insights.push(t("aiInsightBusiestStage", { stage: busiestCol.name, count: busiestCol.count }));
          if (insights.length === 0) insights.push(t("aiInsightFlowing"));
          return (
            <Card className="mb-4 border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span
                    className="flex size-7 items-center justify-center rounded-lg"
                    style={{ background: "var(--content-ai-soft)" }}
                  >
                    <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
                  </span>
                  <CardTitle>{t("aiPipelineTitle")}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {insights.map((text, i) => (
                    <li key={i} className="flex items-start gap-2 text-[0.8125rem] text-foreground">
                      <Lightbulb
                        aria-hidden
                        className="mt-0.5 size-3.5 shrink-0"
                        strokeWidth={1.9}
                        style={{ color: "var(--content-ai)" }}
                      />
                      {text}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          );
        })()}

      {board.truncated && (
        <p
          role="status"
          className="mb-4 flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-xs"
          style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
        >
          <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={1.9} />
          {t("truncatedNote", { cap: board.candidate_cap })}
        </p>
      )}

      {allEmpty ? (
        <EmptyState kind="empty" icon={Users} title={t("emptyTitle")} description={t("emptyBody")} />
      ) : (
        <KanbanBoard
          ariaLabel={t("boardAriaLabel")}
          onMove={handleMove}
          disabled={advanceMutation.isPending}
          renderOverlay={(id) => {
            const card = cardsById.get(id);
            if (!card) return null;
            return (
              <div className="rounded-lg border border-[var(--field-focus-border)] bg-card p-3 shadow-[var(--shadow-xl)]">
                <p className="truncate text-[0.8125rem] font-semibold text-foreground">{cardHandle(card)}</p>
                <div className="mt-1.5">
                  <StatusChip tone={APPLICATION_CHIP_TONE[card.status] ?? "sky"} size="sm">
                    {labels.status(card.status, card.status_label)}
                  </StatusChip>
                </div>
              </div>
            );
          }}
        >
          {board.columns.map((column, index) => {
            const isLast = index === board.columns.length - 1;
            return (
              <PipelineColumnView
                key={column.stage_id ?? NEW_COLUMN_ID}
                column={column}
                stageIndex={index}
                totalStages={board.columns.length}
                canAdvance={!isLast}
                jobId={jobId}
                requiredAction={
                  column.stage_id ? requiredActionByStage.get(column.stage_id) ?? null : null
                }
                hasPriorStage={(stageId) => priorStagesFor(stageId).length > 0}
                locale={locale}
                statusTone={(s) => APPLICATION_CHIP_TONE[s] ?? "sky"}
                statusLabel={(s, l) => labels.status(s, l)}
                advancePendingId={
                  advanceMutation.isPending ? (advanceMutation.variables ?? null) : null
                }
                selected={selected}
                onToggleSelect={toggleSelect}
                onAdvance={(id) => advanceMutation.mutate(id)}
                onRollback={(card) => openRollback(card)}
                t={t}
              />
            );
          })}
        </KanbanBoard>
      )}

      {/* Bulk action toolbar */}
      {selected.size > 0 && (
        <BulkActionBar
          count={selected.size}
          reviewPending={bulkReviewMutation.isPending}
          rejectPending={bulkRejectMutation.isPending}
          onReview={() => bulkReviewMutation.mutate()}
          onReject={() => setBulkRejectOpen(true)}
          onClear={clearSelection}
          t={t}
        />
      )}

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
