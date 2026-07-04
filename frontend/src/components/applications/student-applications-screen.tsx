"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CalendarCheck,
  ClipboardText,
  CurrencyDollar,
  LightbulbFilament,
  SignIn,
  Sparkle,
  WarningCircle,
  PaperPlaneTilt,
  Handshake,
  CheckCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton, StatusBadge } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_TONE,
  INTERVIEW_STATUS_TONE,
  useApplicationLabels,
  useInterviewLabels,
  useOfferLabels,
} from "@/lib/applications/labels";
import { ApiError, applicationsApi, type StudentApplication } from "@/lib/api";

function ApplicationStatusProgress({
  status,
  hasUpcomingInterview,
  hasOffer,
}: {
  status: string;
  hasUpcomingInterview: boolean;
  hasOffer: boolean;
}) {
  // Four honest, real-signal steps. `interview`/`offer` are never
  // `application.status` values — they come from the student's own
  // upcoming-interview / offer cards, tracked separately from status.
  const STEPS = ["submitted", "under_review", "interview_or_offer", "hired"] as const;

  const isTerminal = ["rejected", "withdrawn"].includes(status);
  if (isTerminal) return null;

  let currentIdx = 0;
  if (status === "hired") currentIdx = 3;
  else if (hasOffer || hasUpcomingInterview) currentIdx = 2;
  else if (status === "under_review") currentIdx = 1;

  return (
    <div className="mt-2 flex items-center gap-1" aria-hidden>
      {STEPS.map((step, idx) => (
        <span
          key={step}
          className={`h-1.5 flex-1 rounded-full transition-colors ${
            idx <= currentIdx
              ? "bg-[var(--brand-primary)]"
              : "bg-[var(--bg-muted)]"
          }`}
        />
      ))}
    </div>
  );
}

type AppInsightKey =
  | "insightOfferPending"
  | "insightInterviewUpcoming"
  | "insightGoodMomentum"
  | "insightApplyMore"
  | "insightKeepApplying";

interface AppInsight {
  key: AppInsightKey;
  values?: Record<string, string>;
}

function deriveApplicationInsights(rows: StudentApplication[]): AppInsight[] {
  const out: AppInsight[] = [];
  const offers = rows.filter((r) => r.offer !== null && r.offer !== undefined).length;
  const interviews = rows.filter(
    (r) => r.upcoming_interview !== null && r.upcoming_interview !== undefined,
  ).length;
  // "In progress" = actively moving forward, not a terminal outcome: under
  // review, or carrying a live interview/offer signal.
  const inProgress = rows.filter(
    (r) =>
      r.status === "under_review" ||
      Boolean(r.upcoming_interview) ||
      Boolean(r.offer),
  ).length;

  if (offers > 0) out.push({ key: "insightOfferPending", values: { count: String(offers) } });
  if (interviews > 0) out.push({ key: "insightInterviewUpcoming", values: { count: String(interviews) } });
  if (inProgress >= 3 && offers === 0) out.push({ key: "insightGoodMomentum", values: { count: String(inProgress) } });
  if (out.length === 0 && rows.length > 0 && rows.length < 5) out.push({ key: "insightApplyMore" });
  if (out.length === 0 && rows.length >= 5 && inProgress === 0) out.push({ key: "insightKeepApplying" });
  return out.slice(0, 3);
}

export function StudentApplicationsScreen() {
  const t = useTranslations("applications");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useApplicationLabels();
  const interviewLabels = useInterviewLabels();
  const offerLabels = useOfferLabels();

  const query = useInfiniteQuery({
    queryKey: ["applications", "mine"],
    queryFn: ({ pageParam }) =>
      applicationsApi.listMine({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: StudentApplication[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const appInsights = useMemo(() => deriveApplicationInsights(rows), [rows]);

  if (query.isError && query.error instanceof ApiError && query.error.isAuthError) {
    return (
      <>
        <PageHeader title={t("listTitle")} description={t("listSubtitle")} />
        <EmptyState
          kind="auth"
          icon={SignIn}
          title={tStates("authTitle")}
          description={tStates("authBody")}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t("listTitle")} description={t("listSubtitle")} />

      {query.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-2xl" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={ClipboardText}
          title={t("emptyTitle")}
          description={t("emptyBody")}
          action={
            <Link href="/jobs">
              <Button variant="primary">
                <Briefcase aria-hidden weight="bold" className="size-4" />
                {t("browseJobs")}
              </Button>
            </Link>
          }
        />
      ) : (
        <>
          {/* Application summary tiles */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                <PaperPlaneTilt aria-hidden weight="duotone" className="size-4.5 text-white" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{rows.length}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statTotalApplied")}</p>
            </div>
            <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
                <CalendarCheck aria-hidden weight="duotone" className="size-4.5 text-white" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
                {rows.filter((r) => r.upcoming_interview !== null && r.upcoming_interview !== undefined).length}
              </p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statInterviews")}</p>
            </div>
            <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-info shadow-sm">
                <Handshake aria-hidden weight="duotone" className="size-4.5 text-white" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
                {rows.filter((r) => r.offer !== null && r.offer !== undefined).length}
              </p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statOffers")}</p>
            </div>
            <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
                <CheckCircle aria-hidden weight="duotone" className="size-4.5 text-white" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
                {
                  rows.filter(
                    (r) =>
                      r.status === "under_review" ||
                      Boolean(r.upcoming_interview) ||
                      Boolean(r.offer),
                  ).length
                }
              </p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statInProgress")}</p>
            </div>
          </div>

          {/* AI Application Insights */}
          {appInsights.length > 0 && (
            <section
              className="mb-5 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] p-4 backdrop-blur-xl"
              aria-label={t("listAiInsightsTitle")}
            >
              <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                  <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
                {t("listAiInsightsTitle")}
              </h2>
              <ul className="space-y-1.5">
                {appInsights.map((insight) => (
                  <li key={insight.key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                    <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                    {insight.values ? t(insight.key, insight.values) : t(insight.key)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <ul className="space-y-3">
            {rows.map((app) => (
              <li key={app.id}>
                <Link
                  href={`/student/applications/${app.id}`}
                  className="flex flex-col gap-0 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-4 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md outline-none transition-all hover:border-[var(--brand-primary)]/40 hover:bg-[var(--glass-surface-heavy)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  <div className="flex items-start gap-3.5">
                    <CompanyAvatar
                      name={app.company_name ?? app.job_title ?? "?"}
                      size="md"
                      className="mt-0.5 shrink-0"
                    />
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-base font-bold text-[var(--text-primary)]">
                        {app.job_title ?? t("untitledJob")}
                      </h3>
                      {app.company_name && (
                        <p className="truncate text-sm font-medium text-[var(--text-secondary)]">
                          {app.company_name}
                        </p>
                      )}
                      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                        {t("appliedOn", {
                          date: formatDateTime(app.applied_at, locale),
                        })}
                        {app.is_anonymous ? ` · ${t("anonymousBadge")}` : ""}
                      </p>

                      {/* Progress bar for active applications */}
                      <ApplicationStatusProgress
                        status={app.status}
                        hasUpcomingInterview={Boolean(app.upcoming_interview)}
                        hasOffer={Boolean(app.offer)}
                      />
                    </div>

                    <div className="flex shrink-0 flex-col items-end gap-1.5">
                      <StatusBadge
                        tone={APPLICATION_STATUS_TONE[app.status] ?? "info"}
                      >
                        {labels.status(app.status, app.status_label)}
                      </StatusBadge>
                    </div>
                  </div>

                  {/* Contextual badges — upcoming interview or offer */}
                  {(app.upcoming_interview || app.offer) && (
                    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--border-default)] pt-3">
                      {app.upcoming_interview && (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--teal-100)] bg-[var(--teal-50)] px-2.5 py-1 text-xs font-semibold text-[var(--teal-700)]">
                          <CalendarCheck
                            aria-hidden
                            weight="fill"
                            className="size-3.5"
                          />
                          {formatDateTime(
                            app.upcoming_interview.scheduled_at,
                            locale,
                          )}
                          <StatusBadge
                            tone={
                              INTERVIEW_STATUS_TONE[
                                app.upcoming_interview.status
                              ] ?? "info"
                            }
                            className="text-[10px]"
                          >
                            {interviewLabels.status(
                              app.upcoming_interview.status,
                            )}
                          </StatusBadge>
                        </span>
                      )}
                      {app.offer && (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--amber-100)] bg-[var(--amber-50)] px-2.5 py-1 text-xs font-semibold text-[var(--amber-700)]">
                          <CurrencyDollar
                            aria-hidden
                            weight="fill"
                            className="size-3.5"
                          />
                          {offerLabels.status(
                            app.offer.status,
                            app.offer.status_label,
                          )}
                        </span>
                      )}
                    </div>
                  )}
                </Link>
              </li>
            ))}
          </ul>

          {query.hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
