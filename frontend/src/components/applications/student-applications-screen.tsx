"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CalendarCheck,
  ClipboardText,
  CurrencyDollar,
  LightbulbFilament,
  SignIn,
  WarningCircle,
  PaperPlaneTilt,
  Handshake,
  CheckCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  FilterChip,
  InsightPanel,
  ListToolbar,
  SearchInput,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
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

const INSIGHT_TONE: Record<AppInsightKey, "neutral" | "success" | "warning" | "danger"> = {
  insightOfferPending: "warning",
  insightInterviewUpcoming: "success",
  insightGoodMomentum: "success",
  insightApplyMore: "neutral",
  insightKeepApplying: "neutral",
};

type StatusFilter = "all" | "in_progress" | "interview" | "offer";

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

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const counts = useMemo(
    () => ({
      total: rows.length,
      interview: rows.filter((r) => Boolean(r.upcoming_interview)).length,
      offer: rows.filter((r) => Boolean(r.offer)).length,
      inProgress: rows.filter(
        (r) =>
          r.status === "under_review" ||
          Boolean(r.upcoming_interview) ||
          Boolean(r.offer),
      ).length,
    }),
    [rows],
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (statusFilter === "interview" && !r.upcoming_interview) return false;
      if (statusFilter === "offer" && !r.offer) return false;
      if (
        statusFilter === "in_progress" &&
        !(r.status === "under_review" || r.upcoming_interview || r.offer)
      )
        return false;
      if (
        q &&
        !`${r.job_title ?? ""} ${r.company_name ?? ""}`.toLowerCase().includes(q)
      )
        return false;
      return true;
    });
  }, [rows, statusFilter, search]);

  const filtersActive = search.trim() !== "" || statusFilter !== "all";

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
          {/* Application summary tiles — flat tokenized cards (was glass). */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="marketplace-card rounded-2xl px-4 py-3.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary">
                <PaperPlaneTilt aria-hidden weight="duotone" className="size-4.5" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{counts.total}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statTotalApplied")}</p>
            </div>
            <div className="marketplace-card rounded-2xl px-4 py-3.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success">
                <CalendarCheck aria-hidden weight="duotone" className="size-4.5" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{counts.interview}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statInterviews")}</p>
            </div>
            <div className="marketplace-card rounded-2xl px-4 py-3.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-info">
                <Handshake aria-hidden weight="duotone" className="size-4.5" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{counts.offer}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statOffers")}</p>
            </div>
            <div className="marketplace-card rounded-2xl px-4 py-3.5">
              <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success">
                <CheckCircle aria-hidden weight="duotone" className="size-4.5" />
              </div>
              <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{counts.inProgress}</p>
              <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statInProgress")}</p>
            </div>
          </div>

          {/* Application signals — flat monochrome panel (was a gradient,
              "AI"-styled card; these are deterministic heuristics, not AI). */}
          <InsightPanel
            className="mb-5"
            title={t("listAiInsightsTitle")}
            icon={<LightbulbFilament aria-hidden weight="duotone" className="size-4" />}
            items={appInsights.map((insight) => ({
              label: insight.values ? t(insight.key, insight.values) : t(insight.key),
              tone: INSIGHT_TONE[insight.key],
            }))}
          />

          {/* Filter / search toolbar */}
          <ListToolbar
            className="mb-4"
            search={
              <SearchInput
                value={search}
                onValueChange={setSearch}
                onClear={() => setSearch("")}
                ariaLabel={tc("search")}
                placeholder={tc("search")}
              />
            }
            filters={
              <>
                <FilterChip
                  active={statusFilter === "all"}
                  onClick={() => setStatusFilter("all")}
                  count={counts.total}
                >
                  {tc("all")}
                </FilterChip>
                <FilterChip
                  active={statusFilter === "in_progress"}
                  onClick={() => setStatusFilter("in_progress")}
                  count={counts.inProgress}
                >
                  {t("statInProgress")}
                </FilterChip>
                <FilterChip
                  active={statusFilter === "interview"}
                  onClick={() => setStatusFilter("interview")}
                  count={counts.interview}
                >
                  {t("statInterviews")}
                </FilterChip>
                <FilterChip
                  active={statusFilter === "offer"}
                  onClick={() => setStatusFilter("offer")}
                  count={counts.offer}
                >
                  {t("statOffers")}
                </FilterChip>
              </>
            }
            count={<span>{tc("results", { count: filteredRows.length })}</span>}
          />

          {filteredRows.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={ClipboardText}
              title={tc("noResultsTitle")}
              description={tc("noResultsBody")}
              action={
                filtersActive ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSearch("");
                      setStatusFilter("all");
                    }}
                  >
                    {tc("clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className="space-y-3">
              {filteredRows.map((app) => (
              <li key={app.id}>
                <Link
                  href={`/student/applications/${app.id}`}
                  className="marketplace-card marketplace-card-hover flex flex-col gap-0 rounded-2xl p-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
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
          )}

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
