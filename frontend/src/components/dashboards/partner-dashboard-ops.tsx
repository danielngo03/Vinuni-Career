"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Pulse,
  Briefcase,
  CaretRight,
  ChartLineUp,
  ClockCounterClockwise,
  Hourglass,
  Lightning,
  ListChecks,
  Lock,
  NotePencil,
  ShieldCheck,
  ShieldWarning,
  Sparkle,
  Target,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, DataTable, EmptyState } from "@/components/ui";
import type { Column } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatRelativeTime } from "@/lib/format";
import {
  dashboardsApi,
  type PartnerJobPerformanceRow,
  type PartnerOpsTodo,
  type PartnerTopJobRow,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  DashboardErrorState,
  DashboardGuestGate,
  DashboardSection,
  DashboardSkeleton,
  QueueList,
  QUEUE_ROW_CLASS,
  SectionLink,
} from "./dashboard-kit";

const TODO_ICONS: Record<string, Icon> = {
  jobs_pending_review: Hourglass,
  jobs_in_draft: NotePencil,
  review_access_alerts: ShieldWarning,
  post_job: Briefcase,
};

const PRIORITY_DOT: Record<PartnerOpsTodo["priority"], string> = {
  high: "bg-[var(--brand-red)]",
  medium: "bg-[var(--amber-500)]",
  low: "bg-[var(--border-strong)]",
};

/* -------------------------------------------------------------------------- */
/* Todos                                                                      */
/* -------------------------------------------------------------------------- */

function TodoList({ items }: { items: PartnerOpsTodo[] }) {
  const tp = useTranslations("dashboard.partnerOps");

  return (
    <DashboardSection icon={ListChecks} tone="primary" title={tp("todoTitle")} count={items.length}>
      {items.length === 0 ? (
        <EmptyState kind="empty" icon={ListChecks} title={tp("todoEmptyTitle")} description={tp("todoEmptyBody")} />
      ) : (
        <QueueList>
          {items.map((item) => {
            const ItemIcon = TODO_ICONS[item.key] ?? ListChecks;
            return (
              <li key={item.key}>
                <Link href={item.href} className={cn(QUEUE_ROW_CLASS, "group py-3")}>
                  <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", PRIORITY_DOT[item.priority])} />
                  <ItemIcon aria-hidden weight="duotone" className="size-[18px] shrink-0 text-[var(--text-muted)]" />
                  <span className="min-w-0 flex-1 text-[0.8125rem] font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                    {tp.has(`todoLabel.${item.key}`) ? tp(`todoLabel.${item.key}`) : item.key}
                  </span>
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {tp(`priority.${item.priority}`)}
                  </span>
                  {item.count != null && item.count > 0 && (
                    <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-[var(--amber-50)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--amber-700)]">
                      {item.count}
                    </span>
                  )}
                  <CaretRight aria-hidden weight="bold" className="size-3.5 shrink-0 text-[var(--text-muted)] transition-colors group-hover:text-[var(--brand-primary)]" />
                </Link>
              </li>
            );
          })}
        </QueueList>
      )}
    </DashboardSection>
  );
}

/* -------------------------------------------------------------------------- */
/* Engagement metrics (honest degradation)                                    */
/* -------------------------------------------------------------------------- */

function EngagementCard({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const engagement = data.metrics.engagement;

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-info flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <ChartLineUp aria-hidden weight="duotone" className="size-4" />
        </span>
        {tp("engagement.title")}
      </h3>

      {engagement.available ? (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {(
            [
              ["impressions", engagement.impressions],
              ["detailViews", engagement.detail_views],
              ["ctaClicks", engagement.cta_clicks],
              ["applyStarts", engagement.apply_starts],
              ["applicationsSubmitted", engagement.applications_submitted],
              [
                "conversion",
                engagement.conversion_rate_pct != null ? `${engagement.conversion_rate_pct}%` : tp("engagement.conversionUnavailable"),
              ],
            ] as const
          ).map(([key, value]) => (
            <div key={key} className="rounded-[10px] border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-2.5">
              <dt className="text-[11px] font-medium text-[var(--text-muted)]">{tp(`engagement.${key}`)}</dt>
              <dd className="mt-0.5 font-mono text-lg font-bold tabular-nums text-[var(--text-primary)]">{value}</dd>
            </div>
          ))}
        </dl>
      ) : engagement.basis === "locked" ? (
        <EmptyState kind="permission" icon={Lock} title={tp("engagement.lockedTitle")} description={tp("engagement.lockedBody")} />
      ) : (
        <EmptyState kind="empty" icon={ChartLineUp} title={tp("engagement.noDataTitle")} description={tp("engagement.noDataBody")} />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Job performance table                                                     */
/* -------------------------------------------------------------------------- */

function JobPerformanceSection({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const widget = data.job_performance;

  if (widget.locked) {
    return (
      <DashboardSection icon={Target} tone="info" title={tp("jobPerformanceTitle")}>
        <EmptyState kind="permission" icon={Lock} title={tp("jobPerformanceLockedTitle")} description={tp("jobPerformanceLockedBody")} />
      </DashboardSection>
    );
  }

  if (widget.basis === "job_metrics_daily") {
    const columns: Column<PartnerJobPerformanceRow>[] = [
      { key: "title", header: tp("table.job"), cell: (r) => (
        <Link href={`/partner/jobs/${r.job_id}`} className="font-semibold text-[var(--text-primary)] hover:text-[var(--brand-primary)]">
          {r.title}
        </Link>
      ) },
      { key: "impressions", header: tp("table.impressions"), align: "right", cell: (r) => r.impressions },
      { key: "detail_views", header: tp("table.views"), align: "right", cell: (r) => r.detail_views },
      { key: "cta_clicks", header: tp("table.clicks"), align: "right", cell: (r) => r.cta_clicks },
      { key: "applications_submitted", header: tp("table.applications"), align: "right", cell: (r) => r.applications_submitted },
      {
        key: "conversion_rate_pct",
        header: tp("table.conversion"),
        align: "right",
        cell: (r) => (r.conversion_rate_pct != null ? `${r.conversion_rate_pct}%` : "—"),
      },
    ];
    return (
      <DashboardSection icon={Target} tone="info" title={tp("jobPerformanceTitle")} count={widget.items.length}>
        <DataTable
          columns={columns}
          rows={widget.items}
          getRowId={(r) => r.job_id}
          empty={{ kind: "empty", icon: Briefcase, title: tp("jobPerformanceEmptyTitle"), description: tp("jobPerformanceEmptyBody") }}
        />
      </DashboardSection>
    );
  }

  const columns: Column<PartnerTopJobRow>[] = [
    { key: "title", header: tp("table.job"), cell: (r) => (
      <Link href={`/partner/jobs/${r.job_id}`} className="font-semibold text-[var(--text-primary)] hover:text-[var(--brand-primary)]">
        {r.title}
      </Link>
    ) },
    { key: "application_count", header: tp("table.applicationCount"), align: "right", cell: (r) => r.application_count },
  ];
  return (
    <DashboardSection icon={Target} tone="info" title={tp("jobPerformanceTitle")} count={widget.items.length}>
      <DataTable
        columns={columns}
        rows={widget.items}
        getRowId={(r) => r.job_id}
        empty={{ kind: "empty", icon: Briefcase, title: tp("jobPerformanceEmptyTitle"), description: tp("jobPerformanceEmptyBody") }}
      />
      <p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">{tp("jobPerformanceFallbackNote")}</p>
    </DashboardSection>
  );
}

/* -------------------------------------------------------------------------- */
/* Team activity                                                             */
/* -------------------------------------------------------------------------- */

function TeamActivitySection({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const locale = useLocale();

  return (
    <DashboardSection icon={ClockCounterClockwise} tone="neutral" title={tp("teamActivityTitle")}>
      {data.team_activity.length === 0 ? (
        <EmptyState kind="empty" icon={Pulse} title={tp("teamActivityEmptyTitle")} description={tp("teamActivityEmptyBody")} />
      ) : (
        <QueueList>
          {data.team_activity.map((item, i) => (
            <li key={`${item.action}-${item.occurred_at}-${i}`} className={cn(QUEUE_ROW_CLASS, "cursor-default")}>
              <Pulse aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.8125rem] font-semibold text-[var(--text-primary)]">{item.action_label}</span>
                <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">
                  {item.actor_name ?? "—"} · {formatRelativeTime(item.occurred_at, locale)}
                </span>
              </span>
            </li>
          ))}
        </QueueList>
      )}
    </DashboardSection>
  );
}

/* -------------------------------------------------------------------------- */
/* Access alerts                                                             */
/* -------------------------------------------------------------------------- */

function AccessAlertsSection({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const widget = data.access_alerts;

  return (
    <DashboardSection
      icon={ShieldWarning}
      tone={widget.locked || widget.items.length === 0 ? "neutral" : "warning"}
      title={tp("accessAlertsTitle")}
      action={<SectionLink href="/partner/security">{tp("viewAccessLog")}</SectionLink>}
    >
      {widget.locked ? (
        <EmptyState kind="permission" icon={Lock} title={tp("accessAlertsLockedTitle")} description={tp("accessAlertsLockedBody")} />
      ) : widget.items.length === 0 ? (
        <EmptyState kind="empty" icon={ShieldCheck} title={tp("accessAlertsEmptyTitle")} description={tp("accessAlertsEmptyBody")} />
      ) : (
        <ul className="space-y-2" role="list">
          {widget.items.map((alert, i) => (
            <li key={`${alert.code}-${i}`} className="flex items-center gap-3 rounded-[10px] border border-[var(--amber-400)]/50 bg-[var(--amber-50)] px-3.5 py-2.5">
              <ShieldWarning aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--amber-700)]" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.8125rem] font-semibold text-[var(--amber-700)]">{alert.label}</span>
                <span className="mt-0.5 block truncate text-[11px] text-[var(--amber-700)]/80">
                  {alert.actor_name ?? "—"} · {tp("alertWindow", { count: alert.count, hours: alert.window_hours })}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </DashboardSection>
  );
}

/* -------------------------------------------------------------------------- */
/* RBAC summary + AI recommendations                                         */
/* -------------------------------------------------------------------------- */

function RbacSummaryCard({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const rbac = data.rbac_summary;

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-neutral flex size-7 shrink-0 items-center justify-center rounded-lg">
          <ShieldCheck aria-hidden weight="duotone" className="size-4" />
        </span>
        {tp("rbacTitle")}
      </h3>
      <p className="text-xs leading-5 text-[var(--text-secondary)]">
        {rbac.is_org_admin ? tp("rbacAdminBody") : tp("rbacMemberBody")}
      </p>
      {!rbac.is_org_admin && rbac.hidden_widgets.length > 0 && (
        <p className="mt-2 text-[11px] font-semibold text-[var(--amber-700)]">
          {tp("hiddenWidgetsCount", { count: rbac.hidden_widgets.length })}
        </p>
      )}
    </div>
  );
}

function AiRecommendationsCard({ data }: { data: import("@/lib/api").PartnerDashboardOps }) {
  const tp = useTranslations("dashboard.partnerOps");
  const locale = useLocale();
  if (data.ai_recommendations.length === 0) return null;

  return (
    <div className="marketplace-card rounded-[12px] border-l-[3px] border-l-[var(--brand-teal)] p-5">
      <div className="mb-1 flex items-center gap-2">
        <span className="icon-chip-success flex size-8 shrink-0 items-center justify-center rounded-[10px]">
          <Sparkle aria-hidden weight="fill" className="size-4" />
        </span>
        <span className="text-sm font-bold text-[var(--text-primary)]">{tp("aiRecommendationsTitle")}</span>
      </div>
      <p className="mb-2 text-[11px] text-[var(--text-muted)]">{tp("aiRecommendationsDisclaimer")}</p>
      <ul className="space-y-2">
        {data.ai_recommendations.map((rec) => (
          <li key={rec.code} className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]">
            <Lightning aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
            {locale === "vi" ? rec.message_vi : rec.message_en}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                     */
/* -------------------------------------------------------------------------- */

export function PartnerDashboardOps() {
  const tp = useTranslations("dashboard.partnerOps");
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["dashboard", "partner", "ops"],
    queryFn: () => dashboardsApi.partnerOps(),
    enabled: authed,
    retry: false,
  });

  return (
    <>
      <PageHeader
        title={tp("title")}
        actions={
          <Link href="/partner/dashboard">
            <Button variant="secondary">{tp("backToOverview")}</Button>
          </Link>
        }
      />
      <p className="-mt-4 mb-6 max-w-2xl text-sm text-[var(--text-secondary)]">{tp("subtitle")}</p>

      {!authed ? (
        <DashboardGuestGate persona="partner" />
      ) : query.isPending ? (
        <DashboardSkeleton tileCount={5} tileCols={5} />
      ) : query.isError ? (
        <DashboardErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        (() => {
          const data = query.data;
          return (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="space-y-6 lg:col-span-2">
                <TodoList items={data.todos} />
                <JobPerformanceSection data={data} />
                <TeamActivitySection data={data} />
              </div>
              <div className="space-y-6">
                <EngagementCard data={data} />
                <AccessAlertsSection data={data} />
                <AiRecommendationsCard data={data} />
                <RbacSummaryCard data={data} />
              </div>
            </div>
          );
        })()
      )}
    </>
  );
}
