"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Briefcase,
  FileText,
  Gauge,
  Layers,
  ListChecks,
  Mail,
  Plus,
  Send,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  UserRound,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  ActivityFeed,
  type ActivityEntry,
  AreaChart,
  AttentionPanel,
  type AttentionItem,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardToolbar,
  DataTable,
  type ColumnDef,
  DonutChart,
  EmptyState,
  FunnelChart,
  GradientHeroCard,
  HorizontalBars,
  type HorizontalBarDatum,
  KpiRow,
  KpiTile,
  type KpiDelta,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { formatRelativeTime } from "@/lib/format";
import { dashboardsApi, ApiError } from "@/lib/api";
import type {
  PartnerDashboardOps,
  PartnerOpsTodo,
  PartnerJobPerformanceRow,
  PartnerTopJobRow,
  AnalyticsMonthlyPoint,
} from "@/lib/api/dashboards";
import { useAuthStore } from "@/stores/auth-store";
import { DashboardGuestGate } from "./dashboard-kit";

const nf = new Intl.NumberFormat();

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function trendDelta(points: AnalyticsMonthlyPoint[]): KpiDelta | undefined {
  if (points.length < 2) return undefined;
  const last = points[points.length - 1]!.count;
  const prev = points[points.length - 2]!.count;
  if (prev === 0) return undefined;
  const pct = Math.round(((last - prev) / prev) * 100);
  return {
    value: `${pct > 0 ? "+" : ""}${pct}%`,
    direction: pct > 0 ? "up" : pct < 0 ? "down" : "flat",
    good: pct >= 0,
  };
}

const TODO_META: Record<string, { icon: React.ElementType; tone: (p: PartnerOpsTodo["priority"]) => ChipTone }> = {
  applications_to_review: { icon: ListChecks, tone: () => "warning" },
  offers_to_approve: { icon: Send, tone: () => "info" },
  offers_to_send: { icon: Send, tone: () => "info" },
  unread_messages: { icon: Mail, tone: () => "info" },
  jobs_pending_review: { icon: FileText, tone: () => "warning" },
  jobs_in_draft: { icon: FileText, tone: () => "neutral" },
  review_access_alerts: { icon: ShieldAlert, tone: () => "danger" },
  post_job: { icon: Briefcase, tone: () => "info" },
};

const PRIORITY_TONE: Record<PartnerOpsTodo["priority"], ChipTone> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                    */
/* -------------------------------------------------------------------------- */

function CommandCenterSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-40 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-40 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Partner Recruiting Command Center — the v10 flagship exemplar. Wires the real
 * partner ops + analytics + pipeline projections into the locked design system:
 * KPI row, gradient hero, funnel, pipeline-health donut, applications trend,
 * job-performance table, the ops todo queue, team activity, access alerts,
 * engagement, and advisory AI. Every widget degrades honestly (loading / empty /
 * permission-locked) and never fabricates data. This is the pattern every other
 * partner + university surface copies.
 */
export function PartnerCommandCenter() {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const locale = useLocale();
  const authed = useAuthStore((s) => s.status === "authenticated");
  const userName = useAuthStore((s) => s.user?.name ?? null);

  const opsQ = useQuery({
    queryKey: ["dashboard", "partner", "ops"],
    queryFn: () => dashboardsApi.partnerOps(),
    enabled: authed,
    retry: false,
  });
  const analyticsQ = useQuery({
    queryKey: ["dashboard", "partner", "analytics"],
    queryFn: () => dashboardsApi.partnerAnalytics(),
    enabled: authed,
    retry: false,
  });
  const pipelineQ = useQuery({
    queryKey: ["dashboard", "partner", "pipeline-overview"],
    queryFn: () => dashboardsApi.partnerPipelineOverview(),
    enabled: authed,
    retry: false,
  });

  const offline = opsQ.error instanceof ApiError && opsQ.error.code === "NETWORK_ERROR";

  const header = (
    <PageHeader
      title={tf("title")}
      meta={
        userName || opsQ.data?.org_name ? (
          <>
            {userName && (
              <span className="inline-flex items-center gap-1.5">
                <UserRound className="size-3.5" strokeWidth={1.8} />
                {tf("greeting", { name: userName })}
              </span>
            )}
            {opsQ.data?.org_name && (
              <span className="inline-flex items-center gap-1.5">
                <Briefcase className="size-3.5" strokeWidth={1.8} />
                {opsQ.data.org_name}
              </span>
            )}
          </>
        ) : undefined
      }
      actions={
        <>
          <Link href="/partner/analytics">
            <Button variant="secondary" size="sm">
              <BarChart3 className="size-4" strokeWidth={1.8} />
              {tf("viewAnalytics")}
            </Button>
          </Link>
          <Link href="/partner/jobs/new">
            <Button variant="primary" size="sm">
              <Plus className="size-4" strokeWidth={2} />
              {tf("postJob")}
            </Button>
          </Link>
        </>
      }
    />
  );

  if (!authed) {
    return (
      <>
        {header}
        <DashboardGuestGate persona="partner" />
      </>
    );
  }
  if (opsQ.isPending) {
    return (
      <>
        {header}
        <CommandCenterSkeleton />
      </>
    );
  }
  if (opsQ.isError) {
    return (
      <>
        {header}
        <EmptyState
          kind={offline ? "offline" : "error"}
          title={offline ? tf("offlineTitle") : tf("errorTitle")}
          description={offline ? tf("offlineBody") : tf("errorBody")}
          action={
            <Button variant="secondary" onClick={() => opsQ.refetch()}>
              {tf("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const ops = opsQ.data;

  return (
    <>
      {header}
      <div className="space-y-4">
        <KpiSection ops={ops} monthly={analyticsQ.data?.monthly_trend ?? []} />

        {/* Hero + applications trend (left) · pipeline health + funnel (right) */}
        <div className="grid gap-4 lg:grid-cols-3 lg:items-start">
          <div className="space-y-4 lg:col-span-2">
            <HeroSection ops={ops} pipeline={pipelineQ.data} />
            <TrendCard monthly={analyticsQ.data?.monthly_trend ?? []} loading={analyticsQ.isPending} />
          </div>
          <div className="space-y-4">
            <PipelineHealthCard pipeline={pipelineQ.data} loading={pipelineQ.isPending} />
            <FunnelCard funnel={analyticsQ.data?.funnel ?? []} loading={analyticsQ.isPending} />
          </div>
        </div>

        {/* Job performance + operational rail */}
        <div className="grid gap-4 lg:grid-cols-3 lg:items-start">
          <div className="space-y-4 lg:col-span-2">
            <JobPerformanceCard ops={ops} />
            <TeamActivityCard ops={ops} locale={locale} />
          </div>
          <div className="space-y-4">
            <AttentionCard ops={ops} />
            <AccessAlertsCard ops={ops} />
            <ChannelMixCard ops={ops} />
            <EngagementCard ops={ops} />
            <AiCard ops={ops} locale={locale} />
          </div>
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* KPI row                                                                     */
/* -------------------------------------------------------------------------- */

function KpiSection({ ops, monthly }: { ops: PartnerDashboardOps; monthly: AnalyticsMonthlyPoint[] }) {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const m = ops.metrics;
  const spark = monthly.map((p) => p.count);
  const appsDelta = trendDelta(monthly);
  const engagement = m.engagement;
  const conversion = engagement.available && engagement.conversion_rate_pct != null
    ? `${engagement.conversion_rate_pct}%`
    : null;

  return (
    <KpiRow cols={5}>
      <KpiTile label={tf("kpi.openJobs")} value={nf.format(m.jobs_active)} icon={Briefcase} href="/partner/jobs" />
      <KpiTile
        label={tf("kpi.applications")}
        value={nf.format(m.applications_total)}
        icon={ListChecks}
        spark={spark.length > 1 ? spark : undefined}
        delta={appsDelta}
        href="/partner/candidates"
      />
      <KpiTile
        label={tf("kpi.pendingReview")}
        value={nf.format(m.jobs_pending_review)}
        icon={FileText}
        hint={m.jobs_pending_review > 0 ? tf("kpi.pendingReviewHint") : undefined}
        href="/partner/jobs"
      />
      <KpiTile label={tf("kpi.drafts")} value={nf.format(m.jobs_draft)} icon={FileText} href="/partner/jobs" />
      <KpiTile label={tf("kpi.conversion")} value={conversion ?? "—"} icon={TrendingUp} />
    </KpiRow>
  );
}

/* -------------------------------------------------------------------------- */
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

function HeroSection({
  ops,
  pipeline,
  className,
}: {
  ops: PartnerDashboardOps;
  pipeline: import("@/lib/api/dashboards").PartnerPipelineOverview | undefined;
  className?: string;
}) {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const inPlay = pipeline?.total_active ?? ops.metrics.applications_total;
  const roles = pipeline?.jobs.length ?? ops.metrics.jobs_active;
  const engagement = ops.metrics.engagement;
  const conversion = engagement.available && engagement.conversion_rate_pct != null
    ? `${engagement.conversion_rate_pct}%`
    : null;

  const topRoles = React.useMemo(
    () =>
      (pipeline?.jobs ?? [])
        .filter((j) => j.active_total > 0)
        .sort((a, b) => b.active_total - a.active_total)
        .slice(0, 3),
    [pipeline],
  );

  return (
    <GradientHeroCard
      className={className}
      eyebrow={tf("heroEyebrow")}
      icon={Layers}
      title={tf("heroTitle")}
      value={nf.format(inPlay)}
      caption={tf("heroCaption", { roles, apps: nf.format(ops.metrics.applications_total) })}
      aside={
        topRoles.length > 0 ? (
          <div className="w-full space-y-1.5 sm:w-[260px]">
            <div className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-white/70">
              {tf("heroTopRoles")}
            </div>
            {topRoles.map((j) => (
              <div
                key={j.job_id}
                className="flex items-center justify-between gap-3 rounded-lg bg-white/10 px-2.5 py-1.5 backdrop-blur-sm"
              >
                <span className="truncate text-[0.8125rem] font-medium text-white/90">{j.title}</span>
                <span className="shrink-0 text-sm font-bold tabular-nums text-white">
                  {nf.format(j.active_total)}
                </span>
              </div>
            ))}
          </div>
        ) : undefined
      }
      footer={
        <>
          {conversion && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
              <TrendingUp className="size-3.5" strokeWidth={2} />
              {tf("heroConversion", { value: conversion })}
            </span>
          )}
        </>
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Pipeline health                                                             */
/* -------------------------------------------------------------------------- */

function PipelineHealthCard({
  pipeline,
  loading,
}: {
  pipeline: import("@/lib/api/dashboards").PartnerPipelineOverview | undefined;
  loading: boolean;
}) {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const agg = React.useMemo(() => {
    if (!pipeline) return null;
    let active = 0;
    let rejected = 0;
    let withdrawn = 0;
    for (const j of pipeline.jobs) {
      active += j.active_total;
      rejected += j.rejected;
      withdrawn += j.withdrawn;
    }
    return { active, rejected, withdrawn, total: active + rejected + withdrawn };
  }, [pipeline]);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{tf("pipelineHealthTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Gauge className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[200px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : !agg || agg.total === 0 ? (
          <EmptyState kind="empty" title={tf("pipelineEmptyTitle")} description={tf("pipelineEmptyBody")} />
        ) : (
          <>
            <DonutChart
              data={[
                { label: tf("pipelineActive"), value: agg.active, color: "var(--viz-emerald)" },
                { label: tf("pipelineRejected"), value: agg.rejected, color: "var(--viz-rose)" },
                { label: tf("pipelineWithdrawn"), value: agg.withdrawn, color: "var(--border-strong)" },
              ]}
              centerValue={nf.format(agg.active)}
              centerLabel={tf("pipelineCenter")}
              formatValue={(v) => nf.format(v)}
            />
            <ul className="mt-3 space-y-1.5">
              {[
                { label: tf("pipelineActive"), value: agg.active, tone: "emerald" as ChipTone },
                { label: tf("pipelineRejected"), value: agg.rejected, tone: "rose" as ChipTone },
                { label: tf("pipelineWithdrawn"), value: agg.withdrawn, tone: "neutral" as ChipTone },
              ].map((r) => (
                <li key={r.label} className="flex items-center justify-between text-[0.8125rem]">
                  <span className="inline-flex items-center gap-2 text-muted-foreground">
                    <StatusChip tone={r.tone} dot size="sm">
                      {r.label}
                    </StatusChip>
                  </span>
                  <span className="font-semibold tabular-nums text-foreground">{nf.format(r.value)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Funnel                                                                      */
/* -------------------------------------------------------------------------- */

function FunnelCard({
  funnel,
  loading,
}: {
  funnel: import("@/lib/api/dashboards").AnalyticsFunnelItem[];
  loading: boolean;
}) {
  const t = useTranslations("dashboard.partnerOps");
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const stageLabel = (code: string) =>
    tf.has(`stage.${code}`) ? tf(`stage.${code}`) : code.replace(/_/g, " ");

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{tf("funnelTitle")}</CardTitle>
          <CardDescription>{tf("funnelSubtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Target className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-40 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : funnel.length === 0 ? (
          <EmptyState kind="empty" title={tf("funnelEmptyTitle")} description={tf("funnelEmptyBody")} />
        ) : (
          <FunnelChart
            stages={funnel.map((f) => ({ label: stageLabel(f.status), value: f.count }))}
            conversionLabel={tf("funnelOfPrevious")}
            formatValue={(v) => nf.format(v)}
            emptyLabel={t("jobPerformanceEmptyTitle")}
          />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Trend                                                                       */
/* -------------------------------------------------------------------------- */

function TrendCard({ monthly, loading }: { monthly: AnalyticsMonthlyPoint[]; loading: boolean }) {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{tf("trendTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Activity className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[220px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : monthly.length === 0 ? (
          <EmptyState kind="empty" title={tf("trendEmptyTitle")} description={tf("trendEmptyBody")} />
        ) : (
          <AreaChart
            data={monthly.map((p) => ({ month: p.month, count: p.count }))}
            xKey="month"
            series={[{ key: "count", label: tf("trendSeries"), color: "var(--viz-indigo)" }]}
            height={220}
            formatValue={(v) => nf.format(v)}
            ariaLabel={tf("trendTitle")}
          />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Job performance table                                                       */
/* -------------------------------------------------------------------------- */

function JobPerformanceCard({ ops }: { ops: PartnerDashboardOps }) {
  const t = useTranslations("dashboard.partnerOps");
  const widget = ops.job_performance;

  const richCols: ColumnDef<PartnerJobPerformanceRow, unknown>[] = [
    {
      accessorKey: "title",
      header: t("table.job"),
      cell: ({ row }) => (
        <Link
          href={`/partner/jobs/${row.original.job_id}`}
          className="font-semibold text-foreground hover:text-[var(--brand-primary)]"
        >
          {row.original.title}
        </Link>
      ),
    },
    { accessorKey: "impressions", header: t("table.impressions"), meta: { align: "right" }, cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.impressions)}</span> },
    { accessorKey: "detail_views", header: t("table.views"), meta: { align: "right" }, cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.detail_views)}</span> },
    { accessorKey: "applications_submitted", header: t("table.applications"), meta: { align: "right" }, cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.applications_submitted)}</span> },
    {
      accessorKey: "conversion_rate_pct",
      header: t("table.conversion"),
      meta: { align: "right" },
      cell: ({ row }) => <ConversionCell pct={row.original.conversion_rate_pct} />,
    },
  ];

  const fallbackCols: ColumnDef<PartnerTopJobRow, unknown>[] = [
    {
      accessorKey: "title",
      header: t("table.job"),
      cell: ({ row }) => (
        <Link
          href={`/partner/jobs/${row.original.job_id}`}
          className="font-semibold text-foreground hover:text-[var(--brand-primary)]"
        >
          {row.original.title}
        </Link>
      ),
    },
    {
      accessorKey: "application_count",
      header: t("table.applicationCount"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.application_count)}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("jobPerformanceTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Link href="/partner/analytics" className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline">
            {t("flagship.viewAnalytics")}
          </Link>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {widget.locked ? (
          <EmptyState kind="permission" title={t("jobPerformanceLockedTitle")} description={t("jobPerformanceLockedBody")} />
        ) : widget.basis === "job_metrics_daily" ? (
          <DataTable
            columns={richCols}
            data={widget.items}
            getRowId={(r) => r.job_id}
            pageSize={8}
            empty={<EmptyState kind="empty" title={t("jobPerformanceEmptyTitle")} description={t("jobPerformanceEmptyBody")} />}
          />
        ) : (
          <>
            <DataTable
              columns={fallbackCols}
              data={widget.items}
              getRowId={(r) => r.job_id}
              pageSize={8}
              empty={<EmptyState kind="empty" title={t("jobPerformanceEmptyTitle")} description={t("jobPerformanceEmptyBody")} />}
            />
            <p className="mt-2 type-caption text-muted-foreground">{t("jobPerformanceFallbackNote")}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ConversionCell({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const width = Math.max(2, Math.min(100, pct));
  const tone = pct >= 8 ? "var(--viz-emerald)" : pct >= 3 ? "var(--viz-amber)" : "var(--viz-rose)";
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--bg-muted)]">
        <span className="block h-full rounded-full" style={{ width: `${width}%`, background: tone }} />
      </span>
      <span className="w-10 text-right font-semibold tabular-nums text-foreground">{pct}%</span>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Attention / todos                                                           */
/* -------------------------------------------------------------------------- */

function AttentionCard({ ops }: { ops: PartnerDashboardOps }) {
  const t = useTranslations("dashboard.partnerOps");
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const items: AttentionItem[] = ops.todos.map((todo) => {
    const meta = TODO_META[todo.key];
    return {
      key: todo.key,
      label: t.has(`todoLabel.${todo.key}`) ? t(`todoLabel.${todo.key}`) : todo.key,
      href: todo.href,
      icon: meta?.icon ?? ListChecks,
      tone: PRIORITY_TONE[todo.priority],
      count: todo.count,
      meta: t(`priority.${todo.priority}`),
    };
  });

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{tf("attentionTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs font-bold tabular-nums text-muted-foreground">
            {ops.todos.length}
          </span>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <AttentionPanel
          items={items}
          empty={<EmptyState kind="empty" title={t("todoEmptyTitle")} description={t("todoEmptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Access alerts                                                               */
/* -------------------------------------------------------------------------- */

function AccessAlertsCard({ ops }: { ops: PartnerDashboardOps }) {
  const t = useTranslations("dashboard.partnerOps");
  const widget = ops.access_alerts;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("accessAlertsTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Link href="/partner/security" className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline">
            {t("viewAccessLog")}
          </Link>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {widget.locked ? (
          <EmptyState kind="permission" title={t("accessAlertsLockedTitle")} description={t("accessAlertsLockedBody")} />
        ) : widget.items.length === 0 ? (
          <EmptyState kind="empty" title={t("accessAlertsEmptyTitle")} description={t("accessAlertsEmptyBody")} />
        ) : (
          <ul className="space-y-2">
            {widget.items.map((alert, i) => (
              <li
                key={`${alert.code}-${i}`}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5"
                style={{ background: "var(--content-warning-soft)" }}
              >
                <ShieldAlert className="size-4 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-warning)" }} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.8125rem] font-semibold text-foreground">{alert.label}</span>
                  <span className="mt-0.5 block truncate type-caption text-muted-foreground">
                    {alert.actor_name ?? "—"} · {t("alertWindow", { count: alert.count, hours: alert.window_hours })}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Channel / source mix                                                        */
/* -------------------------------------------------------------------------- */

function ChannelMixCard({ ops }: { ops: PartnerDashboardOps }) {
  const tf = useTranslations("dashboard.partnerOps.flagship");
  const widget = ops.job_performance;
  const mix = React.useMemo<HorizontalBarDatum[] | null>(() => {
    if (widget.locked || widget.basis !== "job_metrics_daily") return null;
    const totals = { organic: 0, search: 0, recommendation: 0, sponsored: 0, invitation: 0, direct: 0 };
    for (const row of widget.items) {
      totals.organic += row.source_mix.organic;
      totals.search += row.source_mix.search;
      totals.recommendation += row.source_mix.recommendation;
      totals.sponsored += row.source_mix.sponsored;
      totals.invitation += row.source_mix.invitation;
      totals.direct += row.source_mix.direct;
    }
    const entries = Object.entries(totals).filter(([, v]) => v > 0);
    if (entries.length === 0) return null;
    return entries.map(([k, v]) => ({ label: tf(`source.${k}`), value: v }));
  }, [widget, tf]);

  if (!mix) return null;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{tf("channelTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <HorizontalBars data={mix} formatValue={(v) => nf.format(v)} ariaLabel={tf("channelTitle")} />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Engagement                                                                  */
/* -------------------------------------------------------------------------- */

function EngagementCard({ ops }: { ops: PartnerDashboardOps }) {
  const t = useTranslations("dashboard.partnerOps");
  const engagement = ops.metrics.engagement;
  if (!engagement.available) return null;

  const stats: [string, string][] = [
    ["impressions", nf.format(engagement.impressions)],
    ["detailViews", nf.format(engagement.detail_views)],
    ["ctaClicks", nf.format(engagement.cta_clicks)],
    ["applyStarts", nf.format(engagement.apply_starts)],
    ["applicationsSubmitted", nf.format(engagement.applications_submitted)],
    ["conversion", engagement.conversion_rate_pct != null ? `${engagement.conversion_rate_pct}%` : t("engagement.conversionUnavailable")],
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("engagement.title")}</CardTitle>
        </div>
        <CardToolbar>
          <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-2.5">
          {stats.map(([key, value]) => (
            <div key={key} className="rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2">
              <dt className="type-caption text-muted-foreground">{t(`engagement.${key}`)}</dt>
              <dd className="mt-0.5 text-base font-bold tabular-nums text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* AI recommendations (advisory, masked)                                       */
/* -------------------------------------------------------------------------- */

function AiCard({ ops, locale }: { ops: PartnerDashboardOps; locale: string }) {
  const t = useTranslations("dashboard.partnerOps");
  if (ops.ai_recommendations.length === 0) return null;

  return (
    <Card className="border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span
            className="flex size-7 items-center justify-center rounded-lg"
            style={{ background: "var(--content-ai-soft)" }}
          >
            <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
          </span>
          <CardTitle>{t("aiRecommendationsTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="mb-2 type-caption text-muted-foreground">{t("aiRecommendationsDisclaimer")}</p>
        <ul className="space-y-2">
          {ops.ai_recommendations.map((rec) => (
            <li key={rec.code} className="flex items-start gap-2.5 text-[0.8125rem] text-foreground">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ background: "var(--content-ai)" }} />
              {locale === "vi" ? rec.message_vi : rec.message_en}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Team activity                                                               */
/* -------------------------------------------------------------------------- */

function TeamActivityCard({ ops, locale }: { ops: PartnerDashboardOps; locale: string }) {
  const t = useTranslations("dashboard.partnerOps");
  const items: ActivityEntry[] = ops.team_activity.map((a, i) => ({
    key: `${a.action}-${a.occurred_at}-${i}`,
    icon: Activity,
    tone: "info",
    title: <span className="font-medium">{a.action_label}</span>,
    meta: `${a.actor_name ?? "—"} · ${formatRelativeTime(a.occurred_at, locale)}`,
  }));

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("teamActivityTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Activity className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <ActivityFeed
          items={items}
          empty={<EmptyState kind="empty" title={t("teamActivityEmptyTitle")} description={t("teamActivityEmptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}
