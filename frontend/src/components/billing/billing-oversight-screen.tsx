"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CurrencyCircleDollar,
  Hourglass,
  Receipt,
  ShieldWarning,
  SignIn,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { useBillingLabels, SUBSCRIPTION_STATUS_TONE } from "@/lib/billing/labels";
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
import { RevenueCard } from "./oversight/revenue-card";
import { PlanCatalogSection } from "./oversight/plan-catalog-section";
import { SubscriptionReviewModal } from "./oversight/subscription-review-modal";
import { CancelSubscriptionModal, MarkPaidModal } from "./oversight/subscription-action-modals";
import { PlanFormModal } from "./oversight/plan-form-modal";
import {
  AUDIENCE_FILTERS,
  EMPTY_PLAN_FORM,
  planFormFrom,
  type DialogKind,
  type PlanDialogKind,
  type PlanForm,
} from "./oversight/utils";

const STATUS_FILTERS = ["all", ...SUBSCRIPTION_STATUSES] as const;

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

  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [audienceFilter, setAudienceFilter] = useState<string>("all");
  const [selected, setSelected] = useState<Subscription | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [paymentRef, setPaymentRef] = useState("");
  const [reason, setReason] = useState("");
  const [textError, setTextError] = useState<string | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionPlan | null>(null);
  const [planDialog, setPlanDialog] = useState<PlanDialogKind>(null);
  const [planForm, setPlanForm] = useState<PlanForm>(EMPTY_PLAN_FORM);
  const [planError, setPlanError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "billing", statusFilter, audienceFilter],
    queryFn: () =>
      billingApi.listAllSubscriptions({
        status:
          statusFilter === "all"
            ? undefined
            : (statusFilter as SubscriptionStatus),
        audience:
          audienceFilter === "all"
            ? undefined
            : (audienceFilter as "student" | "partner"),
        limit: 100,
      }),
    retry: false,
  });

  const plansQuery = useQuery({
    queryKey: ["admin", "billing", "plans", audienceFilter],
    queryFn: () =>
      billingApi.listAdminPlans(
        audienceFilter === "all" ? undefined : (audienceFilter as BillingAudience),
      ),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "billing"] });
  }

  function closeDialog() {
    setDialog(null);
    setSelected(null);
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
      toast.show({
        tone: "error",
        title: tb("errors.conflictTitle"),
        description: t("conflictBody"),
      });
      closeDialog();
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const markPaid = useMutation({
    mutationFn: (s: Subscription) =>
      billingApi.markPaid(s.id, paymentRef, s.version),
    onSuccess: () => {
      closeDialog();
      toast.show({ tone: "success", title: t("paidToast") });
      refresh();
    },
    onError: handleError,
  });

  const cancel = useMutation({
    mutationFn: (s: Subscription) =>
      billingApi.adminCancelSubscription(s.id, {
        reason: reason.trim() || undefined,
        version: s.version,
      }),
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
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
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
  const revenue = query.data?.revenue ?? null;

  const columns: Column<Subscription>[] = [
    {
      key: "plan",
      header: t("colPlan"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--text-primary)]">
            {r.plan?.name ?? "—"}
          </p>
          <p className="truncate text-xs text-[var(--text-secondary)]">
            {r.plan
              ? labels.audience(r.plan.audience, r.plan.audience_label)
              : labels.audience(
                  r.principal_type === "org" ? "partner" : "student",
                )}
            {r.principal_id ? ` · ${t("principalRef", { id: r.principal_id.slice(0, 8) })}` : ""}
          </p>
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
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <StatusBadge tone={SUBSCRIPTION_STATUS_TONE[r.status] ?? "info"}>
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

  const canMarkPaid = selected?.status === "pending";
  const canCancel =
    selected != null && ["pending", "active"].includes(selected.status);
  const plans = plansQuery.data ?? [];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      <PlanCatalogSection
        plans={plans}
        loading={plansQuery.isPending}
        locale={locale}
        t={t}
        onCreate={openCreatePlan}
        onEdit={openEditPlan}
      />

      {/* Revenue roll-up */}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <RevenueCard
          label={t("revenueActive")}
          value={
            revenue
              ? formatVnd(revenue.active_revenue_amount, revenue.currency, locale)
              : "—"
          }
          loading={query.isPending}
          icon={<CurrencyCircleDollar aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-success"
        />
        <RevenueCard
          label={t("revenueActiveCount")}
          value={revenue ? String(revenue.active_count) : "—"}
          loading={query.isPending}
          icon={<Receipt aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-primary"
        />
        <RevenueCard
          label={t("revenuePending")}
          value={revenue ? String(revenue.pending_count) : "—"}
          loading={query.isPending}
          icon={<Hourglass aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-warning"
        />
      </div>

      {/* Status + audience filter tab chips */}
      <div className="mb-4 space-y-2.5">
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("filterStatus")}>
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              aria-pressed={statusFilter === s}
              className={cn(
                "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                statusFilter === s
                  ? s === "pending"
                    ? "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm"
                    : s === "active"
                      ? "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm"
                      : s === "cancelled" || s === "expired"
                        ? "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm"
                        : "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                  : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
              )}
            >
              {s === "all" ? t("filterAll") : labels.status(s)}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("filterAudience")}>
          {AUDIENCE_FILTERS.map((a) => (
            <button
              key={a}
              onClick={() => setAudienceFilter(a)}
              aria-pressed={audienceFilter === a}
              className={cn(
                "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                audienceFilter === a
                  ? a === "student"
                    ? "border-teal-500/30 bg-teal-600 text-white shadow-sm"
                    : a === "partner"
                      ? "border-violet-500/30 bg-violet-600 text-white shadow-sm"
                      : "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                  : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
              )}
            >
              {a === "all" ? t("filterAll") : labels.audience(a)}
            </button>
          ))}
        </div>
      </div>

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
            icon: Receipt,
            title: t("empty"),
            description: t("emptyBody"),
          }}
        />
      )}

      <SubscriptionReviewModal
        selected={selected}
        open={selected !== null && dialog === null}
        locale={locale}
        t={t}
        tc={tc}
        canMarkPaid={!!canMarkPaid}
        canCancel={canCancel}
        onClose={() => setSelected(null)}
        onOpenMarkPaid={() => {
          setPaymentRef("");
          setTextError(null);
          setDialog("markPaid");
        }}
        onOpenCancel={() => {
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
