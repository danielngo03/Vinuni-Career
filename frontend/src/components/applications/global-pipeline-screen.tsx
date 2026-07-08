"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Briefcase,
  CheckCircle,
  Kanban,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  Users,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton, StatusBadge } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, dashboardsApi, type PipelineJobRow } from "@/lib/api";
import { JOB_STATUS_TONE, useJobLabels } from "@/lib/jobs/labels";
import { formatDateTime } from "@/lib/format";

type PipelineInsightKey =
  | "insightActivePipeline"
  | "insightNoApplicants"
  | "insightHighRejection"
  | "insightDeadlineSoon"
  | "insightAllEmpty";

function derivePipelineInsights(jobs: PipelineJobRow[], totalActive: number): PipelineInsightKey[] {
  const out: PipelineInsightKey[] = [];
  if (jobs.length === 0) return out;
  const emptyJobs = jobs.filter((j) => j.total === 0).length;
  const highRejection = jobs.some((j) => j.total > 3 && j.rejected / j.total > 0.4);
  const soon = jobs.some((j) => {
    if (!j.deadline) return false;
    const diff = new Date(j.deadline).getTime() - Date.now();
    return diff > 0 && diff < 2 * 24 * 60 * 60 * 1000;
  });
  if (totalActive > 0) out.push("insightActivePipeline");
  if (emptyJobs > 0 && emptyJobs === jobs.length) out.push("insightAllEmpty");
  else if (emptyJobs > 0) out.push("insightNoApplicants");
  if (highRejection) out.push("insightHighRejection");
  if (soon) out.push("insightDeadlineSoon");
  return out.slice(0, 3);
}

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

  /* ── Error states ── */
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
              err.isPermissionError
                ? tStates("permissionBody")
                : tStates("authBody")
            }
          />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
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

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* ── Summary strip ── */}
      <div className="flex flex-wrap gap-3">
        <SummaryStat
          label={t("totalActive")}
          value={isPending ? null : totalActive}
          tone="active"
        />
        <SummaryStat
          label={t("totalJobs")}
          value={isPending ? null : jobs.length}
          tone="neutral"
        />
      </div>

      {/* ── AI Pipeline Health ── */}
      {!isPending && jobs.length > 0 && (() => {
        const insights = derivePipelineInsights(jobs, totalActive);
        if (!insights.length) return null;
        return (
          <section
            aria-label={t("aiPipelineTitle")}
            className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("aiPipelineTitle")}
              </p>
            </div>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* ── Job rows ── */}
      {isPending ? (
        <PipelineSkeleton />
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
        <ul className="flex flex-col gap-3">
          {jobs.map((job) => (
            <JobPipelineRow
              key={job.job_id}
              job={job}
              locale={locale}
              labels={labels}
              t={t}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/* ─── Summary stat chip ──────────────────────────────────────────────────── */

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone: "active" | "neutral";
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 ${
        tone === "active"
          ? "border-[var(--brand-primary)]/30 bg-[var(--blue-50)]/70"
          : "border-[var(--border-default)] bg-[var(--surface-card)]"
      }`}
    >
      <span className="text-xs font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      <span
        className={`text-xl font-black tabular-nums ${
          tone === "active"
            ? "text-[var(--brand-primary)]"
            : "text-[var(--text-primary)]"
        }`}
      >
        {value === null ? "—" : value}
      </span>
    </div>
  );
}

/* ─── Per-job row ────────────────────────────────────────────────────────── */

function JobPipelineRow({
  job,
  locale,
  labels,
  t,
}: {
  job: PipelineJobRow;
  locale: string;
  labels: ReturnType<typeof useJobLabels>;
  t: ReturnType<typeof useTranslations>;
}) {
  const total = job.active_total + job.rejected + job.withdrawn;
  const activeW = total > 0 ? (job.active_total / total) * 100 : 0;
  const rejectedW = total > 0 ? (job.rejected / total) * 100 : 0;
  const withdrawnW = total > 0 ? (job.withdrawn / total) * 100 : 0;

  return (
    <li className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_2px_12px_rgba(11,34,57,0.06)]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        {/* Left: job info */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={JOB_STATUS_TONE[job.status as keyof typeof JOB_STATUS_TONE] ?? "info"}>
              {labels.status(job.status)}
            </StatusBadge>
            {job.deadline && (
              <span className="text-xs text-[var(--text-muted)]">
                {t("deadline", { date: formatDateTime(job.deadline, locale) })}
              </span>
            )}
          </div>
          <h3 className="mt-1 truncate text-base font-bold text-[var(--text-primary)]">
            {job.title || t("untitled")}
          </h3>

          {/* ── Mini funnel bar ── */}
          {total > 0 ? (
            <div className="mt-3">
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--bg-subtle)]">
                <span
                  className="h-full bg-[var(--brand-primary)] transition-all"
                  style={{ width: `${activeW}%` }}
                />
                <span
                  className="h-full bg-[var(--red-400)] transition-all"
                  style={{ width: `${rejectedW}%` }}
                />
                <span
                  className="h-full bg-[var(--bg-muted)] transition-all"
                  style={{ width: `${withdrawnW}%` }}
                />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]">
                <CountChip
                  icon={<Users aria-hidden weight="duotone" className="size-3" />}
                  count={job.active_total}
                  label={t("activeCount")}
                  color="text-[var(--brand-primary)]"
                />
                <CountChip
                  icon={<XCircle aria-hidden weight="duotone" className="size-3 text-[var(--red-400)]" />}
                  count={job.rejected}
                  label={t("rejectedCount")}
                  color="text-[var(--text-secondary)]"
                />
                <CountChip
                  icon={<CheckCircle aria-hidden weight="duotone" className="size-3 text-[var(--text-muted)]" />}
                  count={job.withdrawn}
                  label={t("withdrawnCount")}
                  color="text-[var(--text-muted)]"
                />
              </div>
            </div>
          ) : (
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              {t("noApplications")}
            </p>
          )}
        </div>

        {/* Right: action buttons */}
        <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-end">
          <Link href={`/partner/jobs/${job.job_id}/pipeline`}>
            <Button variant="primary" size="sm">
              <Kanban aria-hidden weight="duotone" className="size-4" />
              {t("viewBoard")}
            </Button>
          </Link>
          <Link href={`/partner/jobs/${job.job_id}/applications`}>
            <Button variant="ghost" size="sm">
              <ArrowRight aria-hidden weight="bold" className="size-4" />
              {t("viewList")}
            </Button>
          </Link>
        </div>
      </div>
    </li>
  );
}

function CountChip({
  icon,
  count,
  label,
  color,
}: {
  icon: React.ReactNode;
  count: number;
  label: string;
  color: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1 ${color}`}>
      {icon}
      <span className="font-semibold tabular-nums">{count}</span>
      <span className="text-[var(--text-muted)]">{label}</span>
    </span>
  );
}

/* ─── Skeleton ───────────────────────────────────────────────────────────── */

function PipelineSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 "
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="mt-2 h-5 w-2/3" />
              <Skeleton className="mt-3 h-2 w-full rounded-full" />
              <div className="mt-2 flex gap-3">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-20" />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Skeleton className="h-8 w-24 rounded-lg" />
              <Skeleton className="h-8 w-24 rounded-lg" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
