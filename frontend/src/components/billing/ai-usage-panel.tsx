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
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import {
  aiAssistantApi,
  type AiUsageDetail,
  type AiUsageWindow,
  type BillingAudience,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * AI usage panel for the billing/usage screen (student + partner). Surfaces the
 * caller's real AI request consumption from `GET /ai/usage/summary`:
 *   - daily + weekly quota meters (the same two gates the backend enforces) with
 *     a live reset countdown,
 *   - a per-feature breakdown over the last 30 days,
 *   - a recent-activity list.
 *
 * Request counts only — no provider/model names, tokens, cost, or latency ever
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
        <div className="space-y-3 rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]">
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
  data: AiUsageDetail;
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

  const dayReset = relativeTime(data.day_reset, locale);
  const weekReset = relativeTime(data.week_reset, locale);

  return (
    <div className="space-y-4 rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)]">
      {/* Meters */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Meter
          label={t("usage.dayLabel")}
          window={data.day}
          blocked={data.blocked_scope === "day"}
          countLabel={t("usage.count", {
            used: data.day.used,
            limit: data.day.limit,
          })}
          resetLabel={dayReset ? t("usage.resetsIn", { when: dayReset }) : null}
        />
        <Meter
          label={t("usage.weekLabel")}
          window={data.week}
          blocked={data.blocked_scope === "week"}
          countLabel={t("usage.count", {
            used: data.week.used,
            limit: data.week.limit,
          })}
          resetLabel={weekReset ? t("usage.resetsIn", { when: weekReset }) : null}
        />
      </div>

      {/* Warning / blocked banner */}
      {data.blocked ? (
        <Banner tone="error">
          {data.blocked_scope === "week"
            ? t("usage.blockedWeek", { when: weekReset ?? "" })
            : t("usage.blockedDay", { when: dayReset ?? "" })}
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

function Meter({
  label,
  window: w,
  blocked,
  countLabel,
  resetLabel,
}: {
  label: string;
  window: AiUsageWindow;
  blocked: boolean;
  countLabel: string;
  resetLabel: string | null;
}) {
  const critical = blocked || w.pct >= 95;
  const warning = !critical && w.pct >= 80;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
          {countLabel}
        </span>
      </div>
      <div
        role="meter"
        aria-valuenow={w.pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none",
            critical
              ? "bg-[var(--red-600)]"
              : warning
                ? "bg-[var(--amber-500)]"
                : "bg-[var(--text-primary)]",
          )}
          style={{ width: `${Math.max(w.pct, w.used > 0 ? 4 : 0)}%` }}
        />
      </div>
      {resetLabel && (
        <p className="mt-1 text-xs text-[var(--text-muted)]">{resetLabel}</p>
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
