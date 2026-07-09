"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeDollarSign,
  CircleDollarSign,
  Hourglass,
  Pencil,
  Plus,
  Receipt,
} from "lucide-react";
import { Button, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { useBillingLabels } from "@/lib/billing/labels";
import { formatVnd, formatWindow } from "@/lib/billing/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  billingApi,
  SUBSCRIPTION_STATUSES,
  type AdminPlanCreateBody,
  type BillingAudience,
  type Subscription,
  type SubscriptionPlan,
  type SubscriptionStatus,
} from "@/lib/api";
import { PlanFormModal } from "./oversight/plan-form-modal";
import { CancelSubscriptionModal, MarkPaidModal } from "./oversight/subscription-action-modals";
import {
  AUDIENCE_FILTERS,
  EMPTY_PLAN_FORM,
  planFormFrom,
  type DialogKind,
  type PlanDialogKind,
  type PlanForm,
} from "./oversight/utils";

const STATUS_FILTERS = ["all", ...SUBSCRIPTION_STATUSES] as const;

/** Subscription status → kit StatusChip tone (color carries meaning). */
const STATUS_CHIP_TONE: Record<SubscriptionStatus, ChipTone> = {
  pending: "warning",
  active: "success",
  expired: "neutral",
  cancelled: "danger",
};

export function BillingOversightScreen() {
  const t = useTranslations("billingOversight");
  const tb = useTranslations("billing");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useBillingLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("pending");
  const [audienceFilter, setAudienceFilter] = React.useState<string>("all");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [dialog, setDialog] = React.useState<DialogKind>(null);
  const [paymentRef, setPaymentRef] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [textError, setTextError] = React.useState<string | null>(null);
  const [selectedPlan, setSelectedPlan] = React.useState<SubscriptionPlan | null>(null);
  const [planDialog, setPlanDialog] = React.useState<PlanDialogKind>(null);
  const [planForm, setPlanForm] = React.useState<PlanForm>(EMPTY_PLAN_FORM);
  const [planError, setPlanError] = React.useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "billing", statusFilter, audienceFilter],
    queryFn: () =>
      billingApi.listAllSubscriptions({
        status: statusFilter === "all" ? undefined : (statusFilter as SubscriptionStatus),
        audience: audienceFilter === "all" ? undefined : (audienceFilter as "student" | "partner"),
        limit: 100,
      }),
    retry: false,
  });

  const plansQuery = useQuery({
    queryKey: ["admin", "billing", "plans", audienceFilter],
    queryFn: () =>
      billingApi.listAdminPlans(audienceFilter === "all" ? undefined : (audienceFilter as BillingAudience)),
    retry: false,
  });

  const rows = React.useMemo(() => query.data?.items ?? [], [query.data]);
  const selected = React.useMemo(() => rows.find((r) => r.id === selectedId) ?? null, [rows, selectedId]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "billing"] });
  }

  function closeDialog() {
    setDialog(null);
    setSelectedId(null);
    setPaymentRef("");
    setReason("");
    setTextError(null);
  }

  function closePlanDialog() {
    setSelectedPlan(null);
    setPlanDialog(null);
    setPlanForm(EMPTY_PLAN_FORM);
    setPlanError(null);
  }

  function openCreatePlan() {
    setSelectedPlan(null);
    setPlanForm(EMPTY_PLAN_FORM);
    setPlanError(null);
    setPlanDialog("create");
  }

  function openEditPlan(plan: SubscriptionPlan) {
    setSelectedPlan(plan);
    setPlanForm(planFormFrom(plan));
    setPlanError(null);
    setPlanDialog("edit");
  }

  function patchPlanForm(patch: Partial<PlanForm>) {
    setPlanForm((current) => ({ ...current, ...patch }));
    if (planError) setPlanError(null);
  }

  function planBody(): AdminPlanCreateBody {
    let limits: AdminPlanCreateBody["limits"];
    try {
      const parsed = JSON.parse(planForm.limitsText || "{}");
      if (parsed == null || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("limits_not_object");
      }
      limits = parsed;
    } catch {
      throw new Error(t("planLimitsInvalid"));
    }
    return {
      code: planForm.code.trim(),
      name: planForm.name.trim(),
      name_en: planForm.nameEn.trim(),
      audience: planForm.audience,
      billing_period: planForm.billingPeriod,
      duration_days: Number(planForm.durationDays),
      price_amount: planForm.priceAmount,
      currency: planForm.currency.trim().toUpperCase(),
      limits,
      is_default: planForm.isDefault,
      is_visible: planForm.isVisible,
      sort_order: Number(planForm.sortOrder || 0),
    };
  }

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: tb("errors.conflictTitle"), description: t("conflictBody") });
      closeDialog();
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const markPaid = useMutation({
    mutationFn: (s: Subscription) => billingApi.markPaid(s.id, paymentRef, s.version),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("paidToast") });
      refresh();
    },
    onError: handleError,
  });

  const cancel = useMutation({
    mutationFn: (s: Subscription) =>
      billingApi.adminCancelSubscription(s.id, { reason: reason.trim() || undefined, version: s.version }),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("cancelledToast") });
      refresh();
    },
    onError: handleError,
  });

  const createPlan = useMutation({
    mutationFn: () => billingApi.createPlan(planBody()),
    onSuccess: () => {
      closePlanDialog();
      toast.show({ tone: "success", title: t("planSavedToast") });
      refresh();
    },
    onError: handleError,
  });

  const updatePlan = useMutation({
    mutationFn: () => {
      if (!selectedPlan) throw new Error("missing_plan");
      const body = planBody();
      return billingApi.updatePlan(selectedPlan.id, {
        name: body.name,
        name_en: body.name_en,
        billing_period: body.billing_period,
        duration_days: body.duration_days,
        price_amount: body.price_amount,
        currency: body.currency,
        limits: body.limits,
        is_default: body.is_default,
        is_visible: body.is_visible,
        sort_order: body.sort_order,
      });
    },
    onSuccess: () => {
      closePlanDialog();
      toast.show({ tone: "success", title: t("planSavedToast") });
      refresh();
    },
    onError: handleError,
  });

  const header = <PageHeader title={t("title")} subtitle={t("subtitle")} />;

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const revenue = query.data?.revenue ?? null;
  const plans = plansQuery.data ?? [];
  const canMarkPaid = selected?.status === "pending";
  const canCancel = selected != null && ["pending", "active"].includes(selected.status);

  const subColumns: ColumnDef<Subscription, unknown>[] = [
    {
      accessorKey: "plan",
      header: t("colPlan"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="min-w-0">
            <span className="block truncate font-semibold text-foreground">{r.plan?.name ?? "—"}</span>
            <span className="type-caption block truncate text-muted-foreground">
              {r.plan
                ? labels.audience(r.plan.audience, r.plan.audience_label)
                : labels.audience(r.principal_type === "org" ? "partner" : "student")}
              {r.principal_id ? ` · ${t("principalRef", { id: r.principal_id.slice(0, 8) })}` : ""}
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: "price_amount",
      header: t("colPrice"),
      meta: { align: "right" },
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex flex-col items-end">
            <span className="font-semibold tabular-nums text-foreground">
              {formatVnd(r.price_amount, r.currency, locale)}
            </span>
            <StatusChip tone={r.is_paid ? "success" : "warning"} size="sm">
              {r.is_paid ? t("paid") : t("unpaid")}
            </StatusChip>
          </div>
        );
      },
    },
    {
      id: "window",
      header: t("colWindow"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="type-caption text-muted-foreground">
          {formatWindow(row.original.start_at, row.original.end_at, locale)}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_CHIP_TONE[row.original.status] ?? "neutral"} dot size="sm">
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
        <div onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" size="sm" onClick={() => setSelectedId(row.original.id)}>
            {t("review")}
          </Button>
        </div>
      ),
    },
  ];

  const loadError =
    query.isError &&
    !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError));

  return (
    <>
      {header}

      <div className="space-y-4">
        {/* Revenue KPI row */}
        <KpiRow cols={3}>
          <KpiTile
            label={t("revenueActive")}
            value={revenue ? formatVnd(revenue.active_revenue_amount, revenue.currency, locale) : "—"}
            icon={CircleDollarSign}
          />
          <KpiTile label={t("revenueActiveCount")} value={revenue ? String(revenue.active_count) : "—"} icon={Receipt} />
          <KpiTile
            label={t("revenuePending")}
            value={revenue ? String(revenue.pending_count) : "—"}
            icon={Hourglass}
            hint={revenue && revenue.pending_count > 0 ? t("revenuePendingHint") : undefined}
          />
        </KpiRow>

        {/* Plan catalogue */}
        <PlanCatalogueCard
          plans={plans}
          loading={plansQuery.isPending}
          locale={locale}
          onCreate={openCreatePlan}
          onEdit={openEditPlan}
        />

        {/* Subscriptions */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("subscriptionsTitle")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {/* Filters */}
            <div className="mb-4 space-y-2.5">
              <ChipGroup
                ariaLabel={t("filterStatus")}
                options={STATUS_FILTERS.map((s) => ({ value: s, label: s === "all" ? t("filterAll") : labels.status(s) }))}
                value={statusFilter}
                onChange={setStatusFilter}
              />
              <ChipGroup
                ariaLabel={t("filterAudience")}
                options={AUDIENCE_FILTERS.map((a) => ({ value: a, label: a === "all" ? t("filterAll") : labels.audience(a) }))}
                value={audienceFilter}
                onChange={setAudienceFilter}
              />
            </div>

            {loadError ? (
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
                columns={subColumns}
                data={rows}
                getRowId={(r) => r.id}
                loading={query.isPending}
                onRowClick={(r) => setSelectedId(r.id)}
                activeRowId={selectedId ?? undefined}
                pageSize={15}
                empty={<EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Review detail sheet */}
      <SubscriptionDetailSheet
        subscription={dialog === null ? selected : null}
        locale={locale}
        canMarkPaid={!!canMarkPaid}
        canCancel={canCancel}
        onClose={() => setSelectedId(null)}
        onMarkPaid={() => {
          setPaymentRef("");
          setTextError(null);
          setDialog("markPaid");
        }}
        onCancel={() => {
          setReason("");
          setTextError(null);
          setDialog("cancel");
        }}
      />

      <MarkPaidModal
        open={dialog === "markPaid"}
        selected={selected}
        paymentRef={paymentRef}
        textError={textError}
        loading={markPaid.isPending}
        t={t}
        tc={tc}
        onClose={closeDialog}
        onPaymentRefChange={(v) => {
          setPaymentRef(v);
          if (textError) setTextError(null);
        }}
        onSubmit={() => {
          if (!paymentRef.trim()) {
            setTextError(t("paymentRefRequired"));
            return;
          }
          if (selected) markPaid.mutate(selected);
        }}
      />

      <CancelSubscriptionModal
        open={dialog === "cancel"}
        selected={selected}
        reason={reason}
        loading={cancel.isPending}
        t={t}
        tc={tc}
        onClose={closeDialog}
        onReasonChange={setReason}
        onSubmit={() => selected && cancel.mutate(selected)}
      />

      <PlanFormModal
        planDialog={planDialog}
        planForm={planForm}
        planError={planError}
        saving={createPlan.isPending || updatePlan.isPending}
        t={t}
        tc={tc}
        onClose={closePlanDialog}
        onPatch={patchPlanForm}
        onSubmit={() => {
          try {
            planBody();
          } catch (err) {
            setPlanError(err instanceof Error ? err.message : t("planInvalid"));
            return;
          }
          if (planDialog === "edit") updatePlan.mutate();
          else createPlan.mutate();
        }}
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Plan catalogue                                                              */
/* -------------------------------------------------------------------------- */

function PlanCatalogueCard({
  plans,
  loading,
  locale,
  onCreate,
  onEdit,
}: {
  plans: SubscriptionPlan[];
  loading: boolean;
  locale: string;
  onCreate: () => void;
  onEdit: (plan: SubscriptionPlan) => void;
}) {
  const t = useTranslations("billingOversight");
  const labels = useBillingLabels();

  const columns: ColumnDef<SubscriptionPlan, unknown>[] = [
    {
      accessorKey: "name",
      header: t("colPlan"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate font-semibold text-foreground">{row.original.name}</span>
          <span className="type-caption block truncate font-mono text-muted-foreground">{row.original.code}</span>
        </div>
      ),
    },
    {
      accessorKey: "audience",
      header: t("planAudience"),
      cell: ({ row }) => (
        <StatusChip tone={row.original.audience === "partner" ? "violet" : "teal"} size="sm">
          {labels.audience(row.original.audience, row.original.audience_label)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "billing_period",
      header: t("planPeriod"),
      cell: ({ row }) => <span className="text-muted-foreground">{labels.period(row.original.billing_period, row.original.billing_period_label)}</span>,
    },
    {
      accessorKey: "price_amount",
      header: t("planPrice"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="font-semibold tabular-nums text-foreground">
          {formatVnd(row.original.price_amount, row.original.currency, locale)}
        </span>
      ),
    },
    {
      id: "flags",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1.5">
          {row.original.is_default && <StatusChip tone="indigo" size="sm">{t("planDefault")}</StatusChip>}
          <StatusChip tone={row.original.is_visible ? "success" : "neutral"} size="sm">
            {row.original.is_visible ? t("planVisible") : t("planHidden")}
          </StatusChip>
        </div>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <div onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" size="sm" onClick={() => onEdit(row.original)}>
            <Pencil className="size-4" strokeWidth={1.8} />
            {t("planEdit")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("planCatalogTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Button variant="secondary" size="sm" onClick={onCreate}>
            <Plus className="size-4" strokeWidth={2} />
            {t("planCreate")}
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={plans}
          getRowId={(r) => r.id}
          loading={loading}
          onRowClick={(r) => onEdit(r)}
          empty={<EmptyState kind="empty" title={t("planEmpty")} description={t("planEmptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Subscription detail sheet                                                    */
/* -------------------------------------------------------------------------- */

function SubscriptionDetailSheet({
  subscription,
  locale,
  canMarkPaid,
  canCancel,
  onClose,
  onMarkPaid,
  onCancel,
}: {
  subscription: Subscription | null;
  locale: string;
  canMarkPaid: boolean;
  canCancel: boolean;
  onClose: () => void;
  onMarkPaid: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("billingOversight");
  const tc = useTranslations("common");
  const labels = useBillingLabels();
  const open = subscription != null;

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      title={subscription?.plan?.name ?? t("reviewTitle")}
      subtitle={
        subscription
          ? labels.audience(
              subscription.plan?.audience ?? (subscription.principal_type === "org" ? "partner" : "student"),
              subscription.plan?.audience_label,
            )
          : undefined
      }
      status={
        subscription ? (
          <>
            <StatusChip tone={STATUS_CHIP_TONE[subscription.status] ?? "neutral"} dot>
              {labels.status(subscription.status, subscription.status_label)}
            </StatusChip>
            <StatusChip tone={subscription.is_paid ? "success" : "warning"}>
              {subscription.is_paid ? t("paid") : t("unpaid")}
            </StatusChip>
          </>
        ) : undefined
      }
      width="md"
      closeLabel={tc("close")}
      footer={
        subscription && (canMarkPaid || canCancel) ? (
          <>
            {canCancel && (
              <Button variant="ghost" size="sm" onClick={onCancel}>
                {t("cancel")}
              </Button>
            )}
            {canMarkPaid && (
              <Button variant="primary" size="sm" onClick={onMarkPaid}>
                <BadgeDollarSign className="size-4" strokeWidth={1.8} />
                {t("markPaid")}
              </Button>
            )}
          </>
        ) : undefined
      }
    >
      {subscription && (
        <>
          <DetailSheetSection title={t("reviewTitle")}>
            <dl>
              <DetailRow label={t("colPrice")}>
                {formatVnd(subscription.price_amount, subscription.currency, locale)}
              </DetailRow>
              <DetailRow label={t("colWindow")}>
                {formatWindow(subscription.start_at, subscription.end_at, locale)}
              </DetailRow>
              {subscription.principal_id && (
                <DetailRow label={t("fieldPrincipal")}>
                  <span className="font-mono text-xs">{subscription.principal_id}</span>
                </DetailRow>
              )}
              {subscription.payment_reference && (
                <DetailRow label={t("fieldPaymentRef")}>
                  <span className="font-mono text-xs">{subscription.payment_reference}</span>
                </DetailRow>
              )}
              {subscription.cancel_reason && (
                <DetailRow label={t("fieldCancelReason")}>{subscription.cancel_reason}</DetailRow>
              )}
            </dl>
            {!canMarkPaid && !canCancel && (
              <p className="mt-3 type-small text-muted-foreground">{t("noActions")}</p>
            )}
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Chip filter group                                                            */
/* -------------------------------------------------------------------------- */

function ChipGroup({
  ariaLabel,
  options,
  value,
  onChange,
}: {
  ariaLabel: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={ariaLabel}>
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
              active
                ? "border-transparent bg-foreground text-[var(--surface-card)]"
                : "border-border bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
