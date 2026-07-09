"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Check,
  CircleDollarSign,
  Clock,
  Flag,
  Hourglass,
  Megaphone,
  ShieldCheck,
  ShieldX,
  UserCheck,
  X,
} from "lucide-react";
import { Button, Input, Modal, useToast } from "@/components/ui";
import {
  DataTable,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  FilterBar,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import { BulkResultList, ReasonCodeSelect } from "@/components/moderation/queue-controls";
import { useAuthStore } from "@/stores/auth-store";
import { useAdvertisingLabels } from "@/lib/advertising/labels";
import { formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  advertisingApi,
  type BulkModerationResultItem,
  type ModerationReasonCode,
  type Placement,
  type PlacementStatus,
  type PlacementType,
} from "@/lib/api";
import { CreativeModerationPanel } from "./creative-moderation-panel";

const STATUS_FILTERS = [
  "all",
  "pending_approval",
  "approved",
  "active",
  "completed",
  "rejected",
  "cancelled",
] as const;

const STATUS_CHIP: Record<PlacementStatus, ChipTone> = {
  draft: "neutral",
  pending_approval: "warning",
  approved: "info",
  active: "success",
  completed: "success",
  rejected: "danger",
  cancelled: "neutral",
};

const TYPE_CHIP: Record<PlacementType, ChipTone> = {
  sponsored: "amber",
  featured: "indigo",
  both: "violet",
};

type DialogKind = "approve" | "reject" | "markPaid" | "disable" | "escalate" | null;
type BulkKind = "approve" | "reject" | null;

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

export function AdvertisingOversightScreen() {
  const t = useTranslations("advertisingOversight");
  const ta = useTranslations("advertising");
  const tm = useTranslations("common");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useAdvertisingLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();
  const userId = useAuthStore((s) => s.user?.id);

  const [statusFilter, setStatusFilter] = React.useState<string>("pending_approval");
  const [selected, setSelected] = React.useState<Placement | null>(null);
  const [dialog, setDialog] = React.useState<DialogKind>(null);
  const [reason, setReason] = React.useState("");
  const [reasonCode, setReasonCode] = React.useState<ModerationReasonCode | string>("other");
  const [escalateReasonCode, setEscalateReasonCode] =
    React.useState<ModerationReasonCode | string>("policy_violation");
  const [paymentRef, setPaymentRef] = React.useState("");
  const [textError, setTextError] = React.useState<string | null>(null);

  const [bulkKind, setBulkKind] = React.useState<BulkKind>(null);
  const [bulkIds, setBulkIds] = React.useState<string[]>([]);
  const bulkClearRef = React.useRef<() => void>(() => {});
  const [bulkResults, setBulkResults] = React.useState<BulkModerationResultItem[] | null>(null);

  const query = useQuery({
    queryKey: ["admin", "advertising", statusFilter],
    queryFn: () =>
      advertisingApi.listAllPlacements({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "advertising"] });
  }

  function closeDialog() {
    setDialog(null);
    setReason("");
    setPaymentRef("");
    setTextError(null);
  }

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: ta("errors.conflictTitle"), description: ta("errors.conflictBody") });
      closeDialog();
      setSelected(null);
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const approve = useMutation({
    mutationFn: (p: Placement) => advertisingApi.approvePlacement(p.id, { version: p.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reject = useMutation({
    mutationFn: (p: Placement) => advertisingApi.rejectPlacement(p.id, reason, p.version, reasonCode),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleError,
  });

  const markPaid = useMutation({
    mutationFn: (p: Placement) => advertisingApi.markPaid(p.id, paymentRef, p.version),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("paidToast") });
      refresh();
    },
    onError: handleError,
  });

  const disable = useMutation({
    mutationFn: (p: Placement) =>
      advertisingApi.disablePlacement(p.id, { reason: reason.trim() || undefined, version: p.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("disabledToast") });
      refresh();
    },
    onError: handleError,
  });

  const claim = useMutation({
    mutationFn: (p: Placement) => advertisingApi.claimPlacement(p.id),
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
    mutationFn: (p: Placement) =>
      advertisingApi.escalatePlacement(p.id, {
        reason_code: escalateReasonCode,
        note: reason.trim() || undefined,
      }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: tm("moderationQueue.escalatedToast") });
      refresh();
    },
    onError: handleError,
  });

  const bulkApprove = useMutation({
    mutationFn: (ids: string[]) => advertisingApi.bulkApprovePlacements(ids),
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
      advertisingApi.bulkRejectPlacements(ids.map((id) => ({ id, reason, reason_code: reasonCode }))),
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

  const rows = query.data?.items ?? [];
  const spend = query.data?.spend ?? null;
  const selectedLive = selected ? (rows.find((r) => r.id === selected.id) ?? selected) : null;

  const columns: ColumnDef<Placement, unknown>[] = [
    {
      id: "target",
      header: t("colTarget"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-foreground">
            {row.original.target_title ?? ta("targetUnavailable")}
          </p>
          <p className="truncate type-caption text-muted-foreground">
            {t("orgRef", { id: row.original.org_id.slice(0, 8) })}
            {" · "}
            {labels.targetType(row.original.target_type, row.original.target_type_label)}
          </p>
        </div>
      ),
    },
    {
      id: "package",
      header: t("colPackage"),
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-1">
          <StatusChip tone={TYPE_CHIP[row.original.placement_type] ?? "neutral"} dot>
            {labels.placementType(row.original.placement_type, row.original.placement_type_label)}
          </StatusChip>
          <span className="type-caption text-muted-foreground">{row.original.package?.name ?? "—"}</span>
        </div>
      ),
    },
    {
      id: "price",
      header: t("colPrice"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex flex-col items-end">
          <span className="font-semibold tabular-nums text-foreground">
            {formatVnd(row.original.price_amount, row.original.currency, locale)}
          </span>
          <span
            className="type-caption font-medium"
            style={{ color: row.original.is_paid ? "var(--content-success)" : "var(--content-warning)" }}
          >
            {row.original.is_paid ? t("paid") : t("unpaid")}
          </span>
        </div>
      ),
    },
    {
      id: "window",
      header: t("colWindow"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {formatWindow(row.original.start_at, row.original.end_at, locale)}
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
        <StatusChip tone={STATUS_CHIP[row.original.status] ?? "neutral"}>
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

  const canApprove = selectedLive?.status === "pending_approval";
  const canMarkPaid = selectedLive?.status === "pending_approval" || selectedLive?.status === "approved";
  const canDisable =
    selectedLive != null && ["pending_approval", "approved", "active"].includes(selectedLive.status);
  const canClaim = canApprove && selectedLive != null && !selectedLive.claimed_by;

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <KpiTile
              label={t("spendActive")}
              value={spend ? formatVnd(spend.active_spend_amount, spend.currency, locale) : "—"}
              icon={CircleDollarSign}
            />
            <KpiTile
              label={t("spendActiveCount")}
              value={spend ? String(spend.active_count) : "—"}
              icon={Megaphone}
            />
            <KpiTile
              label={t("spendPending")}
              value={spend ? String(spend.pending_approval_count) : "—"}
              icon={Hourglass}
            />
          </div>

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
                    {s === "all" ? ta("filterAllStatuses") : labels.status(s)}
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
              enableSelection={statusFilter === "pending_approval"}
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
                      setTextError(null);
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
              empty={<EmptyState kind="empty" icon={Megaphone} title={t("empty")} description={t("emptyBody")} />}
            />
          )}
        </div>
      )}

      {/* Review + action drawer */}
      <DetailSheet
        open={selectedLive !== null && dialog === null && bulkKind === null}
        onClose={() => setSelected(null)}
        title={selectedLive?.target_title ?? ta("targetUnavailable")}
        subtitle={
          selectedLive
            ? labels.targetType(selectedLive.target_type, selectedLive.target_type_label)
            : undefined
        }
        status={
          selectedLive ? (
            <>
              <StatusChip tone={STATUS_CHIP[selectedLive.status] ?? "neutral"}>
                {labels.status(selectedLive.status, selectedLive.status_label)}
              </StatusChip>
              <StatusChip tone={TYPE_CHIP[selectedLive.placement_type] ?? "neutral"} dot>
                {labels.placementType(selectedLive.placement_type, selectedLive.placement_type_label)}
              </StatusChip>
              <SlaChip dueBy={selectedLive.due_by} ageHours={selectedLive.age_hours} isOverdue={selectedLive.is_overdue} />
              <ClaimChip claimedBy={selectedLive.claimed_by} isMine={selectedLive.claimed_by === userId} />
            </>
          ) : undefined
        }
        width="lg"
        closeLabel={tc("close")}
      >
        {selectedLive && (
          <>
            <DetailSheetSection>
              <dl>
                <DetailRow label={t("fieldOrg")}>
                  <span className="font-mono text-xs">{selectedLive.org_id.slice(0, 8)}</span>
                </DetailRow>
                <DetailRow label={t("fieldTargetType")}>
                  {labels.targetType(selectedLive.target_type, selectedLive.target_type_label)}
                </DetailRow>
                <DetailRow label={t("colPackage")}>{selectedLive.package?.name ?? "—"}</DetailRow>
                <DetailRow label={t("colPrice")}>
                  <span className="tabular-nums">
                    {formatVnd(selectedLive.price_amount, selectedLive.currency, locale)}
                  </span>{" "}
                  <span style={{ color: selectedLive.is_paid ? "var(--content-success)" : "var(--content-warning)" }}>
                    ({selectedLive.is_paid ? t("paid") : t("unpaid")})
                  </span>
                </DetailRow>
                <DetailRow label={t("colWindow")}>
                  {formatWindow(selectedLive.start_at, selectedLive.end_at, locale)}
                </DetailRow>
              </dl>
            </DetailSheetSection>

            {/* Disclosure enforcement */}
            <DetailSheetSection title={t("fieldDisclosure")}>
              {selectedLive.disclosure_confirmed ? (
                <StatusChip tone="success">
                  <ShieldCheck aria-hidden className="size-3.5" strokeWidth={2} />
                  {t("disclosureOk")}
                </StatusChip>
              ) : (
                <StatusChip tone="danger">
                  <ShieldX aria-hidden className="size-3.5" strokeWidth={2} />
                  {t("disclosureMissing")}
                </StatusChip>
              )}
              {selectedLive.payment_reference && (
                <p className="mt-2 type-small text-muted-foreground">
                  {t("fieldPaymentRef")}: <span className="font-mono">{selectedLive.payment_reference}</span>
                </p>
              )}
              {selectedLive.moderation_note && (
                <p className="mt-2 whitespace-pre-wrap type-small text-muted-foreground">
                  {t("fieldNote")}: {selectedLive.moderation_note}
                </p>
              )}
            </DetailSheetSection>

            {/* Actions */}
            <DetailSheetSection>
              <div className="flex flex-col gap-2">
                {canClaim && (
                  <Button variant="secondary" fullWidth loading={claim.isPending} onClick={() => claim.mutate(selectedLive)}>
                    <UserCheck className="size-4" strokeWidth={1.9} />
                    {tm("moderationQueue.claim")}
                  </Button>
                )}
                {canApprove && (
                  <Button variant="primary" fullWidth onClick={() => setDialog("approve")}>
                    <Check className="size-4" strokeWidth={1.9} />
                    {t("approve")}
                  </Button>
                )}
                {canMarkPaid && (
                  <Button
                    variant="secondary"
                    fullWidth
                    onClick={() => {
                      setPaymentRef("");
                      setTextError(null);
                      setDialog("markPaid");
                    }}
                  >
                    <CircleDollarSign className="size-4" strokeWidth={1.9} />
                    {selectedLive.is_paid ? t("updatePayment") : t("markPaid")}
                  </Button>
                )}
                {canApprove && (
                  <Button
                    variant="danger"
                    fullWidth
                    onClick={() => {
                      setReason("");
                      setReasonCode("other");
                      setTextError(null);
                      setDialog("reject");
                    }}
                  >
                    <X className="size-4" strokeWidth={1.9} />
                    {t("reject")}
                  </Button>
                )}
                {canApprove && (
                  <Button
                    variant="ghost"
                    fullWidth
                    onClick={() => {
                      setReason("");
                      setEscalateReasonCode("policy_violation");
                      setTextError(null);
                      setDialog("escalate");
                    }}
                  >
                    <Flag className="size-4" strokeWidth={1.9} />
                    {tm("moderationQueue.escalate")}
                  </Button>
                )}
                {canDisable && (
                  <Button
                    variant="ghost"
                    fullWidth
                    onClick={() => {
                      setReason("");
                      setTextError(null);
                      setDialog("disable");
                    }}
                  >
                    <Ban className="size-4" strokeWidth={1.9} />
                    {t("disable")}
                  </Button>
                )}
                {!canApprove && !canMarkPaid && !canDisable && (
                  <p className="type-small text-muted-foreground">{t("noActions")}</p>
                )}
              </div>
            </DetailSheetSection>

            {/* Creative moderation + disclosure relabel */}
            <DetailSheetSection>
              <CreativeModerationPanel placement={selectedLive} onChanged={() => setSelected(selectedLive)} />
            </DetailSheetSection>
          </>
        )}
      </DetailSheet>

      {/* Approve */}
      <Modal
        open={dialog === "approve"}
        onClose={closeDialog}
        title={t("approveTitle")}
        description={t("approveBody", { target: selectedLive?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={approve.isPending} onClick={() => selectedLive && approve.mutate(selectedLive)}>
              {t("approveConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t("approveNote")}</p>
      </Modal>

      {/* Reject */}
      <Modal
        open={dialog === "reject"}
        onClose={closeDialog}
        title={t("rejectTitle")}
        description={t("rejectBody", { target: selectedLive?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={reject.isPending}
              onClick={() => {
                if (!reason.trim()) {
                  setTextError(t("reasonRequired"));
                  return;
                }
                if (selectedLive) reject.mutate(selectedLive);
              }}
            >
              {t("rejectConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect id="ad-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <ReasonField
            id="ad-reject-reason"
            label={t("reasonLabel")}
            hint={t("reasonHint")}
            value={reason}
            error={textError}
            onChange={(v) => {
              setReason(v);
              if (textError) setTextError(null);
            }}
          />
        </div>
      </Modal>

      {/* Escalate */}
      <Modal
        open={dialog === "escalate"}
        onClose={closeDialog}
        title={tm("moderationQueue.escalateTitle")}
        description={tm("moderationQueue.escalateBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={escalate.isPending} onClick={() => selectedLive && escalate.mutate(selectedLive)}>
              {tm("moderationQueue.escalateConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect id="ad-escalate-reason-code" value={escalateReasonCode} onChange={setEscalateReasonCode} />
          <ReasonField id="ad-escalate-note" label={tm("moderationQueue.otherNoteLabel")} value={reason} onChange={setReason} />
        </div>
      </Modal>

      {/* Mark paid */}
      <Modal
        open={dialog === "markPaid"}
        onClose={closeDialog}
        title={t("markPaidTitle")}
        description={t("markPaidBody", { target: selectedLive?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={markPaid.isPending}
              onClick={() => {
                if (!paymentRef.trim()) {
                  setTextError(t("paymentRefRequired"));
                  return;
                }
                if (selectedLive) markPaid.mutate(selectedLive);
              }}
            >
              {t("markPaidConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("markPaidNote")}</p>
          <Input
            id="ad-payment-ref"
            label={t("paymentRefLabel")}
            required
            value={paymentRef}
            error={textError ?? undefined}
            onChange={(e) => {
              setPaymentRef(e.target.value);
              if (textError) setTextError(null);
            }}
            placeholder={t("paymentRefPlaceholder")}
            help={t("paymentRefHint")}
          />
        </div>
      </Modal>

      {/* Disable */}
      <Modal
        open={dialog === "disable"}
        onClose={closeDialog}
        title={t("disableTitle")}
        description={t("disableBody", { target: selectedLive?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={disable.isPending} onClick={() => selectedLive && disable.mutate(selectedLive)}>
              {t("disableConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("disableNote")}</p>
          <ReasonField
            id="ad-disable-reason"
            label={t("disableReasonLabel")}
            hint={t("disableReasonHint")}
            value={reason}
            onChange={setReason}
          />
        </div>
      </Modal>

      {/* Bulk approve */}
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

      {/* Bulk reject */}
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
                  setTextError(t("reasonRequired"));
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
          <ReasonCodeSelect id="ad-bulk-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <ReasonField
            id="ad-bulk-reject-reason"
            label={t("reasonLabel")}
            value={reason}
            error={textError}
            onChange={(v) => {
              setReason(v);
              if (textError) setTextError(null);
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
          <BulkResultList results={bulkResults} getLabel={(id) => rows.find((r) => r.id === id)?.target_title ?? id} />
        )}
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Shared reason textarea (v10 field treatment)                                */
/* -------------------------------------------------------------------------- */

function ReasonField({
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
