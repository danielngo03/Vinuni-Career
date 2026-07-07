"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  Briefcase,
  ChartBar,
  ChartLine,
  Trophy,
  WarningCircle,
  Users,
  TrendUp,
  TrendDown,
  ChartLineUp,
  SealCheck,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, InsightPanel, Skeleton, type InsightItem } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { dashboardsApi, type AnalyticsMonthlyPoint, type PartnerAnalytics } from "@/lib/api";

const ANALYTICS_KEY = ["dashboards", "partner", "analytics"] as const;

/** Funnel stage color map using design tokens. */
const FUNNEL_COLOR: Record<string, string> = {
  submitted: "bg-[var(--brand-primary)]",
  under_review: "bg-[var(--brand-primary)]/80",
  shortlisted: "bg-[var(--teal-600)]",
  interview: "bg-[var(--teal-600)]",
  offer: "bg-[var(--teal-700)]",
  hired: "bg-[var(--teal-700)]",
  rejected: "bg-[var(--brand-red)]/70",
  withdrawn: "bg-[var(--text-muted)]/50",
};

function formatMonth(iso: string): string {
  if (!iso || iso.length < 7) return iso;
  const [year, month] = iso.split("-");
  const d = new Date(Number(year), Number(month) - 1, 1);
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

interface InsightEntry {
  key: string;
  values?: Record<string, string | number>;
}

/** Derive structured hiring insights from funnel and trend data. */
function deriveInsights(data: PartnerAnalytics): InsightEntry[] {
  const insights: InsightEntry[] = [];
  const byStatus = Object.fromEntries(data.funnel.map((f) => [f.status, f.count]));
  const submitted = byStatus.submitted ?? 0;
  const shortlisted = byStatus.shortlisted ?? 0;
  const hired = byStatus.hired ?? 0;
  const rejected = byStatus.rejected ?? 0;
  const trend = data.monthly_trend;

  if (submitted > 0) {
    const shortlistRate = shortlisted / submitted;
    if (shortlistRate < 0.15) {
      insights.push({ key: "insightLowShortlist" });
    } else if (shortlistRate > 0.5) {
      insights.push({ key: "insightHighShortlist" });
    }
  }

  if (submitted > 0 && hired > 0) {
    const hireRate = Math.round((hired / submitted) * 1000) / 10;
    insights.push({
      key: hireRate < 5 ? "insightConversionLow" : "insightConversionHigh",
      values: { rate: hireRate },
    });
  }

  if (rejected > 0 && submitted > 0 && rejected / submitted > 0.6) {
    insights.push({ key: "insightHighRejection" });
  }

  if (trend.length >= 2) {
    const last = trend[trend.length - 1]?.count ?? 0;
    const prev = trend[trend.length - 2]?.count ?? 0;
    if (last > prev * 1.3) {
      insights.push({ key: "insightTrendUp" });
    } else if (last < prev * 0.7) {
      insights.push({ key: "insightTrendDown" });
    }
  }

  const topJob = data.top_jobs[0];
  if (topJob && topJob.application_count > 20) {
    insights.push({ key: "insightTopJob", values: { title: topJob.title, count: topJob.application_count } });
  }

  if (insights.length === 0) {
    insights.push({ key: "insightNoData" });
  }

  return insights.slice(0, 3);
}

const ANALYTICS_INSIGHT_TONE: Record<string, InsightItem["tone"]> = {
  insightLowShortlist: "warning",
  insightHighShortlist: "success",
  insightConversionLow: "warning",
  insightConversionHigh: "success",
  insightHighRejection: "danger",
  insightTrendUp: "success",
  insightTrendDown: "warning",
  insightTopJob: "neutral",
  insightNoData: "neutral",
};

export function PartnerAnalyticsScreen() {
  const t = useTranslations("analytics");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const query = useQuery({
    queryKey: ANALYTICS_KEY,
    queryFn: () => dashboardsApi.partnerAnalytics(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  const data = query.data;

  const maxFunnel = data
    ? Math.max(...data.funnel.map((f) => f.count), 1)
    : 1;
  const maxMonthly = data
    ? Math.max(...data.monthly_trend.map((m) => m.count), 1)
    : 1;

  // Summary stats derived from funnel data
  const totalApplications = data
    ? data.funnel.find((f) => f.status === "submitted")?.count ?? data.funnel.reduce((s, f) => s + f.count, 0)
    : undefined;
  const hiredCount = data?.funnel.find((f) => f.status === "hired")?.count;
  const shortlistedCount = data?.funnel.find((f) => f.status === "shortlisted")?.count;
  const trendPeak = data?.monthly_trend.length
    ? Math.max(...data.monthly_trend.map((m) => m.count))
    : undefined;
  const trendLast = data?.monthly_trend.at(-1)?.count;
  const trendPrev = data?.monthly_trend.at(-2)?.count;
  const isTrendUp = trendLast !== undefined && trendPrev !== undefined && trendLast > trendPrev;

  const insights = data ? deriveInsights(data) : [];

  const STATUS_LABELS: Record<string, string> = {
    submitted: t("statusLabels.submitted"),
    under_review: t("statusLabels.underReview"),
    shortlisted: t("statusLabels.shortlisted"),
    interview: t("statusLabels.interview"),
    offer: t("statusLabels.offer"),
    hired: t("statusLabels.hired"),
    rejected: t("statusLabels.rejected"),
    withdrawn: t("statusLabels.withdrawn"),
  };

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {query.isPending && <AnalyticsSkeleton />}

      {query.isError && (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void query.refetch()}
            >
              <ArrowClockwise aria-hidden weight="bold" className="size-4" />
              {tc("retry")}
            </Button>
          }
        />
      )}

      {data && (
        <div className="space-y-8">
          {/* Summary stat tiles */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile
              label={t("statTotalApplications")}
              value={totalApplications}
              icon={<Users aria-hidden weight="duotone" className="size-5" />}
              iconBg="icon-chip-primary"
            />
            <StatTile
              label={t("statShortlisted")}
              value={shortlistedCount}
              icon={<SealCheck aria-hidden weight="duotone" className="size-5" />}
              iconBg="icon-chip-success"
            />
            <StatTile
              label={t("statHired")}
              value={hiredCount}
              icon={<Trophy aria-hidden weight="duotone" className="size-5" />}
              iconBg="icon-chip-success"
            />
            <StatTile
              label={t("statMonthlyPeak")}
              value={trendPeak}
              icon={
                isTrendUp
                  ? <TrendUp aria-hidden weight="duotone" className="size-5" />
                  : <TrendDown aria-hidden weight="duotone" className="size-5" />
              }
              iconBg={isTrendUp ? "icon-chip-info" : "icon-chip-warning"}
            />
          </div>

          {/* Derived hiring signals */}
          <InsightPanel
            title={t("aiInsightsTitle")}
            icon={<ChartLineUp aria-hidden weight="duotone" className="size-4" />}
            items={insights.map((insight) => ({
              label: t(insight.key, insight.values),
              tone: ANALYTICS_INSIGHT_TONE[insight.key],
            }))}
          />

          {/* Application Funnel */}
          <section
            aria-labelledby="funnel-heading"
            className="rounded-2xl border border-[var(--border-default)] bg-white p-5 "
          >
            <h2
              id="funnel-heading"
              className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                <ChartBar
                  aria-hidden
                  weight="duotone"
                  className="size-4.5"
                />
              </span>
              {t("funnelTitle")}
            </h2>

            {data.funnel.length === 0 ? (
              <EmptyState
                kind="empty"
                icon={Briefcase}
                title={t("funnelEmpty")}
                description={t("funnelEmptyBody")}
              />
            ) : (
              <ul className="space-y-2.5" role="list">
                {data.funnel.map((item) => {
                  const pct = Math.max(2, (item.count / maxFunnel) * 100);
                  const barColor = FUNNEL_COLOR[item.status] ?? "bg-[var(--brand-primary)]";
                  return (
                    <li key={item.status}>
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[var(--text-secondary)]">
                          {STATUS_LABELS[item.status] ?? item.status}
                        </span>
                        <span className="text-xs font-bold tabular-nums text-[var(--text-primary)]">
                          {item.count}
                        </span>
                      </div>
                      <div
                        role="meter"
                        aria-valuenow={item.count}
                        aria-valuemin={0}
                        aria-valuemax={maxFunnel}
                        aria-label={STATUS_LABELS[item.status] ?? item.status}
                        className="h-3 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
                      >
                        <div
                          className={`h-full rounded-full transition-[width] duration-700 motion-reduce:transition-none ${barColor}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            {/* Monthly Trend */}
            <section
              aria-labelledby="trend-heading"
              className="rounded-2xl border border-[var(--border-default)] bg-white p-5 "
            >
              <h2
                id="trend-heading"
                className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-success shadow-sm">
                  <ChartLine
                    aria-hidden
                    weight="duotone"
                    className="size-4.5"
                  />
                </span>
                {t("trendTitle")}
              </h2>

              {data.monthly_trend.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">{t("trendEmpty")}</p>
              ) : (
                <MonthlyBars points={data.monthly_trend} maxValue={maxMonthly} />
              )}
            </section>

            {/* Top Jobs */}
            <section
              aria-labelledby="topjobs-heading"
              className="rounded-2xl border border-[var(--border-default)] bg-white p-5 "
            >
              <h2
                id="topjobs-heading"
                className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
                  <Trophy
                    aria-hidden
                    weight="duotone"
                    className="size-4.5"
                  />
                </span>
                {t("topJobsTitle")}
              </h2>

              {data.top_jobs.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">{t("topJobsEmpty")}</p>
              ) : (
                <ol className="space-y-2" role="list">
                  {data.top_jobs.map((job, i) => (
                    <li key={job.job_id}>
                      <Link
                        href={`/partner/jobs/${job.job_id}/applications`}
                        className="flex items-center gap-3 rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 outline-none transition-colors hover:bg-white focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                      >
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-full icon-chip-primary text-[11px] font-bold text-[var(--text-primary)] shadow-sm">
                          {i + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--text-primary)]">
                          {job.title}
                        </span>
                        <span className="shrink-0 rounded-full border border-[var(--border-default)] bg-white px-2 py-0.5 text-xs font-bold text-[var(--text-secondary)]">
                          {job.application_count}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        </div>
      )}
    </>
  );
}

function StatTile({
  label,
  value,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value?: number;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]">
      <div className={`mb-3 flex size-10 items-center justify-center rounded-xl shadow-sm ${iconBg}`}>
        {icon}
      </div>
      <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
        {value ?? "—"}
      </p>
      <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}

function MonthlyBars({
  points,
  maxValue,
}: {
  points: AnalyticsMonthlyPoint[];
  maxValue: number;
}) {
  return (
    <div className="flex h-32 items-end gap-1.5" aria-hidden>
      {points.map((pt) => {
        const heightPct = Math.max(4, (pt.count / maxValue) * 100);
        return (
          <div
            key={pt.month}
            className="flex flex-1 flex-col items-center gap-1"
            title={`${formatMonth(pt.month)}: ${pt.count}`}
          >
            <span className="text-[9px] font-semibold tabular-nums text-[var(--text-muted)]">
              {pt.count}
            </span>
            <div
              className="w-full rounded-t-md bg-[var(--brand-primary)] transition-[height] duration-700 motion-reduce:transition-none"
              style={{ height: `${heightPct}%` }}
            />
            <span className="truncate text-[9px] text-[var(--text-muted)]">
              {formatMonth(pt.month).split(" ")[0]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-8">
      {/* Stat tile skeletons */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 ">
            <Skeleton className="mb-3 size-10 rounded-xl" />
            <Skeleton className="mb-1 h-7 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        ))}
      </div>
      {/* Insights skeleton */}
      <div className="rounded-2xl border border-[var(--border-default)] bg-white p-5 ">
        <Skeleton className="mb-4 h-6 w-1/3" />
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
      {/* Funnel skeleton */}
      <div className="rounded-2xl border border-[var(--border-default)] bg-white p-5 ">
        <Skeleton className="mb-4 h-6 w-1/3" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i}>
              <div className="mb-1 flex justify-between">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-8" />
              </div>
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-5 ">
          <Skeleton className="mb-4 h-6 w-1/3" />
          <Skeleton className="h-32 w-full" />
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-5 ">
          <Skeleton className="mb-4 h-6 w-1/3" />
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
