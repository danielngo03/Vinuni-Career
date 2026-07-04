"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  CheckCircle,
  Flag,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  UserCheck,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  Sheet,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { ModerationTabs } from "@/components/moderation/moderation-tabs";
import {
  BulkResultList,
  ClaimBadge,
  ReasonCodeSelect,
  RowSelectCheckbox,
  SlaBadge,
} from "@/components/moderation/queue-controls";
import { useAuthStore } from "@/stores/auth-store";
import {
  useJobLabels,
  JOB_STATUS_TONE,
  MODERATION_TONE,
} from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { formatDateTime } from "@/lib/format";
import {
  ApiError,
  jobsApi,
  type BulkModerationResultItem,
  type ModerationReasonCode,
  type OwnerJobSummary,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const STATUS_FILTERS = ["pending_review", "active", "rejected", "closed"] as const;

type BulkKind = "approve" | "reject" | null;

export function JobModerationScreen() {
  const t = useTranslations("jobsModeration");
  const tj = useTranslations("jobs");
  const tm = useTranslations("common");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useJobLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();
  const userId = useAuthStore((s) => s.user?.id);

  const [statusFilter, setStatusFilter] = useState<string>("pending_review");
  const [selected, setSelected] = useState<OwnerJobSummary | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [escalateOpen, setEscalateOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonCode, setReasonCode] = useState<ModerationReasonCode | string>("other");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [escalateNote, setEscalateNote] = useState("");
  const [escalateReasonCode, setEscalateReasonCode] =
    useState<ModerationReasonCode | string>("policy_violation");

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkKind, setBulkKind] = useState<BulkKind>(null);
  const [bulkResults, setBulkResults] = useState<BulkModerationResultItem[] | null>(null);

  const query = useQuery({
    queryKey: ["admin", "jobs", statusFilter],
    queryFn: () => jobsApi.listModeration(statusFilter),
    retry: false,
  });

  // Full detail for the review drawer (superadmin/owner only; 404 otherwise).
  const detailQuery = useQuery({
    queryKey: ["admin", "jobs", "detail", selected?.id],
    queryFn: () => jobsApi.getOwned(selected!.id),
    enabled: selected !== null,
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "jobs"] });
  }

  function handleError(e: unknown) {
    const reason_ =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
    if (reason_ === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      setApproveOpen(false);
      setRejectOpen(false);
      setSelected(null);
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const approve = useMutation({
    mutationFn: (job: OwnerJobSummary) => jobsApi.approve(job.id),
    onSuccess: () => {
      setApproveOpen(false);
      setSelected(null);
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reject = useMutation({
    mutationFn: (job: OwnerJobSummary) =>
      jobsApi.reject(job.id, reason, job.version, reasonCode),
    onSuccess: () => {
      setRejectOpen(false);
      setSelected(null);
      setReason("");
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleError,
  });

  const claim = useMutation({
    mutationFn: (job: OwnerJobSummary) => jobsApi.claim(job.id),
    onSuccess: (data) => {
      setSelected(data);
      refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        toast.show({
          tone: "error",
          title: tm("moderationQueue.claimConflictToast"),
          description: tm("moderationQueue.claimConflictBody"),
        });
        refresh();
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const escalate = useMutation({
    mutationFn: (job: OwnerJobSummary) =>
      jobsApi.escalate(job.id, { reason_code: escalateReasonCode, note: escalateNote.trim() || undefined }),
    onSuccess: () => {
      setEscalateOpen(false);
      setSelected(null);
      toast.show({ tone: "success", title: tm("moderationQueue.escalatedToast") });
      refresh();
    },
    onError: handleError,
  });

  const bulkApprove = useMutation({
    mutationFn: (ids: string[]) => jobsApi.bulkApprove(ids),
    onSuccess: (results) => {
      setBulkKind(null);
      setBulkResults(results);
      setSelectedIds(new Set());
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const bulkReject = useMutation({
    mutationFn: (ids: string[]) =>
      jobsApi.bulkReject(
        ids.map((id) => ({ id, reason, reason_code: reasonCode })),
      ),
    onSuccess: (results) => {
      setBulkKind(null);
      setBulkResults(results);
      setSelectedIds(new Set());
      setReason("");
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <ModerationTabs />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const rows = query.data ?? [];
  const detail = detailQuery.data;
  const isPending = selected?.status === "pending_review";
  const canClaim = isPending && selected && !selected.claimed_by;
  const canEscalate = isPending;

  function toggleRow(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const pendingRows = rows.filter((r) => r.status === "pending_review");
  const allPendingSelected =
    pendingRows.length > 0 && pendingRows.every((r) => selectedIds.has(r.id));

  const columns: Column<OwnerJobSummary>[] = [
    {
      key: "select",
      header: "",
      className: "w-10",
      cell: (r) =>
        r.status === "pending_review" ? (
          <RowSelectCheckbox
            checked={selectedIds.has(r.id)}
            onChange={(checked) => toggleRow(r.id, checked)}
            label={t("selectRow", { title: r.title })}
          />
        ) : null,
    },
    {
      key: "title",
      header: t("colJob"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--text-primary)]">{r.title}</p>
          <p className="truncate text-xs text-[var(--text-secondary)]">
            {labels.employmentType(r.employment_type, r.employment_type_label)}
            {" · "}
            {formatLocation(r.location_city, r.location_country)}
          </p>
        </div>
      ),
    },
    {
      key: "submitted",
      header: t("colSubmitted"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {formatDateTime(r.created_at, locale)}
        </span>
      ),
    },
    {
      key: "sla",
      header: t("colSla"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <SlaBadge dueBy={r.due_by} ageHours={r.age_hours} isOverdue={r.is_overdue} />
          <ClaimBadge claimedBy={r.claimed_by} isMine={r.claimed_by === userId} />
        </div>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <StatusBadge tone={JOB_STATUS_TONE[r.status] ?? "info"}>
          {labels.status(r.status, r.status_label)}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <Button variant="ghost" size="sm" onClick={() => setSelected(r)}>
          {t("review")}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ModerationTabs />

      {/* ── AI Moderation Queue ── */}
      {!query.isPending && (() => {
        type JobModerationInsightKey = "insightManyPending" | "insightOnePending" | "insightQueueClear" | "insightRejectedReview";
        const insights: JobModerationInsightKey[] = [];
        if (statusFilter === "pending_review") {
          if (rows.length > 3) insights.push("insightManyPending");
          else if (rows.length === 1) insights.push("insightOnePending");
          else if (rows.length === 0) insights.push("insightQueueClear");
        } else if (statusFilter === "rejected" && rows.length > 0) {
          insights.push("insightRejectedReview");
        }
        if (!insights.length) return null;
        return (
          <section
            aria-label={t("aiInsightsTitle")}
            className="mb-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{t("aiInsightsTitle")}</p>
            </div>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Status filter tab chips */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("filterLabel")}>
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              aria-pressed={statusFilter === s}
              className={cn(
                "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                statusFilter === s
                  ? s === "pending_review"
                    ? "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm"
                    : s === "active"
                      ? "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm"
                      : s === "rejected"
                        ? "border-[var(--red-500)]/30 bg-[var(--red-600)] text-white shadow-sm"
                        : "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm"
                  : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
              )}
            >
              {tj(`enums.status.${s}`)}
            </button>
          ))}
        </div>
        {pendingRows.length > 0 && statusFilter === "pending_review" && (
          <label className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={allPendingSelected}
              onChange={(e) =>
                setSelectedIds(
                  e.target.checked ? new Set(pendingRows.map((r) => r.id)) : new Set(),
                )
              }
              className="size-4 cursor-pointer rounded border-[var(--border-default)] accent-[var(--brand-primary)]"
            />
            {tm("moderationQueue.selectAll")}
          </label>
        )}
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border-default)] bg-white px-4 py-2.5">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {tm("moderationQueue.selectedCount", { count: selectedIds.size })}
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
              {tm("moderationQueue.clearSelection")}
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                setReason("");
                setReasonError(null);
                setBulkKind("reject");
              }}
            >
              <XCircle aria-hidden weight="bold" className="size-4" />
              {tm("moderationQueue.bulkReject")}
            </Button>
            <Button variant="primary" size="sm" onClick={() => setBulkKind("approve")}>
              <CheckCircle aria-hidden weight="bold" className="size-4" />
              {tm("moderationQueue.bulkApprove")}
            </Button>
          </div>
        </div>
      )}

      {query.isError &&
      !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError)) ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowId={(r) => r.id}
          loading={query.isPending}
          caption={t("title")}
          empty={{
            kind: "empty",
            icon: Briefcase,
            title: t("empty"),
            description: t("emptyBody"),
          }}
        />
      )}

      {/* Review drawer */}
      <Sheet
        open={selected !== null && !approveOpen && !rejectOpen && !escalateOpen}
        onClose={() => setSelected(null)}
        title={t("reviewTitle")}
        closeLabel={tc("close")}
      >
        {selected && (
          <div className="space-y-4">
            <div>
              <h3 className="text-base font-bold text-[var(--text-primary)]">
                {selected.title}
              </h3>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusBadge tone={JOB_STATUS_TONE[selected.status] ?? "info"}>
                  {labels.status(selected.status, selected.status_label)}
                </StatusBadge>
                <StatusBadge tone={MODERATION_TONE[selected.moderation_status] ?? "info"}>
                  {labels.moderation(selected.moderation_status, selected.moderation_status_label)}
                </StatusBadge>
                <SlaBadge
                  dueBy={selected.due_by}
                  ageHours={selected.age_hours}
                  isOverdue={selected.is_overdue}
                />
                <ClaimBadge claimedBy={selected.claimed_by} isMine={selected.claimed_by === userId} />
              </div>
            </div>

            <Field label={tj("employmentType")}>
              {labels.employmentType(selected.employment_type, selected.employment_type_label)}
              {" · "}
              {labels.locationType(selected.location_type, selected.location_type_label)}
            </Field>
            <Field label={tj("location")}>
              {formatLocation(selected.location_city, selected.location_country)}
            </Field>
            <Field label={tj("salary")}>
              {formatSalary(selected.salary, locale) ?? tj("salaryUndisclosed")}
            </Field>
            <Field label={tj("visibilityLabel")}>{labels.visibility(selected.visibility)}</Field>

            {/* Full detail (when the moderator can read it). */}
            {detailQuery.isPending ? (
              <p className="text-sm text-[var(--text-muted)]">{tc("loading")}</p>
            ) : detail ? (
              <>
                <Field label={tj("description")}>
                  <span className="whitespace-pre-wrap">{detail.description}</span>
                </Field>
                {detail.requirements && (
                  <Field label={tj("requirements")}>
                    <span className="whitespace-pre-wrap">{detail.requirements}</span>
                  </Field>
                )}
                {detail.required_skills.length > 0 && (
                  <Field label={tj("requiredSkills")}>
                    {detail.required_skills.join(", ")}
                  </Field>
                )}
                {detail.screening_questions.length > 0 && (
                  <Field label={tj("screeningQuestions")}>
                    <ol className="list-decimal space-y-1 pl-4">
                      {detail.screening_questions.map((q) => (
                        <li key={q.id}>{q.question}</li>
                      ))}
                    </ol>
                  </Field>
                )}
              </>
            ) : (
              <p className="rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-xs text-[var(--text-muted)] ">
                {t("detailUnavailable")}
              </p>
            )}

            {isPending ? (
              <div className="flex flex-col gap-2 pt-2">
                {canClaim && (
                  <Button
                    variant="secondary"
                    fullWidth
                    loading={claim.isPending}
                    onClick={() => claim.mutate(selected)}
                  >
                    <UserCheck aria-hidden weight="bold" className="size-4" />
                    {tm("moderationQueue.claim")}
                  </Button>
                )}
                <Button variant="primary" fullWidth onClick={() => setApproveOpen(true)}>
                  <CheckCircle aria-hidden weight="bold" className="size-4" />
                  {t("approve")}
                </Button>
                <Button
                  variant="danger"
                  fullWidth
                  onClick={() => {
                    setReason("");
                    setReasonCode("other");
                    setReasonError(null);
                    setRejectOpen(true);
                  }}
                >
                  <XCircle aria-hidden weight="bold" className="size-4" />
                  {t("reject")}
                </Button>
                {canEscalate && (
                  <Button
                    variant="ghost"
                    fullWidth
                    onClick={() => {
                      setEscalateNote("");
                      setEscalateReasonCode("policy_violation");
                      setEscalateOpen(true);
                    }}
                  >
                    <Flag aria-hidden weight="bold" className="size-4" />
                    {tm("moderationQueue.escalate")}
                  </Button>
                )}
              </div>
            ) : (
              <p className="rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-sm text-[var(--text-secondary)] ">
                {t("notPending")}
              </p>
            )}
          </div>
        )}
      </Sheet>

      {/* Approve modal */}
      <Modal
        open={approveOpen}
        onClose={() => setApproveOpen(false)}
        title={t("approveTitle")}
        description={t("approveBody", { title: selected?.title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setApproveOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={approve.isPending}
              onClick={() => selected && approve.mutate(selected)}
            >
              {t("approveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("approveNote")}</p>
      </Modal>

      {/* Reject modal */}
      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title={t("rejectTitle")}
        description={t("rejectBody", { title: selected?.title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={reject.isPending}
              onClick={() => {
                if (!reason.trim()) {
                  setReasonError(t("reasonRequired"));
                  return;
                }
                if (selected) reject.mutate(selected);
              }}
            >
              {t("rejectConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect
            id="reject-reason-code"
            value={reasonCode}
            onChange={setReasonCode}
          />
          <div>
            <label
              htmlFor="reject-reason"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("reasonLabel")}
              <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
                *
              </span>
            </label>
            <textarea
              id="reject-reason"
              rows={3}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                if (reasonError) setReasonError(null);
              }}
              aria-invalid={reasonError ? true : undefined}
              aria-describedby={reasonError ? "reject-reason-error" : undefined}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
            {reasonError && (
              <p id="reject-reason-error" className="mt-1 text-xs font-medium text-[var(--brand-red)]">
                {reasonError}
              </p>
            )}
            <p className="mt-2 text-xs text-[var(--text-muted)]">{t("reasonHint")}</p>
          </div>
        </div>
      </Modal>

      {/* Escalate modal */}
      <Modal
        open={escalateOpen}
        onClose={() => setEscalateOpen(false)}
        title={tm("moderationQueue.escalateTitle")}
        description={tm("moderationQueue.escalateBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEscalateOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={escalate.isPending}
              onClick={() => selected && escalate.mutate(selected)}
            >
              {tm("moderationQueue.escalateConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect
            id="escalate-reason-code"
            value={escalateReasonCode}
            onChange={setEscalateReasonCode}
          />
          <div>
            <label
              htmlFor="escalate-note"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {tm("moderationQueue.otherNoteLabel")}
            </label>
            <textarea
              id="escalate-note"
              rows={3}
              value={escalateNote}
              onChange={(e) => setEscalateNote(e.target.value)}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
          </div>
        </div>
      </Modal>

      {/* Bulk approve confirm */}
      <Modal
        open={bulkKind === "approve"}
        onClose={() => setBulkKind(null)}
        title={tm("moderationQueue.bulkApproveTitle", { count: selectedIds.size })}
        description={tm("moderationQueue.bulkApproveBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setBulkKind(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={bulkApprove.isPending}
              onClick={() => bulkApprove.mutate(Array.from(selectedIds))}
            >
              {tm("moderationQueue.bulkApproveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("approveNote")}</p>
      </Modal>

      {/* Bulk reject confirm */}
      <Modal
        open={bulkKind === "reject"}
        onClose={() => setBulkKind(null)}
        title={tm("moderationQueue.bulkRejectTitle", { count: selectedIds.size })}
        description={tm("moderationQueue.bulkRejectBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setBulkKind(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={bulkReject.isPending}
              onClick={() => {
                if (!reason.trim()) {
                  setReasonError(t("reasonRequired"));
                  return;
                }
                bulkReject.mutate(Array.from(selectedIds));
              }}
            >
              {tm("moderationQueue.bulkRejectConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect
            id="bulk-reject-reason-code"
            value={reasonCode}
            onChange={setReasonCode}
          />
          <div>
            <label
              htmlFor="bulk-reject-reason"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("reasonLabel")}
              <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
                *
              </span>
            </label>
            <textarea
              id="bulk-reject-reason"
              rows={3}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                if (reasonError) setReasonError(null);
              }}
              aria-invalid={reasonError ? true : undefined}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
            {reasonError && (
              <p className="mt-1 text-xs font-medium text-[var(--brand-red)]">{reasonError}</p>
            )}
          </div>
        </div>
      </Modal>

      {/* Bulk result (partial success is normal) */}
      <Modal
        open={bulkResults !== null}
        onClose={() => setBulkResults(null)}
        title={tm("moderationQueue.bulkResultTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <Button variant="primary" onClick={() => setBulkResults(null)}>
            {tm("moderationQueue.bulkResultClose")}
          </Button>
        }
      >
        {bulkResults && (
          <BulkResultList
            results={bulkResults}
            getLabel={(id) => rows.find((r) => r.id === id)?.title ?? id}
          />
        )}
      </Modal>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <div className="mt-0.5 text-sm text-[var(--text-primary)]">{children}</div>
    </div>
  );
}
