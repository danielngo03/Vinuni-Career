"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Gauge,
  ChartBar,
  ClockCounterClockwise,
  WarningCircle,
  CheckCircle,
  XCircle,
  Lightning,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import {
  aiAssistantApi,
  type AiEnergyUsageDetail,
  type BillingAudience,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * AI energy panel for the billing/usage screen (student + partner). Surfaces the
 * caller's real AI consumption from `GET /ai/usage/summary` under the
 * cost-weighted "energy" model (owner-locked 2026-07-08):
 *   - remaining weekly energy as a single meter (with the week-reset time),
 *   - weekly energy credits used vs the allowance (plus any top-up reserve),
 *   - a rolling-3h burst indicator,
 *   - a per-feature breakdown over the reporting window,
 *   - a recent-activity list.
 *
 * Energy is opaque — no provider/model names, tokens, cost, or latency ever
 * reach this surface (AI_PRODUCT_SPEC §15). The backend returns stable feature
 * CODES which this component localizes via `billing.usage.features.*`.
 */
export function AiUsagePanel({ audience }: { audience: BillingAudience }) {
  const t = useTranslations("billing");
  const locale = useLocale();

  const q = useQuery({
    queryKey: ["ai", "usage", "summary"],
    queryFn: () => aiAssistantApi.myUsageDetail(),
    staleTime: 60_000,
    retry: false,
  });

  const heading = (
    <div className="mb-2.5 flex items-center gap-2">
      <span className="flex size-7 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
        <Gauge aria-hidden weight="duotone" className="size-4 text-white" />
      </span>
      <div>
        <h2 className="text-sm font-bold text-[var(--text-primary)]">
          {t("usage.title")}
        </h2>
        <p className="text-xs text-[var(--text-secondary)]">
          {t("usage.subtitle", { days: q.data?.window_days ?? 30 })}
        </p>
      </div>
    </div>
  );

  return (
    <section aria-label={t("usage.title")}>
      {heading}

      {q.isPending ? (
        <div className="space-y-3 marketplace-card rounded-2xl p-4">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-2 w-full" />
        </div>
      ) : q.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("usage.errorTitle")}
          description={t("usage.errorBody")}
          action={
            <Button variant="secondary" onClick={() => q.refetch()}>
              {t("usage.retry")}
            </Button>
          }
        />
      ) : (
        <UsageBody data={q.data} audience={audience} locale={locale} t={t} />
      )}
    </section>
  );
}

function UsageBody({
  data,
  audience,
  locale,
  t,
}: {
  data: AiEnergyUsageDetail;
  audience: BillingAudience;
  locale: string;
  t: ReturnType<typeof useTranslations<"billing">>;
}) {
  const featureLabel = (feature: string) =>
    t.has(`usage.features.${feature}`)
      ? t(`usage.features.${feature}`)
      : t("usage.features.other");

  const maxCount = useMemo(
    () => data.by_feature.reduce((m, f) => Math.max(m, f.count), 0),
    [data.by_feature],
  );

  const weekReset = relativeTime(data.week_reset, locale);
  const isOrg = data.scope === "org";

  return (
    <div className="space-y-4 marketplace-card rounded-2xl p-4">
      {/* Energy meter */}
      <EnergyMeter data={data} weekReset={weekReset} isOrg={isOrg} t={t} />

      {/* Warning / blocked banner */}
      {data.blocked ? (
        <Banner tone="error">
          {data.blocked_reason === "AI_ORG_WEEKLY_ENERGY_EXCEEDED"
            ? t("usage.blockedOrgWeekly", { when: weekReset ?? "" })
            : t("usage.blockedWeekly", { when: weekReset ?? "" })}
          <span className="block font-normal text-[var(--text-secondary)]">
            {t("usage.seePlans")}
          </span>
        </Banner>
      ) : data.warning ? (
        <Banner tone="warning">{t("usage.nearLimit")}</Banner>
      ) : null}

      {data.total === 0 ? (
        <EmptyState
          kind="empty"
          icon={ChartBar}
          title={t("usage.emptyTitle")}
          description={
            audience === "partner"
              ? t("usage.emptyBodyPartner")
              : t("usage.emptyBody")
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* By-feature breakdown */}
          {data.by_feature.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                <ChartBar aria-hidden weight="duotone" className="size-3.5" />
                {t("usage.breakdownTitle")}
              </p>
              <ul className="space-y-2">
                {data.by_feature.map((f) => (
                  <li key={f.feature}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm text-[var(--text-secondary)]">
                        {featureLabel(f.feature)}
                      </span>
                      <span className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                        {t("usage.calls", { count: f.count })}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]">
                      <div
                        className="h-full rounded-full bg-[var(--text-primary)]"
                        style={{
                          width: `${maxCount > 0 ? Math.max(4, Math.round((f.count * 100) / maxCount)) : 0}%`,
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recent activity */}
          {data.recent.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                <ClockCounterClockwise
                  aria-hidden
                  weight="duotone"
                  className="size-3.5"
                />
                {t("usage.recentTitle")}
              </p>
              <ul className="divide-y divide-[var(--border-default)]">
                {data.recent.map((r, i) => (
                  <li
                    key={`${r.at ?? "na"}-${i}`}
                    className="flex items-center justify-between gap-3 py-1.5 text-sm"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {r.ok ? (
                        <CheckCircle
                          aria-hidden
                          weight="fill"
                          className="size-3.5 shrink-0 text-[var(--teal-600)]"
                        />
                      ) : (
                        <XCircle
                          aria-hidden
                          weight="fill"
                          className="size-3.5 shrink-0 text-[var(--red-600)]"
                        />
                      )}
                      <span className="truncate text-[var(--text-secondary)]">
                        {featureLabel(r.feature)}
                        {!r.ok && (
                          <span className="ml-1 text-[var(--text-muted)]">
                            · {t("usage.failed")}
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="shrink-0 tabular-nums text-xs text-[var(--text-muted)]">
                      {relativeTime(r.at, locale, { past: true }) ?? ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EnergyMeter({
  data,
  weekReset,
  isOrg,
  t,
}: {
  data: AiEnergyUsageDetail;
  weekReset: string | null;
  isOrg: boolean;
  t: ReturnType<typeof useTranslations<"billing">>;
}) {
  const pct = Math.round(data.energy_pct);
  const tone = data.blocked ? "critical" : data.warning ? "warning" : "normal";

  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {isOrg ? t("usage.orgPoolLabel") : t("usage.energyLabel")}
          </p>
          <p
            className={cn(
              "text-3xl font-extrabold tabular-nums leading-none",
              tone === "critical"
                ? "text-[var(--red-600)]"
                : "text-[var(--text-primary)]",
            )}
          >
            {t("usage.energyRemaining", { pct })}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {t("usage.weeklyLabel", {
              used: data.weekly.used,
              allowance: data.weekly.allowance,
            })}
          </p>
          {data.weekly.wallet > 0 && (
            <p className="text-xs tabular-nums text-[var(--text-muted)]">
              {t("usage.walletLabel", { wallet: data.weekly.wallet })}
            </p>
          )}
          {weekReset && (
            <p className="text-xs text-[var(--text-muted)]">
              {t("usage.resetsIn", { when: weekReset })}
            </p>
          )}
        </div>
      </div>

      <div
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={isOrg ? t("usage.orgPoolLabel") : t("usage.energyLabel")}
        className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            tone === "critical"
              ? "bg-[var(--red-600)]"
              : tone === "warning"
                ? "bg-[var(--amber-500)]"
                : "bg-[var(--teal-500)]",
          )}
          style={{ width: `${Math.min(100, Math.max(0, data.energy_pct))}%` }}
        />
      </div>

      {data.session_3h.over_soft_cap && !data.blocked && (
        <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--amber-700)]">
          <Lightning aria-hidden weight="fill" className="size-3.5" />
          {t("usage.burstHint")}
        </p>
      )}
    </div>
  );
}

function Banner({
  tone,
  children,
}: {
  tone: "warning" | "error";
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3.5 py-2.5 text-sm font-medium",
        tone === "error"
          ? "border-[var(--red-400)] bg-[var(--red-50)] text-[var(--red-700)]"
          : "border-[var(--amber-400)] bg-[var(--amber-50)] text-[var(--amber-700)]",
      )}
    >
      {children}
    </div>
  );
}

/**
 * Localized relative time from an ISO instant. Returns e.g. "in 3h" for future
 * (reset) instants or "5m ago" for past (activity) instants. `null` when the
 * input is missing. Client-only (uses the current wall clock).
 */
function relativeTime(
  iso: string | null | undefined,
  locale: string,
  opts: { past?: boolean } = {},
): string | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - Date.now();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  const absMin = Math.abs(diffMs) / 60_000;
  let value: number;
  let unit: Intl.RelativeTimeFormatUnit;
  if (absMin < 60) {
    value = Math.round(diffMs / 60_000);
    unit = "minute";
  } else if (absMin < 60 * 24) {
    value = Math.round(diffMs / 3_600_000);
    unit = "hour";
  } else {
    value = Math.round(diffMs / 86_400_000);
    unit = "day";
  }
  // For future reset instants that round to 0, nudge to the next unit so we
  // never render "now" for a reset that is genuinely in the future.
  if (!opts.past && value === 0) {
    value = unit === "minute" ? 1 : value;
  }
  return rtf.format(value, unit);
}
