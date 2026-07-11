"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Buildings,
  ChartBar,
  NotePencil,
  Hourglass,
  Users,
  UsersThree,
  ClockCounterClockwise,
  UserCircle,
  Sparkle,
  LightbulbFilament,
  ListChecks,
  ShieldCheck,
  Kanban,
  Receipt,
  GearSix,
  TrendUp,
  Target,
  CaretRight,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, StatusBadge } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatRelativeTime } from "@/lib/format";
import { JOB_STATUS_TONE, useJobLabels } from "@/lib/jobs/labels";
import {
  APPLICATION_STATUS_TONE,
  useApplicationLabels,
} from "@/lib/applications/labels";
import {
  dashboardsApi,
  type JobStatus,
  type PartnerDashboardMetrics,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  DashboardErrorState,
  DashboardGuestGate,
  DashboardSection,
  DashboardSkeleton,
  MetricTiles,
  QueueList,
  QUEUE_ROW_CLASS,
  SectionLink,
  type MetricItem,
} from "./dashboard-kit";

/* -------------------------------------------------------------------------- */
/* Pipeline Health mini widget (right rail)                                   */
/* -------------------------------------------------------------------------- */

function PipelineHealthMini({
  metrics,
  pipelineTitle,
  activeJobsLabel,
}: {
  metrics: PartnerDashboardMetrics;
  pipelineTitle: string;
  activeJobsLabel: string;
}) {
  const totalJobSlots =
    metrics.jobs_active + metrics.jobs_draft + metrics.jobs_pending_review;
  const activeRatioPct =
    totalJobSlots > 0
      ? Math.round((metrics.jobs_active / totalJobSlots) * 100)
      : 0;

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <ChartBar
            aria-hidden
            weight="duotone"
            className="size-4"
          />
        </span>
        {pipelineTitle}
      </h3>

      <ul className="space-y-3.5" role="list">
        {/* Active jobs bar */}
        <li>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-[var(--text-secondary)]">
              {activeJobsLabel}
            </span>
            <span className="font-mono text-xs font-bold tabular-nums text-[var(--text-primary)]">
              {metrics.jobs_active}
              <span className="font-normal text-[var(--text-muted)]">
                /{totalJobSlots}
              </span>
            </span>
          </div>
          <div
            role="meter"
            aria-valuenow={activeRatioPct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={activeJobsLabel}
            className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
          >
            <div
              className="h-full rounded-full bg-[var(--brand-primary)] transition-[width] duration-700 motion-reduce:transition-none"
              style={{ width: `${Math.max(activeRatioPct, 2)}%` }}
            />
          </div>
        </li>
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* AI hiring health — derived from existing dashboard metrics                 */
/* -------------------------------------------------------------------------- */

interface HiringInsightEntry {
  key: string;
  values?: Record<string, string | number>;
}

function deriveHiringInsights(m: PartnerDashboardMetrics): HiringInsightEntry[] {
  const insights: HiringInsightEntry[] = [];
  const totalJobs = m.jobs_active + m.jobs_draft + m.jobs_pending_review;

  if (m.jobs_active > 0 && m.applications_total > 0) {
    const appsPerJob = Math.round(m.applications_total / m.jobs_active);
    if (appsPerJob >= 10)
      insights.push({ key: "aiInsightStrongDemand", values: { count: appsPerJob } });
    else if (appsPerJob < 4 && m.jobs_active >= 2)
      insights.push({ key: "aiInsightLowVolume", values: { count: appsPerJob } });
  }

  if (m.jobs_draft > 0)
    insights.push({ key: "aiInsightDraftJobs", values: { count: m.jobs_draft } });

  if (totalJobs > 0 && m.jobs_active === 0)
    insights.push({ key: "aiInsightNoActive" });

  return insights.slice(0, 3);
}

interface PartnerTodo {
  key: string;
  title: string;
  body: string;
  href: string;
  count?: number | null;
  icon: Icon;
  hot?: boolean;
}

function derivePartnerTodos(
  metrics: PartnerDashboardMetrics,
  actions: { key: string; href: string; count: number | null }[],
  tp: ReturnType<typeof useTranslations>,
): PartnerTodo[] {
  const actionMap = new Map(actions.map((action) => [action.key, action]));
  const out: PartnerTodo[] = [];

  const pushAction = (key: string, icon: Icon, hot = false) => {
    const action = actionMap.get(key);
    if (!action) return;
    out.push({
      key,
      title: tp(`todo.${key}.title`),
      body: tp(`todo.${key}.body`, { count: action.count ?? 0 }),
      href: action.href,
      count: action.count,
      icon,
      hot,
    });
  };

  pushAction("jobs_pending_review", Hourglass, metrics.jobs_pending_review > 0);
  pushAction("jobs_in_draft", NotePencil, metrics.jobs_draft > 0);

  if (out.length < 4) {
    out.push({
      key: "review_pipeline",
      title: tp("todo.reviewPipeline.title"),
      body: tp("todo.reviewPipeline.body"),
      href: "/partner/pipeline",
      icon: Kanban,
    });
  }

  if (out.length < 4) {
    out.push({
      key: "invite_team",
      title: tp("todo.inviteTeam.title"),
      body: tp("todo.inviteTeam.body"),
      href: "/partner/team",
      icon: UsersThree,
    });
  }

  const postJob = actionMap.get("post_job");
  if (postJob && out.length < 5) {
    out.push({
      key: "post_job",
      title: tp("todo.post_job.title"),
      body: tp("todo.post_job.body"),
      href: postJob.href,
      icon: Briefcase,
    });
  }

  return out.slice(0, 5);
}

function TodoCommandCenter({ items }: { items: PartnerTodo[] }) {
  const tp = useTranslations("dashboard.partner");

  return (
    <DashboardSection
      icon={ListChecks}
      tone="primary"
      title={tp("todoTitle")}
      count={items.filter((item) => item.hot).length}
    >
      <QueueList>
        {items.map((item) => (
          <li key={item.key}>
            <Link href={item.href} className={cn(QUEUE_ROW_CLASS, "group py-3.5")}>
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-[10px]",
                  item.hot ? "icon-chip-warning" : "icon-chip-neutral",
                )}
              >
                <item.icon aria-hidden weight="duotone" className="size-4.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                  {item.title}
                </span>
                <span className="mt-0.5 block truncate text-xs text-[var(--text-secondary)]">
                  {item.body}
                </span>
              </span>
              {item.count != null && item.count > 0 && (
                <span className="inline-flex min-w-7 items-center justify-center rounded-full bg-[var(--amber-50)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--amber-700)]">
                  {item.count}
                </span>
              )}
              <CaretRight
                aria-hidden
                weight="bold"
                className="size-3.5 shrink-0 text-[var(--text-muted)] transition-colors group-hover:text-[var(--brand-primary)]"
              />
            </Link>
          </li>
        ))}
      </QueueList>
    </DashboardSection>
  );
}

function OperationsHealthCard({
  metrics,
  applicationsPerActiveJob,
}: {
  metrics: PartnerDashboardMetrics;
  applicationsPerActiveJob: number;
}) {
  const tp = useTranslations("dashboard.partner");
  const queueCount = metrics.jobs_draft + metrics.jobs_pending_review;
  const rows = [
    {
      key: "candidateDemand",
      label: tp("health.candidateDemand"),
      value: tp("health.applicationsPerJob", { count: applicationsPerActiveJob }),
      tone: applicationsPerActiveJob >= 4 ? "good" : "watch",
    },
    {
      key: "publishingQueue",
      label: tp("health.publishingQueue"),
      value: tp("health.itemsWaiting", { count: metrics.jobs_draft + metrics.jobs_pending_review }),
      tone: metrics.jobs_draft + metrics.jobs_pending_review === 0 ? "good" : "watch",
    },
  ];

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
            <span className="icon-chip-success flex size-7 shrink-0 items-center justify-center rounded-lg">
              <ShieldCheck aria-hidden weight="duotone" className="size-4" />
            </span>
            {tp("healthTitle")}
          </h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {queueCount === 0 ? tp("healthAllClear") : tp("healthNeedsWork", { count: queueCount })}
          </p>
        </div>
      </div>
      <ul className="space-y-3" role="list">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-[var(--text-secondary)]">
              {row.label}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-1 text-xs font-bold",
                row.tone === "good"
                  ? "bg-[var(--teal-100)] text-[var(--teal-700)]"
                  : "bg-[var(--amber-50)] text-[var(--amber-700)]",
              )}
            >
              {row.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PermissionGovernancePanel() {
  const tp = useTranslations("dashboard.partner");
  const controls: Array<{ key: string; href: string; icon: Icon }> = [
    { key: "team", href: "/partner/team", icon: UsersThree },
    { key: "billing", href: "/partner/billing", icon: Receipt },
    { key: "company", href: "/partner/company-profile", icon: Buildings },
    { key: "analytics", href: "/partner/analytics", icon: TrendUp },
    { key: "pipeline", href: "/partner/pipeline", icon: Kanban },
    { key: "security", href: "/partner/security", icon: ShieldCheck },
    { key: "settings", href: "/partner/settings", icon: GearSix },
  ];

  return (
    <DashboardSection
      icon={ShieldCheck}
      tone="neutral"
      title={tp("governanceTitle")}
    >
      <p className="-mt-1 mb-3 text-xs leading-5 text-[var(--text-secondary)]">
        {tp("governanceBody")}
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
        {controls.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className="group flex items-center gap-3 rounded-[12px] border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3 outline-none transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <span className="icon-chip-neutral flex size-8 shrink-0 items-center justify-center rounded-lg">
              <item.icon aria-hidden weight="duotone" className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                {tp(`governance.${item.key}.title`)}
              </span>
              <span className="mt-0.5 block truncate text-xs text-[var(--text-secondary)]">
                {tp(`governance.${item.key}.body`)}
              </span>
            </span>
            <CaretRight aria-hidden weight="bold" className="size-3.5 text-[var(--text-muted)]" />
          </Link>
        ))}
      </div>
    </DashboardSection>
  );
}

function JobPerformanceSnapshot({
  jobs,
  jobLabels,
}: {
  jobs: Array<{
    id: string;
    title: string;
    status: string;
    status_label: string;
    application_count: number;
  }>;
  jobLabels: ReturnType<typeof useJobLabels>;
}) {
  const tp = useTranslations("dashboard.partner");
  const maxApplications = Math.max(1, ...jobs.map((job) => job.application_count));

  return (
    <DashboardSection
      icon={Target}
      tone="info"
      title={tp("performanceTitle")}
      count={jobs.length}
      action={<SectionLink href="/partner/analytics">{tp("openAnalytics")}</SectionLink>}
    >
      {jobs.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={Briefcase}
          title={tp("noAttentionTitle")}
          description={tp("noAttentionBody")}
          action={
            <Link href="/partner/jobs/new">
              <Button variant="primary">{tp("postJob")}</Button>
            </Link>
          }
        />
      ) : (
        <QueueList>
          {jobs.map((job) => {
            const pct = Math.max(6, Math.round((job.application_count / maxApplications) * 100));
            return (
              <li key={job.id}>
                <Link href={`/partner/jobs/${job.id}`} className={cn(QUEUE_ROW_CLASS, "group items-start py-3")}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                        {job.title}
                      </h3>
                    </div>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="h-1.5 min-w-20 flex-1 overflow-hidden rounded-full bg-[var(--bg-muted)]">
                        <div
                          className="h-full rounded-full bg-[var(--brand-primary)] transition-[width] duration-700 motion-reduce:transition-none"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="shrink-0 text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                        {tp("applicationCount", { count: job.application_count })}
                      </span>
                    </div>
                  </div>
                  <StatusBadge
                    tone={JOB_STATUS_TONE[job.status as JobStatus] ?? "draft"}
                  >
                    {jobLabels.status(job.status, job.status_label)}
                  </StatusBadge>
                </Link>
              </li>
            );
          })}
        </QueueList>
      )}
      <p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">
        {tp("performanceFootnote")}
      </p>
    </DashboardSection>
  );
}

/* -------------------------------------------------------------------------- */
/* Partner Dashboard                                                          */
/* -------------------------------------------------------------------------- */

export function PartnerDashboard() {
  const tp = useTranslations("dashboard.partner");
  const tNav = useTranslations("nav");
  const locale = useLocale();
  const jobLabels = useJobLabels();
  const appLabels = useApplicationLabels();
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["dashboard", "partner"],
    queryFn: () => dashboardsApi.partner(),
    enabled: authed,
    retry: false,
  });

  return (
    <>
      <PageHeader
        title={tNav("dashboard")}
        actions={
          authed && !query.isError ? (
            <>
              <Link href="/partner/ops">
                <Button variant="secondary">{tNav("ops")}</Button>
              </Link>
              <Link href="/partner/jobs/new">
                <Button variant="primary">{tp("postJob")}</Button>
              </Link>
            </>
          ) : undefined
        }
      />

      {!authed ? (
        <DashboardGuestGate persona="partner" />
      ) : query.isPending ? (
        <DashboardSkeleton tileCount={4} tileCols={4} />
      ) : query.isError ? (
        <DashboardErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        (() => {
          const data = query.data;
          const metrics: MetricItem[] = [
            {
              key: "jobs_active",
              label: tp("metric.jobsActive"),
              value: data.metrics.jobs_active,
              icon: Briefcase,
              href: "/partner/jobs",
            },
            {
              key: "jobs_draft",
              label: tp("metric.jobsDraft"),
              value: data.metrics.jobs_draft,
              icon: NotePencil,
              tone: "neutral",
              href: "/partner/jobs",
            },
            {
              key: "jobs_pending_review",
              label: tp("metric.jobsPendingReview"),
              value: data.metrics.jobs_pending_review,
              icon: Hourglass,
              emphasize: true,
              href: "/partner/jobs",
              hotNote: tp("metric.jobsPendingReviewHotNote", {
                count: data.metrics.jobs_pending_review,
              }),
            },
            {
              key: "applications_total",
              label: tp("metric.applicationsTotal"),
              value: data.metrics.applications_total,
              icon: Users,
              tone: "info",
              href: "/partner/candidates",
            },
          ];

          const hiringInsights = deriveHiringInsights(data.metrics);
          const todos = derivePartnerTodos(data.metrics, data.next_actions, tp);
          const applicationsPerActiveJob =
            data.metrics.jobs_active > 0
              ? Math.round(data.metrics.applications_total / data.metrics.jobs_active)
              : 0;

          return (
            <div className="space-y-6">
              <MetricTiles items={metrics} cols={4} />

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="space-y-6 lg:col-span-2">
                  <TodoCommandCenter items={todos} />

                  {hiringInsights.length > 0 && (
                    <div className="marketplace-card rounded-[12px] border-l-[3px] border-l-[var(--brand-teal)] p-5">
                      <div className="mb-3 flex items-center gap-2">
                        <span className="icon-chip-success flex size-8 shrink-0 items-center justify-center rounded-[10px]">
                          <Sparkle aria-hidden weight="fill" className="size-4" />
                        </span>
                        <span className="text-sm font-bold text-[var(--text-primary)]">
                          {tp("aiHiringHealthTitle")}
                        </span>
                      </div>
                      <ul className="space-y-2">
                        {hiringInsights.map((insight, i) => (
                          <li key={i} className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]">
                            <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                            {tp(insight.key, insight.values)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <JobPerformanceSnapshot
                    jobs={data.jobs_attention}
                    jobLabels={jobLabels}
                  />
                </div>

                <div className="space-y-6">
                  <OperationsHealthCard
                    metrics={data.metrics}
                    applicationsPerActiveJob={applicationsPerActiveJob}
                  />

                  <PermissionGovernancePanel />

                  <DashboardSection
                    icon={ClockCounterClockwise}
                    tone="neutral"
                    title={tp("recentApplicationsTitle")}
                    action={
                      <SectionLink href="/partner/candidates">
                        {tp("viewCandidates")}
                      </SectionLink>
                    }
                  >
                    {data.applications_recent.length === 0 ? (
                      <EmptyState
                        kind="empty"
                        icon={Users}
                        title={tp("noApplicationsTitle")}
                        description={tp("noApplicationsBody")}
                      />
                    ) : (
                      <ul
                        className="divide-y divide-[var(--border-default)] overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)]"
                        role="list"
                      >
                        {data.applications_recent.map((app) => (
                          <li
                            key={app.id}
                            className="flex items-center gap-2.5 px-3.5 py-2.5"
                          >
                            {/* Avatar */}
                            <span className="icon-chip-primary flex size-8 shrink-0 items-center justify-center rounded-full shadow-sm">
                              <UserCircle
                                aria-hidden
                                weight="duotone"
                                className="size-5"
                              />
                            </span>

                            {/* Title + handle + time */}
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs font-semibold text-[var(--text-primary)]">
                                {app.job_title ?? tp("untitledJob")}
                              </p>
                              <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                                {app.candidate_name}
                                {" · "}
                                {formatRelativeTime(app.submitted_at, locale)}
                              </p>
                            </div>

                            <StatusBadge
                              tone={
                                APPLICATION_STATUS_TONE[app.status] ?? "info"
                              }
                            >
                              {appLabels.status(app.status, app.status_label)}
                            </StatusBadge>
                          </li>
                        ))}
                      </ul>
                    )}
                  </DashboardSection>

                  <PipelineHealthMini
                    metrics={data.metrics}
                    pipelineTitle={tp("pipelineHealthTitle")}
                    activeJobsLabel={tp("metric.jobsActive")}
                  />
                </div>
              </div>
            </div>
          );
        })()
      )}
    </>
  );
}
