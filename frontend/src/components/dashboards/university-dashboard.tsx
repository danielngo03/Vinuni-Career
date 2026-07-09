"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  Clock,
  Gavel,
  Handshake,
  Buildings,
  Briefcase,
  ClipboardText,
  LightbulbFilament,
  PresentationChart,
  ShieldCheck,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { EmptyState } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatDateTime } from "@/lib/format";
import { dashboardsApi, type UniversityDashboardMetrics } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  DashboardErrorState,
  DashboardGuestGate,
  DashboardSection,
  DashboardSkeleton,
  MetricTiles,
  NextActionsRail,
  QueueList,
  QUEUE_ROW_CLASS,
  SectionLink,
  type MetricItem,
} from "./dashboard-kit";
import { UniversityOpsWorklist } from "./university-ops-worklist";

/* -------------------------------------------------------------------------- */
/* Activity Summary + SLA widget (right rail)                                */
/* -------------------------------------------------------------------------- */

function ActivitySummaryStrip({
  metrics,
  activityTitle,
  onTrackLabel,
  buildingLabel,
  overloadedLabel,
  partnersActiveLabel,
  jobsActiveTotalLabel,
}: {
  metrics: UniversityDashboardMetrics;
  activityTitle: string;
  onTrackLabel: string;
  buildingLabel: string;
  overloadedLabel: string;
  partnersActiveLabel: string;
  jobsActiveTotalLabel: string;
}) {
  const tu = useTranslations("dashboard.university");
  const pending = metrics.jobs_pending_moderation;

  // SLA colour: green 0-2, amber 3-8, red 9+
  const slaStatus: "on_track" | "building" | "overloaded" =
    pending <= 2 ? "on_track" : pending <= 8 ? "building" : "overloaded";

  const slaIcon =
    slaStatus === "on_track" ? CheckCircle : slaStatus === "building" ? Clock : Warning;
  const SlaIcon = slaIcon;

  const slaLabel =
    slaStatus === "on_track"
      ? onTrackLabel
      : slaStatus === "building"
      ? buildingLabel
      : overloadedLabel;

  const slaColors = {
    on_track: {
      badge: "border-[var(--teal-100)] bg-[var(--teal-100)] text-[var(--teal-700)]",
      bar: "bg-[var(--teal-600)]",
    },
    building: {
      badge: "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]",
      bar: "bg-[var(--amber-600)]",
    },
    overloaded: {
      badge: "border-[var(--red-100)] bg-[var(--red-50)] text-[var(--red-600)]",
      bar: "bg-[var(--brand-red)]",
    },
  }[slaStatus];

  // Depth bar — 0 pending = empty, 9 pending = full, capped at 100%
  const queueDepthPct = Math.min(100, Math.round((pending / 9) * 100));

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <PresentationChart
            aria-hidden
            weight="duotone"
            className="size-4"
          />
        </span>
        {activityTitle}
      </h3>

      {/* SLA queue health */}
      <div className="mb-4 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-[var(--text-secondary)]">
            {tu("queueHealth")}
          </span>
          <span
            className={cn(
              "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold leading-none",
              slaColors.badge,
            )}
          >
            <SlaIcon aria-hidden weight="fill" className="size-3" />
            {slaLabel}
          </span>
        </div>
        <div
          role="meter"
          aria-valuenow={queueDepthPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={tu("queueDepth")}
          className="h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-700 motion-reduce:transition-none",
              slaColors.bar,
            )}
            style={{ width: `${Math.max(queueDepthPct, pending > 0 ? 4 : 0)}%` }}
          />
        </div>
        <p className="text-[10px] text-[var(--text-muted)]">
          {pending} job{pending !== 1 ? "s" : ""} pending review
        </p>
      </div>

      {/* Platform stats */}
      <ul className="space-y-2.5 border-t border-[var(--border-subtle)] pt-3" role="list">
        <li className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)]">
            <Buildings
              aria-hidden
              weight="duotone"
              className="size-3.5 text-[var(--brand-primary)]"
            />
            {partnersActiveLabel}
          </span>
          <span className="font-mono text-xs font-bold tabular-nums text-[var(--text-primary)]">
            {metrics.partners_active}
          </span>
        </li>
        <li className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)]">
            <Briefcase
              aria-hidden
              weight="duotone"
              className="size-3.5 text-[var(--brand-primary)]"
            />
            {jobsActiveTotalLabel}
          </span>
          <span className="font-mono text-xs font-bold tabular-nums text-[var(--text-primary)]">
            {metrics.jobs_active_total}
          </span>
        </li>
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* University Dashboard                                                       */
/* -------------------------------------------------------------------------- */

export function UniversityDashboard() {
  const t = useTranslations("dashboard");
  const tu = useTranslations("dashboard.university");
  const tNav = useTranslations("nav");
  const locale = useLocale();
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["dashboard", "university"],
    queryFn: () => dashboardsApi.university(),
    enabled: authed,
    retry: false,
  });

  return (
    <>
      <PageHeader title={tNav("dashboard")} />

      {!authed ? (
        <DashboardGuestGate persona="university" />
      ) : query.isPending ? (
        <DashboardSkeleton tileCount={4} tileCols={4} />
      ) : query.isError ? (
        <DashboardErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        (() => {
          const data = query.data;
          const metrics: MetricItem[] = [
            {
              key: "jobs_pending_moderation",
              label: tu("metric.jobsPending"),
              value: data.metrics.jobs_pending_moderation,
              icon: ClipboardText,
              emphasize: true,
              hotNote: tu("metric.jobsPendingHotNote", {
                count: data.metrics.jobs_pending_moderation,
              }),
            },
            {
              key: "partners_pending",
              label: tu("metric.partnersPending"),
              value: data.metrics.partners_pending,
              icon: Handshake,
              emphasize: true,
              hotNote: tu("metric.partnersPendingHotNote", {
                count: data.metrics.partners_pending,
              }),
            },
            {
              key: "partners_active",
              label: tu("metric.partnersActive"),
              value: data.metrics.partners_active,
              icon: Buildings,
              tone: "info",
            },
            {
              key: "jobs_active_total",
              label: tu("metric.jobsActiveTotal"),
              value: data.metrics.jobs_active_total,
              icon: Briefcase,
              tone: "success",
            },
          ];

          return (
            <div className="space-y-6">
              {/* Row 1: 4 metric tiles */}
              <MetricTiles items={metrics} />

              {/* Operations command center — every queue grouped by function */}
              <UniversityOpsWorklist />

              {/* AI Governance Insights panel */}
              {(() => {
                const jobsPending = data.metrics.jobs_pending_moderation;
                const partnersPending = data.metrics.partners_pending;
                const partnersActive = data.metrics.partners_active;
                const jobsTotal = data.metrics.jobs_active_total;
                const insights: string[] = [];
                if (jobsPending > 8) insights.push(tu("aiInsightQueueOverloaded", { count: jobsPending }));
                else if (jobsPending > 0) insights.push(tu("aiInsightQueuePending", { count: jobsPending }));
                else insights.push(tu("aiInsightQueueClear"));
                if (partnersPending > 0) insights.push(tu("aiInsightPartnersPending", { count: partnersPending }));
                if (partnersActive > 0) insights.push(tu("aiInsightPlatformScope", { partners: partnersActive, jobs: jobsTotal }));
                return (
                  <div className={cn(
                    "marketplace-card rounded-[12px] border-l-[3px] p-4",
                    "border-l-[var(--brand-teal)]",
                  )}>
                    <p className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                      <span className="icon-chip-success flex size-6 shrink-0 items-center justify-center rounded-lg">
                        <Sparkle aria-hidden weight="duotone" className="size-3.5" />
                      </span>
                      {tu("aiInsightsTitle")}
                    </p>
                    <ul className="space-y-1.5">
                      {insights.map((text, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                          <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
                          {text}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}

              {/* Row 2: Next actions (full-width) */}
              <section aria-labelledby="university-next-actions">
                <h2
                  id="university-next-actions"
                  className="mb-3 text-base font-bold tracking-tight text-[var(--text-primary)]"
                >
                  {t("nextActions")}
                </h2>
                <NextActionsRail
                  actions={data.next_actions}
                  emptyTitle={tu("actionsEmptyTitle")}
                  emptyBody={tu("actionsEmptyBody")}
                />
              </section>

              {/* Row 3: 3-column ops grid */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                {/* Left: Job moderation queue */}
                <DashboardSection
                  icon={Gavel}
                  tone="danger"
                  title={tu("moderationTitle")}
                  count={data.moderation_queue_recent.length}
                  action={
                    <SectionLink href="/university/moderation/jobs">
                      {tu("openQueue")}
                    </SectionLink>
                  }
                >
                  {data.moderation_queue_recent.length === 0 ? (
                    <EmptyState
                      kind="empty"
                      icon={ShieldCheck}
                      title={tu("noModerationTitle")}
                      description={tu("noModerationBody")}
                    />
                  ) : (
                    <QueueList>
                      {data.moderation_queue_recent.map((item) => (
                        <li key={item.id}>
                          <Link
                            href="/university/moderation/jobs"
                            className={QUEUE_ROW_CLASS}
                          >
                            <div className="min-w-0">
                              <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">
                                {item.title}
                              </h3>
                              <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                                {item.company_name ?? tu("unknownCompany")}
                                {" · "}
                                {formatDateTime(item.submitted_at, locale)}
                              </p>
                            </div>
                          </Link>
                        </li>
                      ))}
                    </QueueList>
                  )}
                </DashboardSection>

                {/* Center: Partner registration requests */}
                <DashboardSection
                  icon={Handshake}
                  tone="success"
                  title={tu("partnerRequestsTitle")}
                  count={data.partner_requests_recent.length}
                  action={
                    <SectionLink href="/university/partners">
                      {tu("openPartners")}
                    </SectionLink>
                  }
                >
                  {data.partner_requests_recent.length === 0 ? (
                    <EmptyState
                      kind="empty"
                      icon={Buildings}
                      title={tu("noPartnerRequestsTitle")}
                      description={tu("noPartnerRequestsBody")}
                    />
                  ) : (
                    <QueueList>
                      {data.partner_requests_recent.map((item) => (
                        <li key={item.id}>
                          <Link
                            href="/university/partners"
                            className={QUEUE_ROW_CLASS}
                          >
                            <div className="min-w-0">
                              <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">
                                {item.company_name ?? tu("unknownCompany")}
                              </h3>
                              <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                                {tu("requestedOn", {
                                  date: formatDateTime(item.submitted_at, locale),
                                })}
                              </p>
                            </div>
                          </Link>
                        </li>
                      ))}
                    </QueueList>
                  )}
                </DashboardSection>

                {/* Right: Activity summary + SLA indicator */}
                <ActivitySummaryStrip
                  metrics={data.metrics}
                  activityTitle={tu("activityTitle")}
                  onTrackLabel={tu("queueOnTrack")}
                  buildingLabel={tu("queueBuilding")}
                  overloadedLabel={tu("queueOverloaded")}
                  partnersActiveLabel={tu("metric.partnersActive")}
                  jobsActiveTotalLabel={tu("metric.jobsActiveTotal")}
                />
              </div>
            </div>
          );
        })()
      )}
    </>
  );
}
