"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LightbulbFilament,
  Megaphone,
  CheckCircle,
  Flag,
  XCircle,
  CurrencyCircleDollar,
  Hourglass,
  Prohibit,
  ShieldWarning,
  SignIn,
  Sparkle,
  UserCheck,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Input,
  Modal,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import {
  BulkResultList,
  ClaimBadge,
  ReasonCodeSelect,
  RowSelectCheckbox,
  SlaBadge,
} from "@/components/moderation/queue-controls";
import { useAuthStore } from "@/stores/auth-store";
import {
  useAdvertisingLabels,
  PLACEMENT_STATUS_TONE,
  PLACEMENT_TYPE_TONE,
} from "@/lib/advertising/labels";
import { formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  advertisingApi,
  type BulkModerationResultItem,
  type ModerationReasonCode,
  type Placement,
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

type AdOversightInsightKey =
  | "insightPendingApproval"
  | "insightActiveCampaigns"
  | "insightNoActivity"
  | "insightHighSpend";

function deriveAdOversightInsights(
  activeCount: number,
  pendingCount: number,
  activeSpendStr: string,
): AdOversightInsightKey[] {
  const out: AdOversightInsightKey[] = [];
  const activeSpend = parseFloat(activeSpendStr) || 0;
  if (pendingCount > 0) out.push("insightPendingApproval");
  if (activeCount > 0) out.push("insightActiveCampaigns");
  if (activeCount === 0 && pendingCount === 0) out.push("insightNoActivity");
  if (activeSpend > 10_000_000) out.push("insightHighSpend");
  return out.slice(0, 2);
}

type DialogKind = "approve" | "reject" | "markPaid" | "disable" | "escalate" | null;
type BulkKind = "approve" | "reject" | null;

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

  const [statusFilter, setStatusFilter] = useState<string>("pending_approval");
  const [selected, setSelected] = useState<Placement | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [reason, setReason] = useState("");
  const [reasonCode, setReasonCode] = useState<ModerationReasonCode | string>("other");
  const [escalateReasonCode, setEscalateReasonCode] =
    useState<ModerationReasonCode | string>("policy_violation");
  const [paymentRef, setPaymentRef] = useState("");
  const [textError, setTextError] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkKind, setBulkKind] = useState<BulkKind>(null);
  const [bulkResults, setBulkResults] = useState<BulkModerationResultItem[] | null>(null);

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
    setSelected(null);
    setReason("");
    setPaymentRef("");
    setTextError(null);
  }

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({
        tone: "error",
        title: ta("errors.conflictTitle"),
        description: ta("errors.conflictBody"),
      });
      closeDialog();
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const approve = useMutation({
    mutationFn: (p: Placement) =>
      advertisingApi.approvePlacement(p.id, { version: p.version }),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reject = useMutation({
    mutationFn: (p: Placement) =>
      advertisingApi.rejectPlacement(p.id, reason, p.version, reasonCode),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleError,
  });

  const markPaid = useMutation({
    mutationFn: (p: Placement) =>
      advertisingApi.markPaid(p.id, paymentRef, p.version),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("paidToast") });
      refresh();
    },
    onError: handleError,
  });

  const disable = useMutation({
    mutationFn: (p: Placement) =>
      advertisingApi.disablePlacement(p.id, {
        reason: reason.trim() || undefined,
        version: p.version,
      }),
    onSuccess: () => {
      closeDialog();
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
      setSelectedIds(new Set());
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const bulkReject = useMutation({
    mutationFn: (ids: string[]) =>
      advertisingApi.bulkRejectPlacements(
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
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const rows = query.data?.items ?? [];
  const spend = query.data?.spend ?? null;
  /** Keep the open review panel bound to the freshest row (creatives/version). */
  const selectedLive = selected
    ? (rows.find((r) => r.id === selected.id) ?? selected)
    : null;

  function toggleRow(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const pendingRows = rows.filter((r) => r.status === "pending_approval");
  const allPendingSelected =
    pendingRows.length > 0 && pendingRows.every((r) => selectedIds.has(r.id));

  const columns: Column<Placement>[] = [
    {
      key: "select",
      header: "",
      className: "w-10",
      cell: (r) =>
        r.status === "pending_approval" ? (
          <RowSelectCheckbox
            checked={selectedIds.has(r.id)}
            onChange={(checked) => toggleRow(r.id, checked)}
            label={t("selectRow", { title: r.target_title ?? r.id })}
          />
        ) : null,
    },
    {
      key: "target",
      header: t("colTarget"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--text-primary)]">
            {r.target_title ?? ta("targetUnavailable")}
          </p>
          <p className="truncate font-mono text-[11px] text-[var(--text-muted)]">
            {t("orgRef", { id: r.org_id.slice(0, 8) })}
            {" · "}
            {labels.targetType(r.target_type, r.target_type_label)}
          </p>
        </div>
      ),
    },
    {
      key: "package",
      header: t("colPackage"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={PLACEMENT_TYPE_TONE[r.placement_type] ?? "info"}>
            {labels.placementType(r.placement_type, r.placement_type_label)}
          </StatusBadge>
          <span className="text-xs text-[var(--text-secondary)]">
            {r.package?.name ?? "—"}
          </span>
        </div>
      ),
    },
    {
      key: "price",
      header: t("colPrice"),
      cell: (r) => (
        <div className="flex flex-col">
          <span className="font-semibold text-[var(--text-primary)]">
            {formatVnd(r.price_amount, r.currency, locale)}
          </span>
          <span
            className={`text-[11px] font-medium ${
              r.is_paid ? "text-[var(--teal-600)]" : "text-[var(--amber-700)]"
            }`}
          >
            {r.is_paid ? t("paid") : t("unpaid")}
          </span>
        </div>
      ),
    },
    {
      key: "window",
      header: t("colWindow"),
      cell: (r) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {formatWindow(r.start_at, r.end_at, locale)}
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
        <StatusBadge tone={PLACEMENT_STATUS_TONE[r.status] ?? "info"}>
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

  const canApprove = selected?.status === "pending_approval";
  const canMarkPaid =
    selected?.status === "pending_approval" || selected?.status === "approved";
  const canDisable =
    selected != null &&
    ["pending_approval", "approved", "active"].includes(selected.status);
  const canClaim = canApprove && selected && !selected.claimed_by;

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Spend roll-up */}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SpendCard
          label={t("spendActive")}
          value={spend ? formatVnd(spend.active_spend_amount, spend.currency, locale) : "—"}
          loading={query.isPending}
          icon={<CurrencyCircleDollar aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-success"
        />
        <SpendCard
          label={t("spendActiveCount")}
          value={spend ? String(spend.active_count) : "—"}
          loading={query.isPending}
          icon={<Megaphone aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-primary"
        />
        <SpendCard
          label={t("spendPending")}
          value={spend ? String(spend.pending_approval_count) : "—"}
          loading={query.isPending}
          icon={<Hourglass aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-warning"
        />
      </div>

      {/* AI Ad Oversight Insights */}
      {!query.isPending && spend && (() => {
        const insights = deriveAdOversightInsights(
          spend.active_count,
          spend.pending_approval_count,
          spend.active_spend_amount,
        );
        if (insights.length === 0) return null;
        return (
          <section
            className="mb-5 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
            aria-label={t("aiInsightsTitle")}
          >
            <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
            </h2>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
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
                  ? s === "pending_approval"
                    ? "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm"
                    : s === "approved"
                      ? "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm"
                      : s === "active"
                        ? "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm"
                        : s === "rejected"
                          ? "border-[var(--red-500)]/30 bg-[var(--red-600)] text-white shadow-sm"
                          : s === "cancelled" || s === "completed"
                            ? "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm"
                            : "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                  : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:bg-[var(--surface-card)] hover:text-[var(--text-primary)]",
              )}
            >
              {s === "all" ? ta("filterAllStatuses") : labels.status(s)}
            </button>
          ))}
        </div>
        {pendingRows.length > 0 && statusFilter === "pending_approval" && (
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
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-2.5">
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
                setTextError(null);
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
      !(
        query.error instanceof ApiError &&
        (query.error.isPermissionError || query.error.isAuthError)
      ) ? (
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
            icon: Megaphone,
            title: t("empty"),
            description: t("emptyBody"),
          }}
        />
      )}

      {/* Review + action panel (single modal; reused for all actions) */}
      <Modal
        open={selected !== null && dialog === null}
        onClose={() => setSelected(null)}
        title={t("reviewTitle")}
        size="md"
        closeLabel={tc("close")}
      >
        {selected && (
          <div className="space-y-4">
            <div>
              <h3 className="text-base font-bold text-[var(--text-primary)]">
                {selected.target_title ?? ta("targetUnavailable")}
              </h3>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusBadge tone={PLACEMENT_STATUS_TONE[selected.status] ?? "info"}>
                  {labels.status(selected.status, selected.status_label)}
                </StatusBadge>
                <StatusBadge tone={PLACEMENT_TYPE_TONE[selected.placement_type] ?? "info"}>
                  {labels.placementType(selected.placement_type, selected.placement_type_label)}
                </StatusBadge>
                <SlaBadge
                  dueBy={selected.due_by}
                  ageHours={selected.age_hours}
                  isOverdue={selected.is_overdue}
                />
                <ClaimBadge claimedBy={selected.claimed_by} isMine={selected.claimed_by === userId} />
              </div>
            </div>

            <Field label={t("fieldOrg")}>
              <span className="font-mono text-xs">{selected.org_id}</span>
            </Field>
            <Field label={t("fieldTargetType")}>
              {labels.targetType(selected.target_type, selected.target_type_label)}
            </Field>
            <Field label={t("colPackage")}>{selected.package?.name ?? "—"}</Field>
            <Field label={t("colPrice")}>
              {formatVnd(selected.price_amount, selected.currency, locale)}{" "}
              <span
                className={selected.is_paid ? "text-[var(--teal-600)]" : "text-[var(--amber-700)]"}
              >
                ({selected.is_paid ? t("paid") : t("unpaid")})
              </span>
            </Field>
            <Field label={t("colWindow")}>
              {formatWindow(selected.start_at, selected.end_at, locale)}
            </Field>
            <Field label={t("fieldDisclosure")}>
              {selected.disclosure_confirmed ? t("disclosureOk") : t("disclosureMissing")}
            </Field>
            {selected.payment_reference && (
              <Field label={t("fieldPaymentRef")}>{selected.payment_reference}</Field>
            )}
            {selected.moderation_note && (
              <Field label={t("fieldNote")}>
                <span className="whitespace-pre-wrap">{selected.moderation_note}</span>
              </Field>
            )}

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
              {canApprove && (
                <Button variant="primary" fullWidth onClick={() => setDialog("approve")}>
                  <CheckCircle aria-hidden weight="bold" className="size-4" />
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
                  <CurrencyCircleDollar aria-hidden weight="bold" className="size-4" />
                  {selected.is_paid ? t("updatePayment") : t("markPaid")}
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
                  <XCircle aria-hidden weight="bold" className="size-4" />
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
                  <Flag aria-hidden weight="bold" className="size-4" />
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
                  <Prohibit aria-hidden weight="bold" className="size-4" />
                  {t("disable")}
                </Button>
              )}
              {!canApprove && !canMarkPaid && !canDisable && (
                <p className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-secondary)] ">
                  {t("noActions")}
                </p>
              )}
            </div>

            {/* Creative moderation + inventory-class relabel. */}
            {selectedLive && (
              <CreativeModerationPanel
                placement={selectedLive}
                onChanged={() => setSelected(selectedLive)}
              />
            )}
          </div>
        )}
      </Modal>

      {/* Approve */}
      <Modal
        open={dialog === "approve"}
        onClose={closeDialog}
        title={t("approveTitle")}
        description={t("approveBody", { target: selected?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
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

      {/* Reject */}
      <Modal
        open={dialog === "reject"}
        onClose={closeDialog}
        title={t("rejectTitle")}
        description={t("rejectBody", { target: selected?.target_title ?? "" })}
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
            id="ad-reject-reason-code"
            value={reasonCode}
            onChange={setReasonCode}
          />
          <LabeledTextarea
            id="ad-reject-reason"
            label={t("reasonLabel")}
            required
            value={reason}
            error={textError}
            onChange={(v) => {
              setReason(v);
              if (textError) setTextError(null);
            }}
            hint={t("reasonHint")}
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
            id="ad-escalate-reason-code"
            value={escalateReasonCode}
            onChange={setEscalateReasonCode}
          />
          <LabeledTextarea
            id="ad-escalate-note"
            label={tm("moderationQueue.otherNoteLabel")}
            value={reason}
            onChange={setReason}
          />
        </div>
      </Modal>

      {/* Mark paid */}
      <Modal
        open={dialog === "markPaid"}
        onClose={closeDialog}
        title={t("markPaidTitle")}
        description={t("markPaidBody", { target: selected?.target_title ?? "" })}
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
                if (selected) markPaid.mutate(selected);
              }}
            >
              {t("markPaidConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">{t("markPaidNote")}</p>
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
        description={t("disableBody", { target: selected?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={disable.isPending}
              onClick={() => selected && disable.mutate(selected)}
            >
              {t("disableConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">{t("disableNote")}</p>
          <LabeledTextarea
            id="ad-disable-reason"
            label={t("disableReasonLabel")}
            value={reason}
            onChange={setReason}
            hint={t("disableReasonHint")}
          />
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
                  setTextError(t("reasonRequired"));
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
            id="ad-bulk-reject-reason-code"
            value={reasonCode}
            onChange={setReasonCode}
          />
          <LabeledTextarea
            id="ad-bulk-reject-reason"
            label={t("reasonLabel")}
            required
            value={reason}
            error={textError}
            onChange={(v) => {
              setReason(v);
              if (textError) setTextError(null);
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
        {bulkResults && (
          <BulkResultList
            results={bulkResults}
            getLabel={(id) => rows.find((r) => r.id === id)?.target_title ?? id}
          />
        )}
      </Modal>
    </>
  );
}

function SpendCard({
  label,
  value,
  loading,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value: string;
  loading: boolean;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
      <div
        className={`mb-3 flex size-11 items-center justify-center rounded-xl shadow-sm ${iconBg}`}
      >
        {icon}
      </div>
      <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
        {loading ? "…" : value}
      </p>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
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

function LabeledTextarea({
  id,
  label,
  value,
  onChange,
  required,
  error,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  error?: string | null;
  hint?: string;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
        {required && (
          <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
            *
          </span>
        )}
      </label>
      <textarea
        id={id}
        rows={3}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className="w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--surface-card)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
      />
      {error ? (
        <p id={`${id}-error`} className="mt-1 text-xs font-medium text-[var(--brand-red)]">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-xs text-[var(--text-muted)]">{hint}</p>
      ) : null}
    </div>
  );
}
