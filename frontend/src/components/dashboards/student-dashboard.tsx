"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  Briefcase,
  CalendarBlank,
  PaperPlaneTilt,
  ReadCvLogo,
  ClockCounterClockwise,
  VideoCamera,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, StatusBadge } from "@/components/ui";
import { JobRow } from "@/components/jobs/job-row";
import { ReasonChips } from "@/components/discovery/reason-chips";
import type { RecoSource } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_TONE,
  useApplicationLabels,
} from "@/lib/applications/labels";
import { dashboardsApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import {
  DashboardErrorState,
  DashboardGuestGate,
  DashboardSection,
  DashboardSkeleton,
  MetricTiles,
  NextActionsRail,
  SectionLink,
  type MetricItem,
} from "./dashboard-kit";

/** Honest rail title key by ranking source (never "recommended" for a fallback). */
function rolesTitleKey(source: RecoSource): string {
  if (source === "recommended") return "recommendedRolesTitle";
  if (source === "popular") return "popularRolesTitle";
  return "recentRolesTitle";
}

export function StudentDashboard() {
  const t = useTranslations("dashboard");
  const ts = useTranslations("dashboard.student");
  const locale = useLocale();
  const labels = useApplicationLabels();
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["dashboard", "student"],
    queryFn: () => dashboardsApi.student(),
    enabled: authed,
    retry: false,
  });

  return (
    <>
      <section className="mb-7 overflow-hidden rounded-[18px] border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_14px_44px_rgba(11,34,57,0.10)]">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="relative bg-[var(--brand-navy)] p-6 sm:p-8">
            <div
              aria-hidden
              className="absolute inset-0 opacity-[0.16]"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, rgba(255,255,255,0.16) 1px, transparent 1px)",
                backgroundSize: "28px 28px",
              }}
            />
            <div className="relative max-w-2xl">
              <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--blue-200)]">
                VinUni Career
              </p>
              <h1 className="mt-3 text-3xl font-extrabold leading-tight tracking-tight text-white sm:text-4xl">
                {ts("title")}
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--blue-100)]/86">
                {ts("subtitle")}
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link href="/jobs">
                  <Button variant="secondary">
                    <Briefcase aria-hidden weight="bold" className="size-4" />
                    {ts("browseJobs")}
                  </Button>
                </Link>
                <Link href="/student/cv">
                  <Button variant="ghost" className="border-white/20 bg-white/10 text-white hover:bg-white/16">
                    <ReadCvLogo aria-hidden weight="bold" className="size-4" />
                    CV Studio
                  </Button>
                </Link>
              </div>
            </div>
          </div>
          <div className="border-t border-[var(--border-default)] bg-[var(--surface-card)] p-6 lg:border-l lg:border-t-0">
            <div className="grid gap-3">
              <div className="rounded-[14px] border border-[var(--border-default)] bg-[var(--surface-secondary)] p-4">
                <p className="text-xs font-semibold text-[var(--text-secondary)]">
                  {ts("metric.cvCount")}
                </p>
                <p className="mt-1 text-2xl font-black text-[var(--brand-navy)]">CV Studio</p>
              </div>
              <div className="rounded-[14px] border border-[var(--border-default)] bg-[var(--ai-accent-soft)] p-4">
                <p className="text-xs font-semibold text-[var(--ai-accent)]">
                  {ts("recommendedRolesTitle")}
                </p>
                <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
                  {ts("actionsEmptyBody")}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {!authed ? (
        <DashboardGuestGate persona="student" />
      ) : query.isPending ? (
        <DashboardSkeleton />
      ) : query.isError ? (
        <DashboardErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        (() => {
          const data = query.data;
          const metrics: MetricItem[] = [
            {
              key: "applications_total",
              label: ts("metric.applicationsTotal"),
              value: data.metrics.applications_total,
              icon: PaperPlaneTilt,
              tone: "primary",
            },
            {
              key: "applications_active",
              label: ts("metric.applicationsActive"),
              value: data.metrics.applications_active,
              icon: Briefcase,
              tone: "info",
            },
            {
              key: "cv_count",
              label: ts("metric.cvCount"),
              value: data.metrics.cv_count,
              icon: ReadCvLogo,
              tone: "success",
            },
            {
              key: "alert_count",
              label: ts("metric.alertCount"),
              value: data.metrics.alert_count,
              icon: Bell,
              tone: "warning",
            },
          ];

          return (
            <div className="space-y-8">
              <MetricTiles items={metrics} />

              <section aria-labelledby="student-next-actions">
                <h2
                  id="student-next-actions"
                  className="mb-3 text-base font-bold tracking-tight text-[var(--text-primary)]"
                >
                  {t("nextActions")}
                </h2>
                <NextActionsRail
                  actions={data.next_actions}
                  emptyTitle={ts("actionsEmptyTitle")}
                  emptyBody={ts("actionsEmptyBody")}
                />
              </section>

              {/* Upcoming interviews */}
              {data.upcoming_interviews.length > 0 && (
                <DashboardSection
                  icon={VideoCamera}
                  tone="success"
                  title={ts("upcomingInterviewsTitle")}
                  count={data.upcoming_interviews.length}
                >
                  <ul className="space-y-3">
                    {data.upcoming_interviews.map((iv) => (
                      <li key={iv.id}>
                        <Link
                          href={`/student/applications/${iv.application_id}`}
                          className="marketplace-card marketplace-card-hover flex flex-col gap-2 rounded-[14px] p-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 sm:flex-row sm:items-center sm:justify-between"
                        >
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-bold text-[var(--text-primary)]">
                              {iv.title ?? iv.job_title ?? ts("untitledJob")}
                            </h3>
                            <p className="mt-0.5 truncate text-xs text-[var(--text-secondary)]">
                              {iv.company_name ?? ts("unknownCompany")}
                              {" · "}
                              {formatDateTime(iv.scheduled_at, locale)}
                            </p>
                            {iv.location && (
                              <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                                {iv.location}
                              </p>
                            )}
                          </div>
                          <span className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                            {ts("viewInterview")}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </DashboardSection>
              )}

              {/* Upcoming registered events */}
              {data.upcoming_events.length > 0 && (
                <DashboardSection
                  icon={CalendarBlank}
                  tone="success"
                  title={ts("upcomingEventsTitle")}
                  count={data.upcoming_events.length}
                  action={
                    <SectionLink href="/events">{t("viewAll")}</SectionLink>
                  }
                >
                  <ul className="space-y-3">
                    {data.upcoming_events.map((ev) => (
                      <li key={ev.event_id}>
                        <Link
                          href={`/events/${ev.event_id}`}
                          className="marketplace-card marketplace-card-hover flex flex-col gap-2 rounded-[14px] p-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 sm:flex-row sm:items-center sm:justify-between"
                        >
                          <div className="min-w-0 flex-1">
                            <h3 className="truncate text-sm font-bold text-[var(--text-primary)]">
                              {ev.title}
                            </h3>
                            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                              {ev.starts_at && (
                                <p className="text-xs text-[var(--text-secondary)]">
                                  {formatDateTime(ev.starts_at, locale)}
                                </p>
                              )}
                              <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                                {ev.event_type_label}
                              </span>
                              <span className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                                {ev.format_label}
                              </span>
                              {ev.registration_status === "waitlisted" && (
                                <span className="inline-flex items-center rounded-full border border-[var(--amber-600)]/40 bg-[var(--amber-100)]/50 px-2 py-0.5 text-[10px] font-medium text-[var(--amber-700)]">
                                  {ev.registration_status_label}
                                </span>
                              )}
                            </div>
                            {ev.venue_name && ev.format !== "online" && (
                              <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                                {ev.venue_name}
                              </p>
                            )}
                          </div>
                          <span className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                            {ts("viewEvent")}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </DashboardSection>
              )}

              <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                {/* Recent applications */}
                <DashboardSection
                  icon={ClockCounterClockwise}
                  tone="neutral"
                  title={ts("recentApplicationsTitle")}
                  action={
                    <SectionLink href="/student/applications">
                      {t("viewAll")}
                    </SectionLink>
                  }
                >
                  {data.applications_recent.length === 0 ? (
                    <EmptyState
                      kind="empty"
                      icon={Briefcase}
                      title={ts("noApplicationsTitle")}
                      description={ts("noApplicationsBody")}
                      action={
                        <Link href="/jobs">
                          <Button variant="primary">
                            <Briefcase aria-hidden weight="bold" className="size-4" />
                            {ts("browseJobs")}
                          </Button>
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="space-y-3">
                      {data.applications_recent.map((app) => (
                        <li key={app.id}>
                          <Link
                            href={`/student/applications/${app.id}`}
                            className="marketplace-card marketplace-card-hover flex items-center justify-between gap-3 rounded-[14px] p-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                          >
                            <div className="min-w-0">
                              <h3 className="truncate text-sm font-bold text-[var(--text-primary)]">
                                {app.job_title ?? ts("untitledJob")}
                              </h3>
                              <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                                {app.company_name ?? ts("unknownCompany")}
                                {" · "}
                                {formatDateTime(app.submitted_at, locale)}
                              </p>
                            </div>
                            <StatusBadge
                              tone={APPLICATION_STATUS_TONE[app.status] ?? "info"}
                            >
                              {labels.status(app.status, app.status_label)}
                            </StatusBadge>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </DashboardSection>

                {/* Roles rail — labelled HONESTLY by source: "Đề xuất cho bạn"
                    only when personalized; otherwise "Mới đăng"/"Phổ biến". */}
                <DashboardSection
                  icon={Briefcase}
                  tone="primary"
                  title={ts(rolesTitleKey(data.recommended_jobs.source))}
                  action={
                    <SectionLink href="/jobs">{t("viewAll")}</SectionLink>
                  }
                >
                  {data.recommended_jobs.items.length === 0 ? (
                    <EmptyState
                      kind="empty"
                      icon={Briefcase}
                      title={ts("noRolesTitle")}
                      description={ts("noRolesBody")}
                    />
                  ) : (
                    <ul className="space-y-3">
                      {data.recommended_jobs.items.map((job) => (
                        <li key={job.id} className="space-y-2">
                          <JobRow job={job} />
                          {data.recommended_jobs.source === "recommended" &&
                            job.reason_codes.length > 0 && (
                              <ReasonChips
                                reasons={job.reason_codes}
                                className="px-1"
                              />
                            )}
                        </li>
                      ))}
                    </ul>
                  )}
                </DashboardSection>
              </div>
            </div>
          );
        })()
      )}
    </>
  );
}
