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
  LightbulbFilament,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { StackedBarChart, TimeSeriesChart } from "@/components/ui/charts";
import { dashboardsApi, type PartnerAnalytics } from "@/lib/api";

const ANALYTICS_KEY = ["dashboards", "partner", "analytics"] as const;

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

export function PartnerAnalyticsScreen() {
  const t = useTranslations("analytics");
  const tNav = useTranslations("nav");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const query = useQuery({
    queryKey: ANALYTICS_KEY,
    queryFn: () => dashboardsApi.partnerAnalytics(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  const data = query.data;

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

  // Chart-ready projections of the real API data (no fabrication).
  const funnelData = (data?.funnel ?? []).map((item) => ({
    stage: STATUS_LABELS[item.status] ?? item.status,
    count: item.count,
  }));
  const monthlyData = (data?.monthly_trend ?? []).map((pt) => ({
    month: formatMonth(pt.month).split(" ")[0] ?? pt.month,
    applications: pt.count,
  }));

  return (
    <>
      <PageHeader eyebrow={tNav("group.growth")} title={t("title")} description={t("subtitle")} />

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
              icon={<Users aria-hidden weight="duotone" className="size-5 text-white" />}
              iconBg="icon-chip-primary"
            />
            <StatTile
              label={t("statShortlisted")}
              value={shortlistedCount}
              icon={<SealCheck aria-hidden weight="duotone" className="size-5 text-white" />}
              iconBg="icon-chip-success"
            />
            <StatTile
              label={t("statHired")}
              value={hiredCount}
              icon={<Trophy aria-hidden weight="duotone" className="size-5 text-white" />}
              iconBg="icon-chip-success"
            />
            <StatTile
              label={t("statMonthlyPeak")}
              value={trendPeak}
              icon={
                isTrendUp
                  ? <TrendUp aria-hidden weight="duotone" className="size-5 text-white" />
                  : <TrendDown aria-hidden weight="duotone" className="size-5 text-white" />
              }
              iconBg={isTrendUp ? "icon-chip-info" : "icon-chip-warning"}
            />
          </div>

          {/* Hiring insights — deterministic rollups of the metrics above (not model output). */}
          <section
            aria-labelledby="ai-insights-heading"
            className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-subtle)] p-5 "
          >
            <h2
              id="ai-insights-heading"
              className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
            >
              <span className="icon-chip-neutral flex size-8 shrink-0 items-center justify-center rounded-xl">
                <ChartLineUp aria-hidden weight="duotone" className="size-4.5" />
              </span>
              {t("aiInsightsTitle")}
            </h2>
            <ul className="space-y-3">
              {insights.map((insight, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full icon-chip-info shadow-sm">
                    <LightbulbFilament aria-hidden weight="duotone" className="size-3 text-white" />
                  </span>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{t(insight.key, insight.values)}</p>
                </li>
              ))}
            </ul>
          </section>

          {/* Application Funnel */}
          <section
            aria-labelledby="funnel-heading"
            className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 "
          >
            <h2
              id="funnel-heading"
              className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                <ChartBar
                  aria-hidden
                  weight="duotone"
                  className="size-4.5 text-white"
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
              <StackedBarChart
                data={funnelData}
                xKey="stage"
                series={[{ key: "count", label: t("funnelSeriesLabel") }]}
                height={260}
                ariaLabel={t("funnelTitle")}
                emptyLabel={t("funnelEmpty")}
              />
            )}
          </section>

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            {/* Monthly Trend */}
            <section
              aria-labelledby="trend-heading"
              className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 "
            >
              <h2
                id="trend-heading"
                className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-success shadow-sm">
                  <ChartLine
                    aria-hidden
                    weight="duotone"
                    className="size-4.5 text-white"
                  />
                </span>
                {t("trendTitle")}
              </h2>

              {data.monthly_trend.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">{t("trendEmpty")}</p>
              ) : (
                <TimeSeriesChart
                  data={monthlyData}
                  xKey="month"
                  series={[
                    { key: "applications", label: t("trendSeriesLabel"), type: "area" },
                  ]}
                  height={200}
                  ariaLabel={t("trendTitle")}
                  emptyLabel={t("trendEmpty")}
                />
              )}
            </section>

            {/* Top Jobs */}
            <section
              aria-labelledby="topjobs-heading"
              className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 "
            >
              <h2
                id="topjobs-heading"
                className="mb-4 flex items-center gap-2 text-base font-bold text-[var(--text-primary)]"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
                  <Trophy
                    aria-hidden
                    weight="duotone"
                    className="size-4.5 text-white"
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
                        className="flex items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-2.5 outline-none transition-colors hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                      >
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-full icon-chip-primary text-[11px] font-bold text-white shadow-sm">
                          {i + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--text-primary)]">
                          {job.title}
                        </span>
                        <span className="shrink-0 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-0.5 text-xs font-bold text-[var(--text-secondary)]">
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
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
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

function AnalyticsSkeleton() {
  return (
    <div className="space-y-8">
      {/* Stat tile skeletons */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-4 ">
            <Skeleton className="mb-3 size-10 rounded-xl" />
            <Skeleton className="mb-1 h-7 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        ))}
      </div>
      {/* Insights skeleton */}
      <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 ">
        <Skeleton className="mb-4 h-6 w-1/3" />
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
      {/* Funnel skeleton */}
      <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 ">
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
        <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 ">
          <Skeleton className="mb-4 h-6 w-1/3" />
          <Skeleton className="h-32 w-full" />
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 ">
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
