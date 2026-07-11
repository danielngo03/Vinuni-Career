"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarX,
  Check,
  Clock,
  Flag,
  UserCheck,
  X,
} from "lucide-react";
import { Button, Modal, useToast } from "@/components/ui";
import {
  DataTable,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  FilterBar,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import { ModerationTabs } from "@/components/moderation/moderation-tabs";
import { BulkResultList, ReasonCodeSelect } from "@/components/moderation/queue-controls";
import { useAuthStore } from "@/stores/auth-store";
import { useEventLabels } from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import {
  ApiError,
  eventsApi,
  type BulkModerationResultItem,
  type EventModerationStatus,
  type EventStatus,
  type ModerationReasonCode,
  type OwnerEventSummary,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const STATUS_FILTERS = ["pending_review", "published", "rejected", "cancelled"] as const;

const EVENT_STATUS_CHIP: Record<EventStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  published: "success",
  cancelled: "neutral",
  completed: "success",
  rejected: "danger",
};

const EVENT_MODERATION_CHIP: Record<EventModerationStatus, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  flagged: "info",
};

type BulkKind = "approve" | "reject" | null;

/* SLA / claim chips (v10, StatusChip-based). */
function SlaChip({
  dueBy,
  ageHours,
  isOverdue,
}: {
  dueBy?: string | null;
  ageHours?: number | null;
  isOverdue?: boolean;
}) {
  const t = useTranslations("common");
  if (dueBy == null && ageHours == null) return null;
  const label = isOverdue
    ? t("moderationQueue.slaOverdue", { hours: Math.round(ageHours ?? 0) })
    : t("moderationQueue.slaAge", { hours: Math.round(ageHours ?? 0) });
  return (
    <StatusChip tone={isOverdue ? "danger" : "warning"} size="sm">
      <Clock aria-hidden className="size-3" strokeWidth={2} />
      {label}
    </StatusChip>
  );
}

function ClaimChip({ claimedBy, isMine }: { claimedBy?: string | null; isMine: boolean }) {
  const t = useTranslations("common");
  if (!claimedBy) return null;
  return (
    <StatusChip tone="info" size="sm">
      <UserCheck aria-hidden className="size-3" strokeWidth={2} />
      {isMine ? t("moderationQueue.claimedByMe") : t("moderationQueue.claimedByOther")}
    </StatusChip>
  );
}

export function EventModerationScreen() {
  const t = useTranslations("eventsModeration");
  const te = useTranslations("eventsManage");
  const tm = useTranslations("common");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();
  const userId = useAuthStore((s) => s.user?.id);

  const [statusFilter, setStatusFilter] = React.useState<string>("pending_review");
  const [selected, setSelected] = React.useState<OwnerEventSummary | null>(null);
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
  const [bulkIds, setBulkIds] = React.useState<string[]>([]);
  const bulkClearRef = React.useRef<() => void>(() => {});
  const [bulkResults, setBulkResults] = React.useState<BulkModerationResultItem[] | null>(null);

  const query = useQuery({
    queryKey: ["admin", "events", statusFilter],
    queryFn: () => eventsApi.listModeration(statusFilter),
    retry: false,
  });

  const detailQuery = useQuery({
    queryKey: ["admin", "events", "detail", selected?.id],
    queryFn: () => eventsApi.getOwned(selected!.id),
    enabled: selected !== null,
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "events"] });
  }

  function handleError(e: unknown) {
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
  }

  const approve = useMutation({
    mutationFn: (ev: OwnerEventSummary) => eventsApi.approve(ev.id),
    onSuccess: () => {
      setApproveOpen(false);
      setSelected(null);
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reject = useMutation({
    mutationFn: (ev: OwnerEventSummary) => eventsApi.reject(ev.id, reason, ev.version, reasonCode),
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
    mutationFn: (ev: OwnerEventSummary) => eventsApi.claim(ev.id),
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
    mutationFn: (ev: OwnerEventSummary) =>
      eventsApi.escalate(ev.id, {
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
    mutationFn: (ids: string[]) => eventsApi.bulkApprove(ids),
    onSuccess: (results) => {
      setBulkKind(null);
      setBulkResults(results);
      bulkClearRef.current();
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const bulkReject = useMutation({
    mutationFn: (ids: string[]) =>
      eventsApi.bulkReject(ids.map((id) => ({ id, reason, reason_code: reasonCode }))),
    onSuccess: (results) => {
      setBulkKind(null);
      setBulkResults(results);
      bulkClearRef.current();
      setReason("");
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const isPermissionError =
    query.isError &&
    query.error instanceof ApiError &&
    (query.error.isPermissionError || query.error.isAuthError);

  const rows = query.data ?? [];
  const detail = detailQuery.data;
  const isPending = selected?.status === "pending_review";
  const canClaim = isPending && selected != null && !selected.claimed_by;
  const sheetOpen = selected !== null && !approveOpen && !rejectOpen && !escalateOpen;

  const columns: ColumnDef<OwnerEventSummary, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colEvent"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-foreground">{row.original.title}</p>
          <p className="truncate type-caption text-muted-foreground">
            {labels.eventType(row.original.event_type, row.original.event_type_label)}
            {" · "}
            {labels.format(row.original.format, row.original.format_label)}
          </p>
        </div>
      ),
    },
    {
      id: "when",
      header: t("colWhen"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {formatEventWhen(row.original.starts_at, row.original.ends_at, locale)}
        </span>
      ),
    },
    {
      id: "sla",
      header: t("colSla"),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-1">
          <SlaChip dueBy={row.original.due_by} ageHours={row.original.age_hours} isOverdue={row.original.is_overdue} />
          <ClaimChip claimedBy={row.original.claimed_by} isMine={row.original.claimed_by === userId} />
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={EVENT_STATUS_CHIP[row.original.status] ?? "neutral"}>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <Button variant="ghost" size="sm" onClick={() => setSelected(row.original)}>
          {t("review")}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ModerationTabs />

      {isPermissionError ? (
        <EmptyState
          kind={query.error instanceof ApiError && query.error.isPermissionError ? "permission" : "auth"}
          title={
            query.error instanceof ApiError && query.error.isPermissionError
              ? tStates("permissionTitle")
              : tStates("authTitle")
          }
          description={
            query.error instanceof ApiError && query.error.isPermissionError
              ? t("permissionBody")
              : tStates("authBody")
          }
        />
      ) : (
        <div className="space-y-4">
          <FilterBar>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterLabel")}>
              {STATUS_FILTERS.map((s) => {
                const active = statusFilter === s;
                return (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setStatusFilter(s)}
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                      active
                        ? "border-transparent bg-foreground text-[var(--surface-card)]"
                        : "border-border bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {labels.status(s)}
                  </button>
                );
              })}
            </div>
          </FilterBar>

          {query.isError && !isPermissionError ? (
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
              onRowClick={(r) => setSelected(r)}
              activeRowId={selected?.id ?? undefined}
              enableSelection={statusFilter === "pending_review"}
              bulkActions={(selectedRows, clear) => (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setBulkIds(selectedRows.map((r) => r.id));
                      bulkClearRef.current = clear;
                      setReason("");
                      setReasonCode("other");
                      setReasonError(null);
                      setBulkKind("reject");
                    }}
                  >
                    <X className="size-4" strokeWidth={1.9} />
                    {tm("moderationQueue.bulkReject")}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setBulkIds(selectedRows.map((r) => r.id));
                      bulkClearRef.current = clear;
                      setBulkKind("approve");
                    }}
                  >
                    <Check className="size-4" strokeWidth={1.9} />
                    {tm("moderationQueue.bulkApprove")}
                  </Button>
                </>
              )}
              empty={<EmptyState kind="empty" icon={CalendarX} title={t("empty")} description={t("emptyBody")} />}
            />
          )}
        </div>
      )}

      {/* Review drawer */}
      <DetailSheet
        open={sheetOpen}
        onClose={() => setSelected(null)}
        title={selected?.title ?? t("reviewTitle")}
        subtitle={
          selected
            ? `${labels.eventType(selected.event_type, selected.event_type_label)} · ${labels.format(selected.format, selected.format_label)}`
            : undefined
        }
        status={
          selected ? (
            <>
              <StatusChip tone={EVENT_STATUS_CHIP[selected.status] ?? "neutral"}>
                {labels.status(selected.status, selected.status_label)}
              </StatusChip>
              <StatusChip tone={EVENT_MODERATION_CHIP[selected.moderation_status] ?? "neutral"}>
                {labels.moderation(selected.moderation_status, selected.moderation_status_label)}
              </StatusChip>
              <SlaChip dueBy={selected.due_by} ageHours={selected.age_hours} isOverdue={selected.is_overdue} />
              <ClaimChip claimedBy={selected.claimed_by} isMine={selected.claimed_by === userId} />
            </>
          ) : undefined
        }
        width="lg"
        closeLabel={tc("close")}
      >
        {selected && (
          <>
            <DetailSheetSection title={te("type")}>
              <p className="text-sm text-foreground">
                {labels.eventType(selected.event_type, selected.event_type_label)}
                {" · "}
                {labels.format(selected.format, selected.format_label)}
              </p>
            </DetailSheetSection>
            <DetailSheetSection title={te("when")}>
              <p className="text-sm text-foreground">
                {formatEventWhen(selected.starts_at, selected.ends_at, locale)}
              </p>
            </DetailSheetSection>
            <DetailSheetSection title={te("where")}>
              <p className="text-sm text-foreground">
                {selected.format === "online"
                  ? te("onlineEvent")
                  : selected.venue
                    ? [selected.venue.name, selected.venue.address].filter(Boolean).join(" · ") || "—"
                    : "—"}
              </p>
            </DetailSheetSection>
            <DetailSheetSection title={te("capacity")}>
              <p className="text-sm text-foreground">
                {selected.capacity != null ? selected.capacity : te("unlimited")}
              </p>
            </DetailSheetSection>
            <DetailSheetSection title={te("visibilityLabel")}>
              <p className="text-sm text-foreground">{labels.visibility(selected.visibility)}</p>
            </DetailSheetSection>

            <DetailSheetSection title={te("about")}>
              {detailQuery.isPending ? (
                <div className="h-16 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
              ) : detail ? (
                <p className="whitespace-pre-wrap text-sm text-foreground">{detail.description}</p>
              ) : (
                <p className="type-small text-muted-foreground">{t("detailUnavailable")}</p>
              )}
            </DetailSheetSection>

            <DetailSheetSection>
              {isPending ? (
                <div className="flex flex-col gap-2">
                  {canClaim && (
                    <Button variant="secondary" fullWidth loading={claim.isPending} onClick={() => claim.mutate(selected)}>
                      <UserCheck className="size-4" strokeWidth={1.9} />
                      {tm("moderationQueue.claim")}
                    </Button>
                  )}
                  <Button variant="primary" fullWidth onClick={() => setApproveOpen(true)}>
                    <Check className="size-4" strokeWidth={1.9} />
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
                    <X className="size-4" strokeWidth={1.9} />
                    {t("reject")}
                  </Button>
                  <Button
                    variant="ghost"
                    fullWidth
                    onClick={() => {
                      setEscalateNote("");
                      setEscalateReasonCode("policy_violation");
                      setEscalateOpen(true);
                    }}
                  >
                    <Flag className="size-4" strokeWidth={1.9} />
                    {tm("moderationQueue.escalate")}
                  </Button>
                </div>
              ) : (
                <p className="type-small text-muted-foreground">{t("notPending")}</p>
              )}
            </DetailSheetSection>
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
          <ReasonCodeSelect id="event-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <RejectReasonField
            id="event-reject-reason"
            label={t("reasonLabel")}
            hint={t("reasonHint")}
            value={reason}
            error={reasonError}
            onChange={(v) => {
              setReason(v);
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
          <ReasonCodeSelect id="event-escalate-reason-code" value={escalateReasonCode} onChange={setEscalateReasonCode} />
          <RejectReasonField
            id="event-escalate-note"
            label={tm("moderationQueue.otherNoteLabel")}
            value={escalateNote}
            onChange={setEscalateNote}
          />
        </div>
      </Modal>

      {/* Bulk approve confirm */}
      <Modal
        open={bulkKind === "approve"}
        onClose={() => setBulkKind(null)}
        title={tm("moderationQueue.bulkApproveTitle", { count: bulkIds.length })}
        description={tm("moderationQueue.bulkApproveBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setBulkKind(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={bulkApprove.isPending} onClick={() => bulkApprove.mutate(bulkIds)}>
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
        title={tm("moderationQueue.bulkRejectTitle", { count: bulkIds.length })}
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
                bulkReject.mutate(bulkIds);
              }}
            >
              {tm("moderationQueue.bulkRejectConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect id="event-bulk-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <RejectReasonField
            id="event-bulk-reject-reason"
            label={t("reasonLabel")}
            value={reason}
            error={reasonError}
            onChange={(v) => {
              setReason(v);
              if (reasonError) setReasonError(null);
            }}
          />
        </div>
      </Modal>

      {/* Bulk result */}
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
          <BulkResultList results={bulkResults} getLabel={(id) => rows.find((r) => r.id === id)?.title ?? id} />
        )}
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Shared reason textarea (v10 field treatment)                                */
/* -------------------------------------------------------------------------- */

function RejectReasonField({
  id,
  label,
  value,
  onChange,
  error,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  hint?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-foreground">
        {label}
      </label>
      <textarea
        id={id}
        rows={3}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className="w-full rounded-lg border border-border bg-card px-3.5 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-[var(--field-focus-border)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]/30"
      />
      {error ? (
        <p id={`${id}-error`} className="mt-1 type-caption font-medium text-[var(--content-danger)]">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 type-caption text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
