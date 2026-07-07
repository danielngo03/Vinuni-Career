"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Heart, SignIn, Sparkle, WarningCircle } from "@phosphor-icons/react";
import { Button, EmptyState, InsightPanel, Skeleton } from "@/components/ui";
import type { InsightItem } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { JobCard } from "@/components/jobs/job-card";
import { ApiError, jobsApi, type JobSummary } from "@/lib/api";

export function SavedJobsScreen() {
  const t = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");

  const query = useInfiniteQuery({
    queryKey: ["jobs", "saved"],
    queryFn: ({ pageParam }) =>
      jobsApi.listSaved({ cursor: pageParam as string | undefined, limit: 20 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  const jobs: JobSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  if (query.isError && query.error instanceof ApiError && query.error.isAuthError) {
    return (
      <>
        <PageHeader title={t("savedJobsTitle")} />
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
      <PageHeader title={t("savedJobsTitle")} />

      {query.isError ? (
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
      ) : query.isPending ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full rounded-2xl" />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={Heart}
          title={t("savedJobsEmptyTitle")}
          description={t("savedJobsEmpty")}
        />
      ) : (
        <>
          {/* Saved count header */}
          <p className="mb-4 text-xs font-medium text-[var(--text-muted)]">
            {t("savedCount", { count: query.data?.pages[0]?.page.total ?? jobs.length })}
          </p>

          {/* Saved jobs signals */}
          {jobs.length > 0 && (() => {
            const total = query.data?.pages[0]?.page.total ?? jobs.length;
            const now = Date.now();
            const soonCount = jobs.filter((j) => {
              if (!j.application_deadline) return false;
              const ms = new Date(j.application_deadline).getTime() - now;
              return ms > 0 && ms <= 7 * 86_400_000;
            }).length;
            const featuredCount = jobs.filter((j) => j.is_featured).length;
            const items: InsightItem[] = [
              { label: t("aiInsightSaved", { count: total }), tone: "neutral" },
            ];
            if (soonCount > 0)
              items.push({ label: t("aiInsightDeadlineSoon", { count: soonCount }), tone: "warning" });
            if (featuredCount > 0)
              items.push({ label: t("aiInsightFeatured", { count: featuredCount }), tone: "neutral" });
            return (
              <InsightPanel
                className="mb-6"
                title={t("aiInsightsTitle")}
                icon={<Sparkle aria-hidden weight="duotone" className="size-4" />}
                items={items}
              />
            );
          })()}

          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.map((job) => (
              <li key={job.id}>
                <JobCard job={{ ...job, is_saved: true }} />
              </li>
            ))}
          </ul>

          {query.hasNextPage && (
            <div className="mt-8 flex justify-center">
              <Button
                variant="secondary"
                onClick={() => query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
              >
                {query.isFetchingNextPage ? tc("loading") : tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
