"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Heart, LightbulbFilament, SignIn, Sparkle, WarningCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button, EmptyState, Skeleton } from "@/components/ui";
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

          {/* AI Saved Jobs Insights */}
          {jobs.length > 0 && (() => {
            const total = query.data?.pages[0]?.page.total ?? jobs.length;
            const now = Date.now();
            const soonCount = jobs.filter((j) => {
              if (!j.application_deadline) return false;
              const ms = new Date(j.application_deadline).getTime() - now;
              return ms > 0 && ms <= 7 * 86_400_000;
            }).length;
            const featuredCount = jobs.filter((j) => j.is_featured).length;
            const insights: string[] = [];
            insights.push(t("aiInsightSaved", { count: total }));
            if (soonCount > 0) insights.push(t("aiInsightDeadlineSoon", { count: soonCount }));
            if (featuredCount > 0) insights.push(t("aiInsightFeatured", { count: featuredCount }));
            return (
              <div className={cn(
                "mb-6 rounded-2xl border p-4",
                "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] backdrop-blur-xl",
              )}>
                <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                    <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                  </span>
                  {t("aiInsightsTitle")}
                </p>
                <ul className="space-y-1.5">
                  {insights.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                      <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
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
