"use client";

import { GearSix, PencilSimple, PlusCircle } from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import { useBillingLabels, useLimitLabels } from "@/lib/billing/labels";
import { formatVnd } from "@/lib/billing/format";
import type { SubscriptionPlan } from "@/lib/api";

export function PlanCatalogSection({
  plans,
  loading,
  locale,
  t,
  onCreate,
  onEdit,
}: {
  plans: SubscriptionPlan[];
  loading: boolean;
  locale: string;
  t: ReturnType<typeof import("next-intl").useTranslations>;
  onCreate: () => void;
  onEdit: (plan: SubscriptionPlan) => void;
}) {
  const labels = useBillingLabels();
  const limitLabels = useLimitLabels();

  return (
    <section className="mb-5 rounded-2xl border border-[var(--border-default)] bg-white p-5 shadow-[0_2px_16px_rgba(11,34,57,0.06)] ">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex size-9 items-center justify-center rounded-lg icon-chip-info text-white shadow-sm">
              <GearSix aria-hidden weight="duotone" className="size-5" />
            </span>
            <h2 className="text-base font-bold text-[var(--text-primary)]">
              {t("planCatalogTitle")}
            </h2>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {t("planCatalogSubtitle")}
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={onCreate}>
          <PlusCircle aria-hidden weight="bold" className="size-4" />
          {t("planCreate")}
        </Button>
      </div>

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-36 animate-pulse rounded-xl border border-[var(--border-default)] bg-white/60"
            />
          ))}
        </div>
      ) : plans.length === 0 ? (
        <p className="rounded-xl border border-[var(--border-default)] bg-white px-4 py-3 text-sm text-[var(--text-secondary)]">
          {t("planEmpty")}
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {plans.map((plan) => {
            const limitRows = limitLabels.rows(plan.limits).slice(0, 4);
            return (
              <article
                key={plan.id}
                className="rounded-xl border border-[var(--border-default)] bg-white p-4 shadow-[0_1px_10px_rgba(11,34,57,0.05)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-[var(--text-primary)]">
                      {plan.name}
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                      {labels.audience(plan.audience, plan.audience_label)} ·{" "}
                      {formatVnd(plan.price_amount, plan.currency, locale)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="xs"
                    aria-label={t("planEdit")}
                    onClick={() => onEdit(plan)}
                  >
                    <PencilSimple aria-hidden weight="bold" className="size-4" />
                  </Button>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {plan.is_default && (
                    <StatusBadge tone="info">{t("planDefault")}</StatusBadge>
                  )}
                  <StatusBadge tone={plan.is_visible ? "active" : "closed"}>
                    {plan.is_visible ? t("planVisible") : t("planHidden")}
                  </StatusBadge>
                </div>
                <dl className="mt-3 space-y-1.5">
                  {limitRows.map((row) => (
                    <div key={row.key} className="flex justify-between gap-3 text-xs">
                      <dt className="truncate text-[var(--text-secondary)]">
                        {row.label}
                      </dt>
                      <dd className="shrink-0 font-semibold text-[var(--text-primary)]">
                        {row.display}
                      </dd>
                    </div>
                  ))}
                </dl>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
