"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crown,
  Check,
  Minus,
  Clock,
  CheckCircle,
  WarningCircle,
  ShieldWarning,
  SignIn,
  Bank,
  ArrowUp,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Modal,
  Skeleton,
  StatusBadge,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { AiUsagePanel } from "./ai-usage-panel";
import { EnergyWalletPanel, BILLING_PLANS_ANCHOR } from "./energy-wallet-panel";
import {
  useBillingLabels,
  useLimitLabels,
  SUBSCRIPTION_STATUS_TONE,
} from "@/lib/billing/labels";
import { formatVnd, formatWindow, daysUntil } from "@/lib/billing/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  billingApi,
  type BillingAudience,
  type PaymentInstructions,
  type SubscriptionPlan,
} from "@/lib/api";

export function SubscriberBillingScreen({
  audience,
}: {
  audience: BillingAudience;
}) {
  const t = useTranslations("billing");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useBillingLabels();
  const limitLabels = useLimitLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [upgradeTarget, setUpgradeTarget] = useState<SubscriptionPlan | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  /** Bank-transfer details from the just-completed request (session-scoped). */
  const [instructions, setInstructions] = useState<PaymentInstructions | null>(null);

  const mine = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: () => billingApi.getMySubscription(),
    retry: false,
  });

  const plansQuery = useQuery({
    queryKey: ["billing", "plans", audience],
    queryFn: () => billingApi.listPlans(audience),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["billing"] });
    // The CV library counter reflects the subscription tier — refresh it too.
    void qc.invalidateQueries({ queryKey: ["cv", "list"] });
  }

  function handleMutationError(e: unknown) {
    if (e instanceof ApiError) {
      const reason =
        typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (e.isConflict && reason === "subscription_exists") {
        toast.show({
          tone: "error",
          title: t("errors.conflictTitle"),
          description: t("errors.conflictBody"),
        });
        refresh();
        return;
      }
      if (e.isValidation && reason === "plan_audience_mismatch") {
        toast.show({ tone: "error", title: t("errors.audienceMismatch") });
        return;
      }
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const request = useMutation({
    mutationFn: (plan: SubscriptionPlan) =>
      billingApi.requestSubscription(plan.id),
    onSuccess: (res) => {
      setUpgradeTarget(null);
      setInstructions(res.payment_instructions);
      toast.show({ tone: "success", title: t("toast.requested") });
      refresh();
    },
    onError: (e) => {
      setUpgradeTarget(null);
      handleMutationError(e);
    },
  });

  const cancel = useMutation({
    mutationFn: (version: number | undefined) =>
      billingApi.cancelMySubscription(version),
    onSuccess: () => {
      setCancelOpen(false);
      setInstructions(null);
      toast.show({ tone: "success", title: t("toast.cancelled") });
      refresh();
    },
    onError: (e) => {
      setCancelOpen(false);
      handleMutationError(e);
    },
  });

  // Comparison columns ordered by sort_order (free first, then paid tiers).
  const orderedPlans = useMemo(
    () => [...(plansQuery.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [plansQuery.data],
  );
  // The union of grant keys across plans, for aligned comparison rows.
  const limitKeys = useMemo(() => {
    const seen: string[] = [];
    for (const p of orderedPlans) {
      for (const k of Object.keys(p.limits)) {
        if (!seen.includes(k)) seen.push(k);
      }
    }
    return seen;
  }, [orderedPlans]);

  const titleKey = audience === "partner" ? "partnerTitle" : "studentTitle";
  const subtitleKey =
    audience === "partner" ? "partnerSubtitle" : "studentSubtitle";

  /* ---- Permission / auth states ---- */
  if (mine.isError && mine.error instanceof ApiError) {
    const err = mine.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader
            title={t(`subscriber.${titleKey}`)}
            description={t(`subscriber.${subtitleKey}`)}
          />
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

  const data = mine.data;
  const sub = data?.subscription ?? null;
  const currentPlan = sub?.plan ?? data?.default_plan ?? null;
  const effectiveLimits = data?.limits ?? currentPlan?.limits ?? {};
  const isPending = sub?.status === "pending";
  const isActive = sub?.status === "active";
  const isInflight = sub != null;
  const currentCode = currentPlan?.code;
  const endDays = isActive ? daysUntil(sub?.end_at) : null;

  return (
    <>
      <PageHeader
        title={t(`subscriber.${titleKey}`)}
        description={t(`subscriber.${subtitleKey}`)}
      />

      {mine.isError &&
      !(
        mine.error instanceof ApiError &&
        (mine.error.isPermissionError || mine.error.isAuthError)
      ) ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => mine.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {/* ---- Current plan rail ---- */}
          <section
            aria-label={t("current.heading")}
            className="overflow-hidden rounded-2xl border border-[var(--border-default)] bg-white shadow-[0_2px_16px_rgba(11,34,57,0.06)] "
          >
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
                  <Crown aria-hidden weight="duotone" className="size-4 text-white" />
                </span>
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--text-secondary)]">
                  {t("current.heading")}
                </h2>
              </div>
              {sub ? (
                <StatusBadge tone={SUBSCRIPTION_STATUS_TONE[sub.status] ?? "info"}>
                  {labels.status(sub.status, sub.status_label)}
                </StatusBadge>
              ) : (
                <StatusBadge tone="info">{t("current.freeTier")}</StatusBadge>
              )}
            </header>

            {mine.isPending ? (
              <div className="space-y-3 p-4">
                <Skeleton className="h-6 w-48" />
                <Skeleton className="h-4 w-64" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : (
              <div className="p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-lg font-bold text-[var(--text-primary)]">
                    {currentPlan?.name ?? t("current.freeTier")}
                  </h3>
                  {currentPlan && (
                    <p className="text-sm text-[var(--text-secondary)]">
                      {Number(currentPlan.price_amount ?? 0) > 0 ? (
                        <>
                          <span className="font-semibold text-[var(--text-primary)]">
                            {formatVnd(
                              currentPlan.price_amount,
                              currentPlan.currency,
                              locale,
                            )}
                          </span>{" "}
                          ·{" "}
                          {labels.period(
                            currentPlan.billing_period,
                            currentPlan.billing_period_label,
                          )}
                        </>
                      ) : (
                        t("plans.free")
                      )}
                    </p>
                  )}
                </div>

                {/* Active window / expiry */}
                {isActive && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[var(--text-secondary)]">
                    <span>
                      {t("current.window", {
                        window: formatWindow(sub?.start_at, sub?.end_at, locale),
                      })}
                    </span>
                    {endDays != null && endDays >= 0 && (
                      <span
                        className={`inline-flex items-center gap-1 font-semibold ${
                          endDays <= 3
                            ? "text-[var(--brand-red)]"
                            : "text-[var(--teal-600)]"
                        }`}
                      >
                        {endDays <= 3 ? (
                          <Clock aria-hidden weight="duotone" className="size-4" />
                        ) : (
                          <CheckCircle
                            aria-hidden
                            weight="duotone"
                            className="size-4"
                          />
                        )}
                        {endDays <= 0
                          ? t("current.endingSoon")
                          : t("current.daysLeft", { count: endDays })}
                      </span>
                    )}
                  </div>
                )}

                {/* Effective grants */}
                <div className="mt-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("current.grantsTitle")}
                  </p>
                  <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
                    {limitLabels.rows(effectiveLimits).map((row) => (
                      <div
                        key={row.key}
                        className="flex items-center justify-between gap-3 border-b border-[var(--border-default)] py-1 text-sm last:border-0"
                      >
                        <dt className="text-[var(--text-secondary)]">
                          {row.label}
                        </dt>
                        <dd className="font-semibold text-[var(--text-primary)]">
                          {row.display}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>

                {/* Pending → bank-transfer instructions */}
                {isPending && (
                  <PaymentPanel instructions={instructions} noteRef={sub?.id} />
                )}

                {/* Cancel control for an in-flight sub */}
                {isInflight && (
                  <div className="mt-4 flex justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCancelOpen(true)}
                    >
                      {isPending
                        ? t("current.cancelPending")
                        : t("current.cancelActive")}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ---- Student AI energy wallet (masked % + coarse bucket + nudge) ---- */}
          {audience === "student" && <EnergyWalletPanel />}

          {/* ---- AI usage (real consumption from GET /ai/usage/summary) ---- */}
          <AiUsagePanel audience={audience} />

          {/* ---- Plan comparison ---- */}
          <section id={BILLING_PLANS_ANCHOR} aria-label={t("plans.comparisonTitle")} className="scroll-mt-6">
            <div className="mb-2.5">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">
                {t("plans.comparisonTitle")}
              </h2>
              <p className="text-xs text-[var(--text-secondary)]">
                {t("plans.comparisonHint")}
              </p>
            </div>

            {plansQuery.isPending ? (
              <Skeleton className="h-64 w-full" />
            ) : orderedPlans.length === 0 ? (
              <EmptyState
                kind="empty"
                icon={Crown}
                title={t("plans.emptyTitle")}
                description={t("plans.emptyBody")}
              />
            ) : (
              <div className="overflow-x-auto overflow-hidden rounded-2xl border border-[var(--border-default)] bg-white shadow-[0_2px_16px_rgba(11,34,57,0.06)] ">
                <table className="w-full min-w-[480px] border-collapse text-sm">
                  <caption className="sr-only">
                    {t("plans.comparisonTitle")}
                  </caption>
                  <thead>
                    <tr className="border-b border-[var(--border-default)] bg-white/60">
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]"
                      >
                        {t("plans.featureCol")}
                      </th>
                      {orderedPlans.map((p) => {
                        const isCurrent = p.code === currentCode;
                        return (
                          <th
                            key={p.id}
                            scope="col"
                            className="px-4 py-3 text-left align-bottom"
                          >
                            <span className="block font-bold text-[var(--text-primary)]">
                              {p.name}
                            </span>
                            <span className="block text-xs font-normal text-[var(--text-secondary)]">
                              {Number(p.price_amount ?? 0) > 0
                                ? `${formatVnd(p.price_amount, p.currency, locale)} · ${labels.period(p.billing_period, p.billing_period_label)}`
                                : t("plans.free")}
                            </span>
                            {isCurrent && (
                              <span className="mt-1 inline-block rounded-full bg-[var(--brand-primary)]/10 px-2 py-0.5 text-[11px] font-semibold text-[var(--brand-primary)]">
                                {t("plans.currentBadge")}
                              </span>
                            )}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {limitKeys.map((key) => (
                      <tr
                        key={key}
                        className="border-b border-[var(--border-default)] last:border-0"
                      >
                        <th
                          scope="row"
                          className="px-4 py-2.5 text-left font-medium text-[var(--text-secondary)]"
                        >
                          {limitLabels.labelFor(key)}
                        </th>
                        {orderedPlans.map((p) => (
                          <td
                            key={p.id}
                            className="px-4 py-2.5 text-[var(--text-primary)]"
                          >
                            <LimitCell value={p.limits[key]} />
                          </td>
                        ))}
                      </tr>
                    ))}
                    {/* Action row */}
                    <tr className="bg-[var(--bg-subtle)]">
                      <td className="px-4 py-3" />
                      {orderedPlans.map((p) => {
                        const isCurrent = p.code === currentCode;
                        const isFree = Number(p.price_amount ?? 0) <= 0;
                        if (isCurrent) {
                          return (
                            <td key={p.id} className="px-4 py-3">
                              <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--teal-600)]">
                                <CheckCircle
                                  aria-hidden
                                  weight="fill"
                                  className="size-4"
                                />
                                {t("plans.yourPlan")}
                              </span>
                            </td>
                          );
                        }
                        if (isFree) {
                          return <td key={p.id} className="px-4 py-3" />;
                        }
                        return (
                          <td key={p.id} className="px-4 py-3">
                            <Button
                              variant="primary"
                              size="sm"
                              disabled={isInflight}
                              title={
                                isInflight ? t("plans.alreadyInflight") : undefined
                              }
                              onClick={() => setUpgradeTarget(p)}
                            >
                              <ArrowUp aria-hidden weight="bold" className="size-4" />
                              {t("plans.upgrade")}
                            </Button>
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {isInflight && (
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                {t("plans.alreadyInflight")}
              </p>
            )}
          </section>
        </div>
      )}

      {/* Upgrade confirm */}
      <Modal
        open={upgradeTarget !== null}
        onClose={() => setUpgradeTarget(null)}
        title={t("plans.upgradeTitle")}
        description={t("plans.upgradeBody", {
          plan: upgradeTarget?.name ?? "",
          price: upgradeTarget
            ? formatVnd(upgradeTarget.price_amount, upgradeTarget.currency, locale)
            : "",
        })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setUpgradeTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={request.isPending}
              onClick={() => upgradeTarget && request.mutate(upgradeTarget)}
            >
              {t("plans.upgradeConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("plans.upgradeNote")}
        </p>
      </Modal>

      {/* Cancel confirm */}
      <Modal
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title={t("current.cancelTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCancelOpen(false)}>
              {tc("back")}
            </Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() => cancel.mutate(sub?.version)}
            >
              {t("current.cancelConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {isActive ? t("current.cancelActiveNote") : t("current.cancelNote")}
        </p>
      </Modal>
    </>
  );
}

function LimitCell({ value }: { value: number | boolean | string | null | undefined }) {
  if (typeof value === "boolean") {
    return value ? (
      <Check aria-hidden weight="bold" className="size-4 text-[var(--teal-600)]" />
    ) : (
      <Minus aria-hidden weight="bold" className="size-4 text-[var(--text-muted)]" />
    );
  }
  if (value === null || value === undefined) {
    return <span className="text-[var(--text-muted)]">—</span>;
  }
  return <span className="font-semibold">{String(value)}</span>;
}

function PaymentPanel({
  instructions,
  noteRef,
}: {
  instructions: PaymentInstructions | null;
  noteRef?: string;
}) {
  const t = useTranslations("billing.payment");

  if (!instructions) {
    // Reloaded pending state — instructions were only returned at request time.
    return (
      <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-[var(--amber-400)] bg-[var(--amber-50)] px-3.5 py-3 text-sm text-[var(--text-secondary)]">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
          <Clock aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <div>
          <p className="font-semibold text-[var(--text-primary)]">
            {t("pendingTitle")}
          </p>
          <p className="mt-0.5">{t("pendingBody")}</p>
        </div>
      </div>
    );
  }

  const note = noteRef
    ? `${instructions.note_hint}-${noteRef.slice(0, 8).toUpperCase()}`
    : instructions.note_hint;

  return (
    <div className="mt-4 rounded-lg border border-[var(--blue-200)] bg-[var(--blue-50)] p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <Bank aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <h4 className="text-sm font-bold text-[var(--text-primary)]">
          {t("title")}
        </h4>
      </div>
      <p className="mb-3 text-sm text-[var(--text-secondary)]">{t("intro")}</p>
      <dl className="space-y-1.5 text-sm">
        <Row label={t("bank")} value={instructions.bank_name} />
        <Row label={t("accountName")} value={instructions.account_name} />
        <Row label={t("accountNumber")} value={instructions.account_number} mono />
        <Row label={t("note")} value={note} mono highlight />
      </dl>
      <p className="mt-3 text-xs text-[var(--text-muted)]">{t("doneHint")}</p>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[var(--text-secondary)]">{label}</dt>
      <dd
        className={`${mono ? "font-mono" : "font-semibold"} ${
          highlight ? "text-[var(--brand-primary)]" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
