"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Briefcase,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  DataTable,
  EmptyState,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { useJobLabels, JOB_STATUS_TONE } from "@/lib/jobs/labels";
import { formatLocation } from "@/lib/jobs/format";
import { ApiError, jobsApi, type OwnerJobSummary } from "@/lib/api";

function deriveIndexInsights(rows: OwnerJobSummary[], t: (key: string, values?: Record<string, unknown>) => string): string[] {
  const insights: string[] = [];
  const activeJobs = rows.filter((r) => r.status === "active");
  const pendingModeration = rows.filter((r) => r.moderation_status === "pending");
  const now = Date.now();
  const in7Days = now + 7 * 24 * 60 * 60 * 1000;
  const deadlineSoon = activeJobs.filter((r) => {
    if (!r.application_deadline) return false;
    const dl = new Date(r.application_deadline).getTime();
    return dl > now && dl < in7Days;
  });
  const draftJobs = rows.filter((r) => r.status === "draft");

  if (activeJobs.length > 0) insights.push(t("indexInsightActiveJobs", { count: activeJobs.length }));
  if (deadlineSoon.length > 0) insights.push(t("indexInsightDeadlineSoon", { count: deadlineSoon.length }));
  if (pendingModeration.length > 0) insights.push(t("indexInsightPendingApproval", { count: pendingModeration.length }));
  if (draftJobs.length > 0 && activeJobs.length === 0) insights.push(t("indexInsightDrafts", { count: draftJobs.length }));
  if (insights.length === 0) insights.push(t("indexInsightAllGood"));
  return insights.slice(0, 3);
}

export function PartnerCandidatesIndex() {
  const t = useTranslations("candidates");
  const tNav = useTranslations("nav");
  const tJobs = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const labels = useJobLabels();

  const query = useInfiniteQuery({
    queryKey: ["jobs", "mine", "candidates"],
    queryFn: ({ pageParam }) => jobsApi.listMine({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: OwnerJobSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader eyebrow={tNav("group.recruitment")} title={t("indexTitle")} description={t("indexSubtitle")} />
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
  }

  const columns: Column<OwnerJobSummary>[] = [
    {
      key: "title",
      header: tJobs("colTitle"),
      cell: (job) => (
        <Link
          href={`/partner/jobs/${job.id}/applications`}
          className="font-semibold text-[var(--text-primary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
        >
          {job.title}
        </Link>
      ),
    },
    {
      key: "type",
      header: tJobs("colType"),
      cell: (job) => (
        <span className="text-[var(--text-secondary)]">
          {labels.employmentType(job.employment_type, job.employment_type_label)}
          {" · "}
          {labels.locationType(job.location_type, job.location_type_label)}
        </span>
      ),
    },
    {
      key: "location",
      header: tJobs("location"),
      cell: (job) => (
        <span className="text-[var(--text-secondary)]">
          {formatLocation(job.location_city, job.location_country)}
        </span>
      ),
    },
    {
      key: "status",
      header: tJobs("colStatus"),
      cell: (job) => (
        <StatusBadge tone={JOB_STATUS_TONE[job.status] ?? "info"}>
          {labels.status(job.status, job.status_label)}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (job) => (
        <Link href={`/partner/jobs/${job.id}/applications`}>
          <Button variant="ghost" size="sm">
            <Users aria-hidden weight="duotone" className="size-4" />
            {tJobs("viewCandidates")}
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <>
      <PageHeader eyebrow={tNav("group.recruitment")} title={t("indexTitle")} description={t("indexSubtitle")} />

      {query.isError &&
      !(
        query.error instanceof ApiError &&
        (query.error.isPermissionError || query.error.isAuthError)
      ) ? (
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
      ) : (
        <>
          {rows.length > 0 && (() => {
            const insights = deriveIndexInsights(rows, t as (key: string, values?: Record<string, unknown>) => string);
            return (
              <div className="mb-5 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 ">
                <div className="mb-2.5 flex items-center gap-2">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
                    <Sparkle aria-hidden weight="duotone" className="size-3 text-white" />
                  </span>
                  <span className="text-xs font-bold uppercase tracking-wide text-[var(--ai-accent)]">
                    {t("indexAiInsightsTitle")}
                  </span>
                </div>
                <ul className="space-y-1.5">
                  {insights.map((insight, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                      <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--ai-accent)]" />
                      {insight}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}
          <DataTable
            columns={columns}
            rows={rows}
            getRowId={(job) => job.id}
            loading={query.isPending}
            caption={t("indexTitle")}
            empty={{
              kind: "empty",
              icon: Briefcase,
              title: t("indexEmptyTitle"),
              description: t("indexEmptyBody"),
              action: (
                <Link href="/partner/jobs">
                  <Button variant="primary">{t("goToJobs")}</Button>
                </Link>
              ),
            }}
          />

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
