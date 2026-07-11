"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Award,
  BarChart3,
  CalendarRange,
  Clock,
  Download,
  Layers,
  ListChecks,
  MessagesSquare,
  Target,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  AreaChart,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  type ColumnDef,
  EmptyState,
  FunnelChart,
  HorizontalBars,
  type HorizontalBarDatum,
  KpiRow,
  KpiTile,
  type KpiDelta,
  PageHeader,
} from "@/components/kit";
import { dashboardsApi, ApiError } from "@/lib/api";
import type {
  AnalyticsMonthlyPoint,
  AnalyticsTopJob,
  PartnerAnalytics,
  PartnerRecruitingFunnel,
  RecruitingStageOutcome,
} from "@/lib/api/dashboards";

const nf = new Intl.NumberFormat();

type RangeKey = "30" | "90" | "180" | "365" | "all";
const RANGES: RangeKey[] = ["30", "90", "180", "365", "all"];

function rangeToParams(range: RangeKey): { from?: string; to?: string } {
  if (range === "all") return {};
  const days = Number(range);
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

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

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Partner recruiting analytics (v10). Wires the real analytics projections into
 * the locked kit: KPI row, recruiting funnel (with step conversion), per-stage
 * outcomes, time-to-hire, applications trend, source attribution and a top-jobs
 * table. The richer funnel/stage/time metrics come from the §6 recruiting-funnel
 * read; if that read is unavailable the funnel degrades to the base application
 * funnel and the time-based metrics show an honest "not enough data" — never a
 * fabricated number. Charts carry text/table alternatives for screen readers.
 */
export function PartnerAnalyticsScreen() {
  const t = useTranslations("analytics");
  const tStates = useTranslations("states");
  const [range, setRange] = React.useState<RangeKey>("90");

  const baseQ = useQuery({
    queryKey: ["dashboard", "partner", "analytics"],
    queryFn: () => dashboardsApi.partnerAnalytics(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  const funnelQ = useQuery({
    queryKey: ["dashboard", "partner", "recruiting-funnel", range],
    queryFn: () => dashboardsApi.partnerRecruitingFunnel(rangeToParams(range)),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  const opsQ = useQuery({
    queryKey: ["dashboard", "partner", "ops"],
    queryFn: () => dashboardsApi.partnerOps(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

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

  const header = (
    <PageHeaderRow
      title={t("title")}
      subtitle={t("subtitle")}
      range={range}
      onRange={setRange}
      onExport={() => exportCsv(baseQ.data, t("exportFilename"))}
      canExport={!!baseQ.data}
      rangeLabel={t("range.label")}
      rangeText={(r) => t(`range.${r === "all" ? "all" : `d${r}`}`)}
      exportLabel={t("export")}
    />
  );

  /* ---- Permission / auth / error on the base read ---- */
  if (baseQ.isError && baseQ.error instanceof ApiError) {
    const err = baseQ.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  if (baseQ.isPending) {
    return (
      <>
        {header}
        <AnalyticsSkeleton />
      </>
    );
  }

  if (baseQ.isError || !baseQ.data) {
    return (
      <>
        {header}
        <EmptyState
          kind="error"
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void baseQ.refetch()}>
              {t("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const base = baseQ.data;
  const byStatus = Object.fromEntries(base.funnel.map((f) => [f.status, f.count]));
  const applications = byStatus.submitted ?? base.funnel.reduce((s, f) => s + f.count, 0);
  const interview = byStatus.interview ?? 0;
  const offer = byStatus.offer ?? 0;
  const hired = byStatus.hired ?? 0;
  const interviewRate = applications > 0 ? Math.round((interview / applications) * 100) : null;
  const offerRate = applications > 0 ? Math.round((offer / applications) * 100) : null;

  const tth = funnelQ.data?.time_to_hire;
  const tthAvailable = !!tth && !tth.low_signal && tth.median_days != null;

  return (
    <>
      {header}
      <div className="space-y-4">
        {/* KPI row */}
        <KpiRow cols={5}>
          <KpiTile
            label={t("kpi.applications")}
            value={nf.format(applications)}
            icon={ListChecks}
            spark={base.monthly_trend.length > 1 ? base.monthly_trend.map((p) => p.count) : undefined}
            delta={trendDelta(base.monthly_trend)}
          />
          <KpiTile
            label={t("kpi.interviewRate")}
            value={interviewRate != null ? `${interviewRate}%` : "—"}
            icon={MessagesSquare}
            hint={interviewRate != null ? t("kpi.interviewRateHint") : undefined}
          />
          <KpiTile
            label={t("kpi.offerRate")}
            value={offerRate != null ? `${offerRate}%` : "—"}
            icon={Target}
            hint={offerRate != null ? t("kpi.offerRateHint") : undefined}
          />
          <KpiTile label={t("kpi.hires")} value={nf.format(hired)} icon={Award} />
          <KpiTile
            label={t("kpi.timeToHire")}
            value={tthAvailable ? nf.format(tth!.median_days!) : "—"}
            icon={Clock}
            hint={tthAvailable ? t("kpi.timeToHireHint") : t("notEnoughData")}
          />
        </KpiRow>

        {/* Funnel + time-to-hire */}
        <div className="grid gap-4 lg:grid-cols-3">
          <FunnelCard
            recruiting={funnelQ.data}
            base={base}
            statusLabels={STATUS_LABELS}
            ofPrev={t("funnelOfPrev")}
            title={t("funnelTitle")}
            subtitle={t("funnelSubtitle")}
            emptyTitle={t("funnelEmpty")}
            emptyBody={t("funnelEmptyBody")}
            srCaption={t("chartTableSr")}
            colStage={t("table.stage")}
            colCandidates={t("table.candidates")}
            className="lg:col-span-2"
          />
          <TimeToHireCard data={funnelQ.data} />
        </div>

        {/* Stage outcomes + source attribution */}
        <div className="grid gap-4 lg:grid-cols-2">
          <StageOutcomesCard data={funnelQ.data} />
          <SourceAttributionCard ops={opsQ.data} loading={opsQ.isPending} />
        </div>

        {/* Trend + top jobs */}
        <div className="grid gap-4 lg:grid-cols-2">
          <TrendCard monthly={base.monthly_trend} />
          <TopJobsCard jobs={base.top_jobs} />
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Header row (title + range + export)                                         */
/* -------------------------------------------------------------------------- */

function PageHeaderRow({
  title,
  subtitle,
  range,
  onRange,
  onExport,
  canExport,
  rangeLabel,
  rangeText,
  exportLabel,
}: {
  title: string;
  subtitle: string;
  range: RangeKey;
  onRange: (r: RangeKey) => void;
  onExport: () => void;
  canExport: boolean;
  rangeLabel: string;
  rangeText: (r: RangeKey) => string;
  exportLabel: string;
}) {
  return (
    <PageHeader
      title={title}
      subtitle={subtitle}
      actions={
        <>
          <div
            className="inline-flex items-center rounded-lg border border-border bg-card p-0.5"
            role="group"
            aria-label={rangeLabel}
          >
            <CalendarRange
              aria-hidden
              className="ml-1.5 mr-0.5 size-4 text-muted-foreground"
              strokeWidth={1.8}
            />
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onRange(r)}
                aria-pressed={range === r}
                className={
                  "rounded-md px-2.5 py-1 text-[0.8125rem] font-medium transition-colors " +
                  (range === r
                    ? "bg-[var(--bg-subtle)] text-foreground"
                    : "text-muted-foreground hover:text-foreground")
                }
              >
                {rangeText(r)}
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={onExport} disabled={!canExport}>
            <Download className="size-4" strokeWidth={1.8} />
            {exportLabel}
          </Button>
        </>
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Funnel                                                                      */
/* -------------------------------------------------------------------------- */

function FunnelCard({
  recruiting,
  base,
  statusLabels,
  ofPrev,
  title,
  subtitle,
  emptyTitle,
  emptyBody,
  srCaption,
  colStage,
  colCandidates,
  className,
}: {
  recruiting: PartnerRecruitingFunnel | undefined;
  base: PartnerAnalytics;
  statusLabels: Record<string, string>;
  ofPrev: string;
  title: string;
  subtitle: string;
  emptyTitle: string;
  emptyBody: string;
  srCaption: string;
  colStage: string;
  colCandidates: string;
  className?: string;
}) {
  const stages =
    recruiting && recruiting.funnel.length > 0
      ? recruiting.funnel.map((s) => ({ label: s.label || statusLabels[s.stage] || s.stage, value: s.count }))
      : base.funnel.map((f) => ({ label: statusLabels[f.status] ?? f.status, value: f.count }));

  return (
    <Card className={className}>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{subtitle}</CardDescription>
        </div>
        <CardToolbar>
          <Target className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {stages.length === 0 || stages.every((s) => s.value === 0) ? (
          <EmptyState kind="empty" title={emptyTitle} description={emptyBody} />
        ) : (
          <>
            <FunnelChart
              stages={stages}
              conversionLabel={ofPrev}
              formatValue={(v) => nf.format(v)}
            />
            <table className="sr-only">
              <caption>{srCaption}</caption>
              <thead>
                <tr>
                  <th>{colStage}</th>
                  <th>{colCandidates}</th>
                </tr>
              </thead>
              <tbody>
                {stages.map((s) => (
                  <tr key={s.label}>
                    <td>{s.label}</td>
                    <td>{s.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Time-to-hire                                                                */
/* -------------------------------------------------------------------------- */

function TimeToHireCard({ data }: { data: PartnerRecruitingFunnel | undefined }) {
  const t = useTranslations("analytics");
  const tth = data?.time_to_hire;
  const available = !!tth && !tth.low_signal && tth.median_days != null;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("timeToHire.title")}</CardTitle>
          <CardDescription>{t("timeToHire.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Clock className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {!available ? (
          <EmptyState kind="empty" title={t("timeToHire.empty")} description={t("timeToHire.emptyBody")} />
        ) : (
          <div className="space-y-4">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="type-metric text-foreground">{nf.format(tth!.median_days!)}</span>
                <span className="type-small text-muted-foreground">{t("timeToHire.days")}</span>
              </div>
              <p className="type-caption mt-0.5 text-muted-foreground">
                {t("timeToHire.median")} · {t("timeToHire.sample", { count: tth!.sample_size })}
              </p>
            </div>
            {tth!.buckets.length > 0 && (
              <div>
                <p className="type-caption mb-2 font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  {t("timeToHire.distribution")}
                </p>
                <HorizontalBars
                  data={tth!.buckets.map((b) => ({ label: b.label, value: b.count }))}
                  formatValue={(v) => nf.format(v)}
                  ariaLabel={t("timeToHire.distribution")}
                />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Stage outcomes                                                              */
/* -------------------------------------------------------------------------- */

interface StageRow extends RecruitingStageOutcome {
  median_days: number | null;
}

function StageOutcomesCard({ data }: { data: PartnerRecruitingFunnel | undefined }) {
  const t = useTranslations("analytics");
  const rows: StageRow[] = React.useMemo(() => {
    if (!data) return [];
    const medianByStage = new Map(data.time_in_stage.map((s) => [s.stage_type, s.low_signal ? null : s.median_days]));
    return data.stage_outcomes.map((s) => ({ ...s, median_days: medianByStage.get(s.stage_type) ?? null }));
  }, [data]);

  const cols: ColumnDef<StageRow, unknown>[] = [
    {
      accessorKey: "label",
      header: t("stageOutcomes.colStage"),
      cell: ({ row }) => <span className="font-medium text-foreground">{row.original.label}</span>,
    },
    {
      accessorKey: "entered",
      header: t("stageOutcomes.colEntered"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.entered)}</span>,
    },
    {
      accessorKey: "advanced",
      header: t("stageOutcomes.colAdvanced"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.advanced)}</span>,
    },
    {
      accessorKey: "pass_rate_pct",
      header: t("stageOutcomes.passRate"),
      meta: { align: "right" },
      cell: ({ row }) => <PassRateCell pct={row.original.pass_rate_pct} />,
    },
    {
      accessorKey: "median_days",
      header: t("timeInStage.title"),
      meta: { align: "right" },
      cell: ({ row }) =>
        row.original.median_days != null ? (
          <span className="tabular-nums">{t("timeInStage.days", { count: row.original.median_days })}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("stageOutcomes.title")}</CardTitle>
          <CardDescription>{t("stageOutcomes.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <EmptyState kind="empty" title={t("stageOutcomes.empty")} description={t("stageOutcomes.emptyBody")} />
        ) : (
          <DataTable columns={cols} data={rows} getRowId={(r) => r.stage_type} />
        )}
      </CardContent>
    </Card>
  );
}

function PassRateCell({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const width = Math.max(2, Math.min(100, pct));
  const tone = pct >= 60 ? "var(--viz-emerald)" : pct >= 30 ? "var(--viz-amber)" : "var(--viz-rose)";
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-[var(--bg-muted)]">
        <span className="block h-full rounded-full" style={{ width: `${width}%`, background: tone }} />
      </span>
      <span className="w-9 text-right font-semibold tabular-nums text-foreground">{pct}%</span>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Source attribution                                                          */
/* -------------------------------------------------------------------------- */

function SourceAttributionCard({
  ops,
  loading,
}: {
  ops: import("@/lib/api/dashboards").PartnerDashboardOps | undefined;
  loading: boolean;
}) {
  const t = useTranslations("analytics");
  const mix = React.useMemo<HorizontalBarDatum[] | null>(() => {
    const widget = ops?.job_performance;
    if (!widget || widget.locked || widget.basis !== "job_metrics_daily") return null;
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
    return entries.map(([k, v]) => ({ label: t(`source.${k}`), value: v }));
  }, [ops, t]);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("source.title")}</CardTitle>
          <CardDescription>{t("source.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-24 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : !mix ? (
          <EmptyState kind="empty" title={t("source.empty")} description={t("source.emptyBody")} />
        ) : (
          <HorizontalBars data={mix} formatValue={(v) => nf.format(v)} ariaLabel={t("source.title")} />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Trend                                                                       */
/* -------------------------------------------------------------------------- */

function TrendCard({ monthly }: { monthly: AnalyticsMonthlyPoint[] }) {
  const t = useTranslations("analytics");
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("trendTitle")}</CardTitle>
          <CardDescription>{t("trendSubtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Activity className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {monthly.length === 0 ? (
          <p className="type-small text-muted-foreground">{t("trendEmpty")}</p>
        ) : (
          <>
            <AreaChart
              data={monthly.map((p) => ({ month: p.month, count: p.count }))}
              xKey="month"
              series={[{ key: "count", label: t("trendSeries"), color: "var(--viz-indigo)" }]}
              height={220}
              formatValue={(v) => nf.format(v)}
              ariaLabel={t("trendTitle")}
            />
            <table className="sr-only">
              <caption>{t("chartTableSr")}</caption>
              <thead>
                <tr>
                  <th>{t("table.month")}</th>
                  <th>{t("table.applications")}</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((p) => (
                  <tr key={p.month}>
                    <td>{p.month}</td>
                    <td>{p.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Top jobs                                                                     */
/* -------------------------------------------------------------------------- */

function TopJobsCard({ jobs }: { jobs: AnalyticsTopJob[] }) {
  const t = useTranslations("analytics");
  const cols: ColumnDef<AnalyticsTopJob, unknown>[] = [
    {
      accessorKey: "title",
      header: t("table.job"),
      cell: ({ row }) => (
        <Link
          href={`/partner/jobs/${row.original.job_id}/applications`}
          className="font-semibold text-foreground hover:text-[var(--brand-primary)]"
        >
          {row.original.title}
        </Link>
      ),
    },
    {
      accessorKey: "application_count",
      header: t("table.applications"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums">{nf.format(row.original.application_count)}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("topJobsTitle")}</CardTitle>
          <CardDescription>{t("topJobsSubtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={cols}
          data={jobs}
          getRowId={(r) => r.job_id}
          pageSize={8}
          empty={<EmptyState kind="empty" title={t("topJobsEmpty")} description={t("topJobsSubtitle")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* CSV export                                                                   */
/* -------------------------------------------------------------------------- */

function exportCsv(data: PartnerAnalytics | undefined, filename: string) {
  if (!data) return;
  const lines: string[] = [];
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  lines.push("section,label,value");
  for (const f of data.funnel) lines.push(["funnel", f.status, f.count].map(esc).join(","));
  for (const m of data.monthly_trend) lines.push(["monthly", m.month, m.count].map(esc).join(","));
  for (const j of data.top_jobs) lines.push(["top_job", j.title, j.application_count].map(esc).join(","));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                     */
/* -------------------------------------------------------------------------- */

function AnalyticsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
    </div>
  );
}
