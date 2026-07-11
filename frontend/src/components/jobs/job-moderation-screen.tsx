"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Clock,
  Flag,
  ListChecks,
  UserCheck,
  UserPlus,
  X,
} from "lucide-react";
import { Button, Modal, Textarea, useToast, SegmentedControl } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { ModerationTabs } from "@/components/moderation/moderation-tabs";
import { ReasonCodeSelect } from "@/components/moderation/queue-controls";
import { useAuthStore } from "@/stores/auth-store";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { formatDateTime } from "@/lib/format";
import {
  ApiError,
  jobsApi,
  type BulkModerationResultItem,
  type JobStatus,
  type ModerationStatus,
  type ModerationReasonCode,
  type OwnerJobSummary,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const STATUS_FILTERS = ["pending_review", "active", "rejected", "closed"] as const;

const JOB_STATUS_CHIP: Record<JobStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  rejected: "danger",
  closed: "neutral",
  expired: "neutral",
};

const MODERATION_CHIP: Record<ModerationStatus, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  flagged: "amber",
};

type BulkKind = "approve" | "reject" | null;
type BulkSelection = { ids: string[]; clear: () => void };

/* -------------------------------------------------------------------------- */
/* Small chips                                                                 */
/* -------------------------------------------------------------------------- */

function SlaChip({ job }: { job: OwnerJobSummary }) {
  const t = useTranslations("common");
  if (job.due_by == null && job.age_hours == null) return null;
  const hours = Math.round(job.age_hours ?? 0);
  return (
    <StatusChip tone={job.is_overdue ? "danger" : "warning"} size="sm">
      <Clock aria-hidden className="size-3" strokeWidth={2} />
      {job.is_overdue
        ? t("moderationQueue.slaOverdue", { hours })
        : t("moderationQueue.slaAge", { hours })}
    </StatusChip>
  );
}

function ClaimChip({ job, userId }: { job: OwnerJobSummary; userId?: string }) {
  const t = useTranslations("common");
  if (!job.claimed_by) return null;
  return (
    <StatusChip tone="info" size="sm">
      <UserCheck aria-hidden className="size-3" strokeWidth={2} />
      {job.claimed_by === userId
        ? t("moderationQueue.claimedByMe")
        : t("moderationQueue.claimedByOther")}
    </StatusChip>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

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

  const [statusFilter, setStatusFilter] = React.useState<string>("pending_review");
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<OwnerJobSummary | null>(null);
  const [approveOpen, setApproveOpen] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [escalateOpen, setEscalateOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [reasonCode, setReasonCode] = React.useState<ModerationReasonCode | string>("other");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const [escalateNote, setEscalateNote] = React.useState("");
  const [escalateReasonCode, setEscalateReasonCode] =
    React.useState<ModerationReasonCode | string>("policy_violation");

  const [bulkKind, setBulkKind] = React.useState<BulkKind>(null);
  const [bulkSelection, setBulkSelection] = React.useState<BulkSelection | null>(null);
  const [bulkResults, setBulkResults] = React.useState<BulkModerationResultItem[] | null>(null);

  const query = useQuery({
    queryKey: ["admin", "jobs", statusFilter],
    queryFn: () => jobsApi.listModeration(statusFilter),
    retry: false,
  });

  // Dedicated pending read powers the KPI strip regardless of the active filter.
  const pendingQuery = useQuery({
    queryKey: ["admin", "jobs", "pending_review", "kpi"],
    queryFn: () => jobsApi.listModeration("pending_review"),
    retry: false,
    staleTime: 30_000,
  });

  // Full detail for the review drawer (superadmin/owner only; 404 otherwise).
  const detailQuery = useQuery({
    queryKey: ["admin", "jobs", "detail", selected?.id],
    queryFn: () => jobsApi.getOwned(selected!.id),
    enabled: selected !== null,
    retry: false,
  });

  const refresh = React.useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["admin", "jobs"] });
  }, [qc]);

  const handleError = React.useCallback(
    (e: unknown) => {
      const reason_ =
        e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reason_ === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
        toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
        setApproveOpen(false);
        setRejectOpen(false);
        setSelected(null);
        refresh();
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
    [getMessage, refresh, t, toast],
  );

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
    mutationFn: (job: OwnerJobSummary) => jobsApi.reject(job.id, reason, job.version, reasonCode),
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
      jobsApi.escalate(job.id, {
        reason_code: escalateReasonCode,
        note: escalateNote.trim() || undefined,
      }),
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
      bulkSelection?.clear();
      setBulkSelection(null);
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const bulkReject = useMutation({
    mutationFn: (ids: string[]) =>
      jobsApi.bulkReject(ids.map((id) => ({ id, reason, reason_code: reasonCode }))),
    onSuccess: (results) => {
      setBulkKind(null);
      setBulkResults(results);
      setReason("");
      bulkSelection?.clear();
      setBulkSelection(null);
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  // Sync buffers when the selected job changes.
  React.useEffect(() => {
    setReasonError(null);
  }, [selected]);

  const rows = query.data ?? [];
  const detail = detailQuery.data;
  const isPending = selected?.status === "pending_review";
  const canClaim = Boolean(isPending && selected && !selected.claimed_by);

  const pending = pendingQuery.data ?? [];
  const overdue = pending.filter((r) => r.is_overdue).length;
  const unclaimed = pending.filter((r) => !r.claimed_by).length;
  const mine = pending.filter((r) => r.claimed_by === userId).length;

  const selectionEnabled = statusFilter === "pending_review";

  const columns: ColumnDef<OwnerJobSummary, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colJob"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="min-w-0">
            <p className="truncate font-semibold text-foreground">{r.title}</p>
            <p className="truncate type-caption text-muted-foreground">
              {labels.employmentType(r.employment_type, r.employment_type_label)}
              {" · "}
              {formatLocation(r.location_city, r.location_country)}
            </p>
          </div>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: t("colSubmitted"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {formatDateTime(row.original.created_at, locale)}
        </span>
      ),
    },
    {
      id: "sla",
      header: t("colSla"),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-1">
          <SlaChip job={row.original} />
          <ClaimChip job={row.original} userId={userId} />
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={JOB_STATUS_CHIP[row.original.status] ?? "neutral"} dot>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
  ];

  const header = (
    <PageHeader title={t("title")} subtitle={t("subtitle")} />
  );

  /* ---- Permission / auth states (after hooks) ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <ModerationTabs />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const isHardError =
    query.isError &&
    !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError));

  return (
    <>
      {header}
      <ModerationTabs />

      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile label={t("kpiPending")} value={pendingQuery.isPending ? "—" : String(pending.length)} icon={ListChecks} />
          <KpiTile
            label={t("kpiOverdue")}
            value={pendingQuery.isPending ? "—" : String(overdue)}
            icon={AlertTriangle}
            hint={overdue > 0 ? t("overdueHint") : undefined}
          />
          <KpiTile label={t("kpiUnclaimed")} value={pendingQuery.isPending ? "—" : String(unclaimed)} icon={UserPlus} />
          <KpiTile label={t("kpiClaimedByMe")} value={pendingQuery.isPending ? "—" : String(mine)} icon={UserCheck} />
        </KpiRow>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("title")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <FilterBar
              search={{
                value: search,
                onChange: setSearch,
                placeholder: t("searchPlaceholder"),
              }}
            >
              <SegmentedControl
                ariaLabel={t("filterLabel")}
                value={statusFilter}
                onValueChange={setStatusFilter}
                size="sm"
                options={STATUS_FILTERS.map((s) => ({ value: s, label: tj(`enums.status.${s}`) }))}
              />
            </FilterBar>

            {isHardError ? (
              <EmptyState
                kind="error"
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
                data={rows}
                getRowId={(r) => r.id}
                loading={query.isPending}
                globalFilter={search}
                onRowClick={(r) => setSelected(r)}
                activeRowId={selected?.id}
                enableSelection={selectionEnabled}
                bulkActions={(sel, clear) => (
                  <>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        setReason("");
                        setReasonCode("other");
                        setReasonError(null);
                        setBulkSelection({ ids: sel.map((r) => r.id), clear });
                        setBulkKind("reject");
                      }}
                    >
                      <X className="size-4" strokeWidth={2} />
                      {tm("moderationQueue.bulkReject")}
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => {
                        setBulkSelection({ ids: sel.map((r) => r.id), clear });
                        setBulkKind("approve");
                      }}
                    >
                      <Check className="size-4" strokeWidth={2} />
                      {tm("moderationQueue.bulkApprove")}
                    </Button>
                  </>
                )}
                empty={<EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Review drawer */}
      <DetailSheet
        open={selected !== null && !approveOpen && !rejectOpen && !escalateOpen}
        onClose={() => setSelected(null)}
        title={selected?.title ?? ""}
        subtitle={
          selected
            ? `${labels.employmentType(selected.employment_type, selected.employment_type_label)} · ${labels.locationType(selected.location_type, selected.location_type_label)}`
            : undefined
        }
        closeLabel={tc("close")}
        width="lg"
        status={
          selected ? (
            <>
              <StatusChip tone={JOB_STATUS_CHIP[selected.status] ?? "neutral"} dot>
                {labels.status(selected.status, selected.status_label)}
              </StatusChip>
              <StatusChip tone={MODERATION_CHIP[selected.moderation_status] ?? "neutral"} dot>
                {labels.moderation(selected.moderation_status, selected.moderation_status_label)}
              </StatusChip>
              <SlaChip job={selected} />
              <ClaimChip job={selected} userId={userId} />
            </>
          ) : undefined
        }
        footer={
          selected && isPending ? (
            <>
              {canClaim && (
                <Button variant="secondary" size="sm" loading={claim.isPending} onClick={() => claim.mutate(selected)}>
                  <UserCheck className="size-4" strokeWidth={1.8} />
                  {tm("moderationQueue.claim")}
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEscalateNote("");
                  setEscalateReasonCode("policy_violation");
                  setEscalateOpen(true);
                }}
              >
                <Flag className="size-4" strokeWidth={1.8} />
                {tm("moderationQueue.escalate")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-[var(--content-danger)]"
                onClick={() => {
                  setReason("");
                  setReasonCode("other");
                  setReasonError(null);
                  setRejectOpen(true);
                }}
              >
                <X className="size-4" strokeWidth={1.8} />
                {t("reject")}
              </Button>
              <Button variant="primary" size="sm" onClick={() => setApproveOpen(true)}>
                <Check className="size-4" strokeWidth={2} />
                {t("approve")}
              </Button>
            </>
          ) : undefined
        }
      >
        {selected && (
          <>
            <DetailSheetSection title={t("sectionDetails")}>
              <dl className="space-y-2.5">
                <SheetField label={tj("salary")}>
                  {formatSalary(selected.salary, locale) ?? tj("salaryUndisclosed")}
                </SheetField>
                <SheetField label={tj("location")}>
                  {formatLocation(selected.location_city, selected.location_country)}
                </SheetField>
                <SheetField label={tj("visibilityLabel")}>{labels.visibility(selected.visibility)}</SheetField>
                <SheetField label={t("colSubmitted")}>{formatDateTime(selected.created_at, locale)}</SheetField>
              </dl>
            </DetailSheetSection>

            <DetailSheetSection title={t("sectionContent")}>
              {detailQuery.isPending ? (
                <div className="h-24 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
              ) : detail ? (
                <div className="space-y-3 text-[0.8125rem] text-foreground">
                  <p className="whitespace-pre-wrap">{detail.description}</p>
                  {detail.requirements && (
                    <div>
                      <p className="mb-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                        {tj("requirements")}
                      </p>
                      <p className="whitespace-pre-wrap">{detail.requirements}</p>
                    </div>
                  )}
                  {detail.required_skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {detail.required_skills.map((s) => (
                        <StatusChip key={s} tone="neutral" size="sm">
                          {s}
                        </StatusChip>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="type-small text-muted-foreground">{t("detailUnavailable")}</p>
              )}
            </DetailSheetSection>

            {!isPending && (
              <DetailSheetSection>
                <p className="type-small text-muted-foreground">{t("notPending")}</p>
              </DetailSheetSection>
            )}
          </>
        )}
      </DetailSheet>

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
            <Button variant="primary" loading={approve.isPending} onClick={() => selected && approve.mutate(selected)}>
              {t("approveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("approveNote")}</p>
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
          <ReasonCodeSelect id="reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <Textarea
            label={t("reasonLabel")}
            required
            rows={3}
            value={reason}
            error={reasonError ?? undefined}
            help={t("reasonHint")}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError(null);
            }}
          />
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
            <Button variant="primary" loading={escalate.isPending} onClick={() => selected && escalate.mutate(selected)}>
              {tm("moderationQueue.escalateConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect id="escalate-reason-code" value={escalateReasonCode} onChange={setEscalateReasonCode} />
          <Textarea
            label={tm("moderationQueue.otherNoteLabel")}
            rows={3}
            value={escalateNote}
            onChange={(e) => setEscalateNote(e.target.value)}
          />
        </div>
      </Modal>

      {/* Bulk approve confirm */}
      <Modal
        open={bulkKind === "approve"}
        onClose={() => setBulkKind(null)}
        title={tm("moderationQueue.bulkApproveTitle", { count: bulkSelection?.ids.length ?? 0 })}
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
              onClick={() => bulkSelection && bulkApprove.mutate(bulkSelection.ids)}
            >
              {tm("moderationQueue.bulkApproveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("approveNote")}</p>
      </Modal>

      {/* Bulk reject confirm */}
      <Modal
        open={bulkKind === "reject"}
        onClose={() => setBulkKind(null)}
        title={tm("moderationQueue.bulkRejectTitle", { count: bulkSelection?.ids.length ?? 0 })}
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
                if (bulkSelection) bulkReject.mutate(bulkSelection.ids);
              }}
            >
              {tm("moderationQueue.bulkRejectConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect id="bulk-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <Textarea
            label={t("reasonLabel")}
            required
            rows={3}
            value={reason}
            error={reasonError ?? undefined}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError(null);
            }}
          />
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
        {bulkResults && <BulkResult results={bulkResults} rows={rows} />}
      </Modal>
    </>
  );
}

function SheetField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="type-small shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right text-[0.8125rem] font-medium text-foreground">{children}</dd>
    </div>
  );
}

function BulkResult({
  results,
  rows,
}: {
  results: BulkModerationResultItem[];
  rows: OwnerJobSummary[];
}) {
  const t = useTranslations("common");
  const failed = results.filter((r) => !r.success);
  const succeeded = results.filter((r) => r.success);
  const label = (id: string) => rows.find((r) => r.id === id)?.title ?? id;
  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-foreground">
        {t("moderationQueue.bulkResultSummary", { success: succeeded.length, failed: failed.length })}
      </p>
      {failed.length > 0 && (
        <ul
          className="space-y-1.5 rounded-xl border p-3"
          style={{ borderColor: "var(--content-danger)", background: "var(--content-danger-soft)" }}
        >
          {failed.map((r) => (
            <li key={r.id} className="text-xs" style={{ color: "var(--content-danger)" }}>
              <span className="font-semibold">{label(r.id)}</span>
              {r.message ? `: ${r.message}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
