"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Briefcase,
  Kanban,
  Layers,
  Lightbulb,
  LogIn,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  DonutChart,
  EmptyState,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, dashboardsApi, type PipelineJobRow } from "@/lib/api";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatDateTime } from "@/lib/format";

const nf = new Intl.NumberFormat();

const JOB_STATUS_CHIP: Record<string, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  rejected: "danger",
  closed: "neutral",
  expired: "neutral",
};

export function GlobalPipelineScreen() {
  const t = useTranslations("globalPipeline");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const labels = useJobLabels();

  const query = useQuery({
    queryKey: ["dashboards", "partner", "pipeline-overview"],
    queryFn: () => dashboardsApi.partnerPipelineOverview(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  });

  const header = <PageHeader title={t("title")} description={t("subtitle")} />;

  /* ---- error states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldAlert : LogIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <EmptyState
          kind={err.code === "NETWORK_ERROR" ? "offline" : "error"}
          icon={AlertCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const data = query.data;
  const jobs = data?.jobs ?? [];
  const totalActive = data?.total_active ?? 0;
  const isPending = query.isPending;

  const agg = React.useMemo(() => {
    let active = 0;
    let rejected = 0;
    let withdrawn = 0;
    for (const j of jobs) {
      active += j.active_total;
      rejected += j.rejected;
      withdrawn += j.withdrawn;
    }
    return { active, rejected, withdrawn, total: active + rejected + withdrawn };
  }, [jobs]);

  const insights = React.useMemo(() => derivePipelineInsights(jobs, totalActive, t), [jobs, totalActive, t]);

  const columns: ColumnDef<PipelineJobRow, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colJob"),
      cell: ({ row }) => {
        const j = row.original;
        return (
          <div className="min-w-0">
            <Link
              href={`/partner/jobs/${j.job_id}/pipeline`}
              className="block truncate font-semibold text-foreground hover:text-[var(--brand-primary)]"
            >
              {j.title || t("untitled")}
            </Link>
            <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
              <StatusChip tone={JOB_STATUS_CHIP[j.status] ?? "neutral"} size="sm">
                {labels.status(j.status)}
              </StatusChip>
              {j.deadline && (
                <span className="type-caption text-muted-foreground">
                  {t("deadline", { date: formatDateTime(j.deadline, locale) })}
                </span>
              )}
            </span>
          </div>
        );
      },
    },
    {
      id: "distribution",
      header: t("colDistribution"),
      enableSorting: false,
      cell: ({ row }) => <DistributionBar job={row.original} emptyLabel={t("noApplications")} />,
    },
    {
      accessorKey: "active_total",
      header: t("activeCount"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums text-foreground">{nf.format(row.original.active_total)}</span>,
    },
    {
      accessorKey: "rejected",
      header: t("rejectedCount"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums text-muted-foreground">{nf.format(row.original.rejected)}</span>,
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1">
          <Link href={`/partner/jobs/${row.original.job_id}/pipeline`}>
            <Button variant="ghost" size="sm">
              <Kanban className="size-4" strokeWidth={1.8} />
              {t("viewBoard")}
            </Button>
          </Link>
          <Link href={`/partner/jobs/${row.original.job_id}/applications`}>
            <Button variant="ghost" size="sm">
              <ArrowRight className="size-4" strokeWidth={1.8} />
              {t("viewList")}
            </Button>
          </Link>
        </div>
      ),
    },
  ];

  return (
    <>
      {header}

      <div className="space-y-4">
        {/* KPI row */}
        <KpiRow cols={4}>
          <KpiTile label={t("totalActive")} value={isPending ? "—" : nf.format(totalActive)} icon={Layers} />
          <KpiTile label={t("totalJobs")} value={isPending ? "—" : nf.format(jobs.length)} icon={Briefcase} />
          <KpiTile label={t("aggRejected")} value={isPending ? "—" : nf.format(agg.rejected)} />
          <KpiTile label={t("aggWithdrawn")} value={isPending ? "—" : nf.format(agg.withdrawn)} />
        </KpiRow>

        {isPending ? (
          <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ) : jobs.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={Briefcase}
            title={t("emptyTitle")}
            description={t("emptyBody")}
            action={
              <Link href="/partner/jobs">
                <Button variant="primary">{t("goToJobs")}</Button>
              </Link>
            }
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            {/* Aggregate rollup donut */}
            <Card>
              <CardHeader>
                <CardTitle>{t("rollupTitle")}</CardTitle>
                <CardToolbar>
                  <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
                </CardToolbar>
              </CardHeader>
              <CardContent>
                {agg.total === 0 ? (
                  <EmptyState kind="empty" title={t("rollupEmptyTitle")} description={t("rollupEmptyBody")} />
                ) : (
                  <>
                    <DonutChart
                      data={[
                        { label: t("activeCount"), value: agg.active, color: "var(--viz-indigo)" },
                        { label: t("rejectedCount"), value: agg.rejected, color: "var(--viz-rose)" },
                        { label: t("withdrawnCount"), value: agg.withdrawn, color: "var(--border-strong)" },
                      ]}
                      centerValue={nf.format(agg.active)}
                      centerLabel={t("activeCount")}
                      formatValue={(v) => nf.format(v)}
                    />
                    <ul className="mt-3 space-y-1.5">
                      {[
                        { label: t("activeCount"), value: agg.active, tone: "indigo" as ChipTone },
                        { label: t("rejectedCount"), value: agg.rejected, tone: "rose" as ChipTone },
                        { label: t("withdrawnCount"), value: agg.withdrawn, tone: "neutral" as ChipTone },
                      ].map((r) => (
                        <li key={r.label} className="flex items-center justify-between text-[0.8125rem]">
                          <StatusChip tone={r.tone} dot size="sm">{r.label}</StatusChip>
                          <span className="font-semibold tabular-nums text-foreground">{nf.format(r.value)}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Per-job funnel rollup table */}
            <div className="lg:col-span-2 space-y-4">
              {insights.length > 0 && (
                <Card className="border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <span
                        className="flex size-7 items-center justify-center rounded-lg"
                        style={{ background: "var(--content-ai-soft)" }}
                      >
                        <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
                      </span>
                      <CardTitle>{t("aiPipelineTitle")}</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {insights.map((text, i) => (
                        <li key={i} className="flex items-start gap-2 text-[0.8125rem] text-foreground">
                          <Lightbulb
                            aria-hidden
                            className="mt-0.5 size-3.5 shrink-0"
                            strokeWidth={1.9}
                            style={{ color: "var(--content-ai)" }}
                          />
                          {text}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              <DataTable
                columns={columns}
                data={jobs}
                getRowId={(r) => r.job_id}
                pageSize={10}
                empty={<EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />}
              />
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */

function DistributionBar({ job, emptyLabel }: { job: PipelineJobRow; emptyLabel: string }) {
  const total = job.active_total + job.rejected + job.withdrawn;
  if (total === 0) {
    return <span className="type-caption text-muted-foreground">{emptyLabel}</span>;
  }
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="min-w-[9rem]">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]">
        <span className="h-full" style={{ width: pct(job.active_total), background: "var(--viz-indigo)" }} />
        <span className="h-full" style={{ width: pct(job.rejected), background: "var(--viz-rose)" }} />
        <span className="h-full" style={{ width: pct(job.withdrawn), background: "var(--border-strong)" }} />
      </div>
    </div>
  );
}

function derivePipelineInsights(
  jobs: PipelineJobRow[],
  totalActive: number,
  t: ReturnType<typeof useTranslations>,
): string[] {
  if (jobs.length === 0) return [];
  const out: string[] = [];
  const emptyJobs = jobs.filter((j) => j.total === 0).length;
  const highRejection = jobs.some((j) => j.total > 3 && j.rejected / j.total > 0.4);
  const soon = jobs.some((j) => {
    if (!j.deadline) return false;
    const diff = new Date(j.deadline).getTime() - Date.now();
    return diff > 0 && diff < 2 * 24 * 60 * 60 * 1000;
  });
  if (totalActive > 0) out.push(t("insightActivePipeline", { count: totalActive }));
  if (emptyJobs > 0 && emptyJobs === jobs.length) out.push(t("insightAllEmpty"));
  else if (emptyJobs > 0) out.push(t("insightNoApplicants", { count: emptyJobs }));
  if (highRejection) out.push(t("insightHighRejection"));
  if (soon) out.push(t("insightDeadlineSoon"));
  return out.slice(0, 3);
}
