"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Check,
  CircleDollarSign,
  Clock,
  Hourglass,
  Megaphone,
  Pause,
  ShieldCheck,
  ShieldX,
  Tag,
  Target,
  X,
} from "lucide-react";
import { Button, Input, Modal, Select, SponsoredLabel, useToast } from "@/components/ui";
import {
  DataTable,
  DetailRow,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  FilterBar,
  KpiTile,
  StatusChip,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import { ReasonCodeSelect } from "@/components/moderation/queue-controls";
import {
  CAMPAIGN_OBJECTIVE_TONE,
  CAMPAIGN_STATUS_TONE,
  useCampaignLabels,
} from "@/lib/advertising/campaign-labels";
import { useReachSummary } from "@/lib/advertising/use-reach-summary";
import { formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  advertisingApi,
  CAMPAIGN_STATUSES,
  type AdCampaign,
  type DisclosureClass,
  type ModerationReasonCode,
} from "@/lib/api";

const STATUS_FILTERS = ["all", ...CAMPAIGN_STATUSES] as const;

const DISCLOSURE_CLASS_OPTIONS: DisclosureClass[] = [
  "paid_sponsored",
  "university_curated",
  "strategic_partner",
  "featured",
];

type DialogKind = "approve" | "reject" | "markPaid" | "pause" | "disable" | "relabel" | null;

function SlaChip({
  ageHours,
  isOverdue,
}: {
  ageHours?: number | null;
  isOverdue?: boolean;
}) {
  const t = useTranslations("common");
  if (ageHours == null) return null;
  const label = isOverdue
    ? t("moderationQueue.slaOverdue", { hours: Math.round(ageHours) })
    : t("moderationQueue.slaAge", { hours: Math.round(ageHours) });
  return (
    <StatusChip tone={isOverdue ? "danger" : "warning"} size="sm">
      <Clock aria-hidden className="size-3" strokeWidth={2} />
      {label}
    </StatusChip>
  );
}

export function CampaignQueueScreen() {
  const t = useTranslations("advertisingOversight.campaign");
  const tOversight = useTranslations("advertisingOversight");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const labels = useCampaignLabels();
  const reachSummary = useReachSummary();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("pending_review");
  const [selected, setSelected] = React.useState<AdCampaign | null>(null);
  const [dialog, setDialog] = React.useState<DialogKind>(null);
  const [reason, setReason] = React.useState("");
  const [reasonCode, setReasonCode] = React.useState<ModerationReasonCode | string>("other");
  const [paymentRef, setPaymentRef] = React.useState("");
  const [relabelClass, setRelabelClass] = React.useState<DisclosureClass>("paid_sponsored");
  const [textError, setTextError] = React.useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "advertising", "campaigns", statusFilter],
    queryFn: () =>
      advertisingApi.listCampaignQueue({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
    retry: false,
  });

  const rows = query.data?.items ?? [];
  const spend = query.data?.spend ?? null;
  const selectedLive = selected ? (rows.find((r) => r.id === selected.id) ?? selected) : null;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "advertising", "campaigns"] });
  }

  function closeDialog() {
    setDialog(null);
    setReason("");
    setPaymentRef("");
    setTextError(null);
  }

  function handleError(e: unknown) {
    const reasonCodeDetail =
      e instanceof ApiError && typeof e.details?.reason === "string" ? (e.details.reason as string) : undefined;
    if (reasonCodeDetail === "paid_disclosure_immutable") {
      toast.show({ tone: "error", title: t("relabelImmutable") });
      return;
    }
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: t("conflictTitle"), description: t("conflictBody") });
      closeDialog();
      setSelected(null);
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const approve = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.approveCampaign(c.id, { version: c.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleError,
  });

  const reject = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.rejectCampaign(c.id, reason, c.version, reasonCode),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleError,
  });

  const markPaid = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.markCampaignPaid(c.id, paymentRef, c.version),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("paidToast") });
      refresh();
    },
    onError: handleError,
  });

  const pause = useMutation({
    mutationFn: (c: AdCampaign) =>
      advertisingApi.adminPauseCampaign(c.id, { reason: reason.trim() || undefined, version: c.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("pausedToast") });
      refresh();
    },
    onError: handleError,
  });

  const disable = useMutation({
    mutationFn: (c: AdCampaign) =>
      advertisingApi.disableCampaign(c.id, { reason: reason.trim() || undefined, version: c.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("disabledToast") });
      refresh();
    },
    onError: handleError,
  });

  const relabel = useMutation({
    mutationFn: (c: AdCampaign) =>
      advertisingApi.setCampaignDisclosureClass(c.id, { disclosure_class: relabelClass, version: c.version }),
    onSuccess: () => {
      closeDialog();
      setSelected(null);
      toast.show({ tone: "success", title: t("relabelSaved") });
      refresh();
    },
    onError: handleError,
  });

  const isPermissionError =
    query.isError &&
    query.error instanceof ApiError &&
    (query.error.isPermissionError || query.error.isAuthError);

  const columns: ColumnDef<AdCampaign, unknown>[] = [
    {
      id: "campaign",
      header: t("col.campaign"),
      cell: ({ row }) => {
        const c = row.original;
        return (
          <div className="min-w-0">
            <p className="truncate font-semibold text-foreground">{c.name}</p>
            <p className="truncate type-caption text-muted-foreground">
              {labels.objective(c.objective, c.objective_label)} · {labels.surface(c.surface)}
            </p>
          </div>
        );
      },
    },
    {
      id: "org",
      header: t("col.org"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="font-mono type-caption text-muted-foreground">{row.original.org_id.slice(0, 8)}</span>
      ),
    },
    {
      id: "budget",
      header: t("col.budget"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex flex-col items-end">
          <span className="font-semibold tabular-nums text-foreground">
            {formatVnd(row.original.budget_amount, row.original.currency, locale)}
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
      id: "sla",
      header: t("col.sla"),
      enableSorting: false,
      cell: ({ row }) => <SlaChip ageHours={row.original.age_hours} isOverdue={row.original.is_overdue} />,
    },
    {
      accessorKey: "status",
      header: t("col.status"),
      cell: ({ row }) => (
        <StatusChip tone={CAMPAIGN_STATUS_TONE[row.original.status] ?? "neutral"} dot>
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

  const canApprove = selectedLive?.status === "pending_review";
  const canMarkPaid =
    selectedLive != null && ["pending_review", "approved", "active", "paused"].includes(selectedLive.status);
  const canPause = selectedLive?.status === "active";
  const canDisable =
    selectedLive != null && ["approved", "active", "paused"].includes(selectedLive.status);

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
              ? tOversight("permissionBody")
              : tStates("authBody")
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <KpiTile
              label={t("kpi.activeSpend")}
              value={spend ? formatVnd(spend.total_spend_amount, spend.currency, locale) : "—"}
              icon={CircleDollarSign}
            />
            <KpiTile label={t("kpi.activeCount")} value={spend ? String(spend.active_count) : "—"} icon={Megaphone} />
            <KpiTile
              label={t("kpi.pendingCount")}
              value={spend ? String(spend.pending_review_count) : "—"}
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
                    {s === "all" ? t("allStatuses") : labels.status(s)}
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
              empty={<EmptyState kind="empty" icon={Megaphone} title={t("empty")} description={t("emptyBody")} />}
            />
          )}
        </div>
      )}

      {/* Review + action drawer */}
      <DetailSheet
        open={selectedLive !== null && dialog === null}
        onClose={() => setSelected(null)}
        title={selectedLive?.name ?? ""}
        subtitle={selectedLive ? labels.surface(selectedLive.surface) : undefined}
        width="lg"
        closeLabel={tc("close")}
        status={
          selectedLive ? (
            <>
              <StatusChip tone={CAMPAIGN_STATUS_TONE[selectedLive.status] ?? "neutral"} dot>
                {labels.status(selectedLive.status, selectedLive.status_label)}
              </StatusChip>
              <StatusChip tone={CAMPAIGN_OBJECTIVE_TONE[selectedLive.objective] ?? "neutral"} size="sm">
                {labels.objective(selectedLive.objective, selectedLive.objective_label)}
              </StatusChip>
              <SlaChip ageHours={selectedLive.age_hours} isOverdue={selectedLive.is_overdue} />
            </>
          ) : undefined
        }
      >
        {selectedLive && (
          <>
            {selectedLive.moderation_note && (
              <div className="mb-3 rounded-lg px-3 py-2 type-small text-muted-foreground">
                {t("detail.moderationNote")}: {selectedLive.moderation_note}
              </div>
            )}

            <DetailSheetSection title={t("detail.budgetSection")}>
              <dl>
                <DetailRow label={t("detail.org")}>
                  <span className="font-mono text-xs">{selectedLive.org_id.slice(0, 8)}</span>
                </DetailRow>
                <DetailRow label={t("detail.budget")}>
                  <span className="tabular-nums">{formatVnd(selectedLive.budget_amount, selectedLive.currency, locale)}</span>{" "}
                  <span style={{ color: selectedLive.is_paid ? "var(--content-success)" : "var(--content-warning)" }}>
                    ({selectedLive.is_paid ? t("paid") : t("unpaid")})
                  </span>
                </DetailRow>
                <DetailRow label={t("detail.spent")}>
                  <span className="tabular-nums">{formatVnd(selectedLive.spent_amount, selectedLive.currency, locale)}</span>
                </DetailRow>
                <DetailRow label={t("detail.pacing")}>{labels.pacing(selectedLive.pacing, selectedLive.pacing_label)}</DetailRow>
                <DetailRow label={t("detail.schedule")}>
                  {formatWindow(selectedLive.start_at, selectedLive.end_at, locale)}
                </DetailRow>
                {selectedLive.payment_reference && (
                  <DetailRow label={t("detail.paymentRef")}>
                    <span className="font-mono text-xs">{selectedLive.payment_reference}</span>
                  </DetailRow>
                )}
              </dl>
            </DetailSheetSection>

            <DetailSheetSection title={t("detail.targetingSection")}>
              <p className="flex items-start gap-2 type-small text-foreground">
                <Target aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.8} />
                {reachSummary(selectedLive.targeting)}
              </p>
            </DetailSheetSection>

            <DetailSheetSection title={t("detail.creativeSection")}>
              {!selectedLive.creative?.headline && !selectedLive.creative?.image_ref ? (
                <p className="type-small text-muted-foreground">{t("detail.noCreative")}</p>
              ) : (
                <div className="rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
                  {selectedLive.creative?.headline && (
                    <p className="font-semibold text-foreground">{selectedLive.creative.headline}</p>
                  )}
                  {selectedLive.creative?.body && (
                    <p className="mt-1 type-small text-muted-foreground">{selectedLive.creative.body}</p>
                  )}
                </div>
              )}
            </DetailSheetSection>

            <DetailSheetSection title={t("detail.disclosureSection")}>
              <div className="flex flex-wrap items-center gap-2">
                {selectedLive.disclosure_confirmed ? (
                  <StatusChip tone="success" size="sm">
                    <ShieldCheck aria-hidden className="size-3.5" strokeWidth={2} />
                    {t("detail.disclosureConfirmed")}
                  </StatusChip>
                ) : (
                  <StatusChip tone="danger" size="sm">
                    <ShieldX aria-hidden className="size-3.5" strokeWidth={2} />
                    {t("detail.disclosureMissing")}
                  </StatusChip>
                )}
                <SponsoredLabel label={selectedLive.disclosure?.label ?? ""} />
              </div>
            </DetailSheetSection>

            {/* Actions */}
            <DetailSheetSection>
              <div className="flex flex-col gap-2">
                {canApprove && (
                  <Button variant="primary" fullWidth onClick={() => setDialog("approve")}>
                    <Check className="size-4" strokeWidth={1.9} />
                    {t("action.approve")}
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
                    {t("action.reject")}
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
                    {selectedLive.is_paid ? t("action.updatePayment") : t("action.markPaid")}
                  </Button>
                )}
                {canPause && (
                  <Button
                    variant="ghost"
                    fullWidth
                    onClick={() => {
                      setReason("");
                      setTextError(null);
                      setDialog("pause");
                    }}
                  >
                    <Pause className="size-4" strokeWidth={1.9} />
                    {t("action.pause")}
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
                    {t("action.disable")}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  fullWidth
                  onClick={() => {
                    setRelabelClass((selectedLive.disclosure_class as DisclosureClass) ?? "paid_sponsored");
                    setDialog("relabel");
                  }}
                >
                  <Tag className="size-4" strokeWidth={1.9} />
                  {t("action.relabel")}
                </Button>
                {!canApprove && !canMarkPaid && !canPause && !canDisable && (
                  <p className="type-small text-muted-foreground">{t("action.none")}</p>
                )}
              </div>
            </DetailSheetSection>
          </>
        )}
      </DetailSheet>

      {/* Approve */}
      <Modal
        open={dialog === "approve"}
        onClose={closeDialog}
        title={t("approveTitle")}
        description={t("approveBody", { name: selectedLive?.name ?? "" })}
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
        description={t("rejectBody", { name: selectedLive?.name ?? "" })}
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
          <ReasonCodeSelect id="campaign-reject-reason-code" value={reasonCode} onChange={setReasonCode} />
          <ReasonField
            id="campaign-reject-reason"
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

      {/* Mark paid */}
      <Modal
        open={dialog === "markPaid"}
        onClose={closeDialog}
        title={t("markPaidTitle")}
        description={t("markPaidBody", { name: selectedLive?.name ?? "" })}
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
            id="campaign-payment-ref"
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

      {/* Pause */}
      <Modal
        open={dialog === "pause"}
        onClose={closeDialog}
        title={t("pauseTitle")}
        description={t("pauseBody", { name: selectedLive?.name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={pause.isPending} onClick={() => selectedLive && pause.mutate(selectedLive)}>
              {t("pauseConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("pauseNote")}</p>
          <ReasonField id="campaign-pause-reason" label={t("reasonOptional")} value={reason} onChange={setReason} />
        </div>
      </Modal>

      {/* Disable */}
      <Modal
        open={dialog === "disable"}
        onClose={closeDialog}
        title={t("disableTitle")}
        description={t("disableBody", { name: selectedLive?.name ?? "" })}
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
          <ReasonField id="campaign-disable-reason" label={t("reasonOptional")} value={reason} onChange={setReason} />
        </div>
      </Modal>

      {/* Relabel disclosure class */}
      <Modal
        open={dialog === "relabel"}
        onClose={closeDialog}
        title={t("relabelTitle")}
        description={t("relabelBody", { name: selectedLive?.name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={relabel.isPending} onClick={() => selectedLive && relabel.mutate(selectedLive)}>
              {t("relabelConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Select
            label={t("relabelLabel")}
            value={relabelClass}
            onChange={(e) => setRelabelClass(e.target.value as DisclosureClass)}
            options={DISCLOSURE_CLASS_OPTIONS.map((c) => ({
              value: c,
              label: t(`relabelOptions.${c}`),
            }))}
            help={t("relabelHelp")}
          />
        </div>
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
