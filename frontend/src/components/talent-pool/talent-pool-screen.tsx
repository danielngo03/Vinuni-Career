"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { Button } from "@/components/ui";
import { EmptyState, PageHeader } from "@/components/kit";
import { ApiError, talentPoolApi } from "@/lib/api";
import { TalentSearchPanel, type TalentSearchCriteria } from "./talent-search-panel";
import { TalentResultCard } from "./talent-result-card";

const PAGE_SIZE = 12;

/* -------------------------------------------------------------------------- */
/* Source indicator — honest provenance of the ranking that served the page.   */
/* -------------------------------------------------------------------------- */

function SourceIndicator({ source }: { source: "ai_semantic" | "keyword_fallback" }) {
  const t = useTranslations("talentPool");
  if (source === "keyword_fallback") {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full bg-[var(--content-warning-soft)] px-2.5 py-1 text-xs font-medium text-[var(--content-warning)]"
        title={t("sourceFallbackHint")}
      >
        <Info aria-hidden className="size-3.5 shrink-0" strokeWidth={1.9} />
        {t("sourceFallback")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--content-ai-soft)] px-2.5 py-1 text-xs font-medium text-[var(--content-ai)]">
      <Sparkles aria-hidden className="size-3.5 shrink-0" strokeWidth={1.9} />
      {t("sourceAi")}
    </span>
  );
}

function ResultsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-[220px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Talent Pool — AI semantic candidate search (the "Kho nhân tài" destination).
 *
 * A recruiter expresses a hiring need (pasted/uploaded JD — posted or not —,
 * required skills, minimum experience, and/or free text) and gets the best-matching
 * CONSENTED candidates ranked with a categorical match TIER and human-readable
 * REASONS. No score/percentage/provider is ever shown. Every state degrades
 * honestly: start guidance, loading skeletons, empty, 422 (need a criterion),
 * 403 (no candidate-access capability), auth, and generic error with retry.
 */
export function TalentPoolScreen() {
  const t = useTranslations("talentPool");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const [criteria, setCriteria] = React.useState<TalentSearchCriteria | null>(null);

  const query = useInfiniteQuery({
    queryKey: ["talent-search", criteria],
    enabled: criteria !== null,
    queryFn: ({ pageParam }) =>
      talentPoolApi.search({ ...criteria!, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const { total, limit, offset } = last.page;
      const next = offset + limit;
      return total != null && next < total ? next : undefined;
    },
    retry: false,
  });

  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const source = pages[0]?.source;
  const total = pages[0]?.page.total ?? items.length;

  const err = query.error instanceof ApiError ? query.error : null;

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      <div className="space-y-5">
        <TalentSearchPanel
          onSearch={setCriteria}
          onClear={() => setCriteria(null)}
          loading={query.isFetching && !query.isFetchingNextPage}
          hasResults={criteria !== null}
        />

        {/* Results region */}
        {criteria === null ? (
          <EmptyState kind="empty" title={t("startTitle")} description={t("startBody")} />
        ) : query.isPending ? (
          <ResultsSkeleton />
        ) : err ? (
          err.isAuthError ? (
            <EmptyState kind="auth" title={tStates("authTitle")} description={tStates("authBody")} />
          ) : err.isPermissionError ? (
            <EmptyState kind="permission" title={t("lockedTitle")} description={t("lockedBody")} />
          ) : err.isValidation ? (
            <EmptyState kind="empty" title={t("needCriteriaTitle")} description={t("needCriteriaBody")} />
          ) : (
            <EmptyState
              kind="error"
              title={tStates("errorTitle")}
              description={tStates("errorBody")}
              action={
                <Button variant="secondary" onClick={() => query.refetch()}>
                  {tc("retry")}
                </Button>
              }
            />
          )
        ) : items.length === 0 ? (
          <EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="type-small font-medium text-foreground">
                {t("resultsCount", { count: total })}
              </p>
              {source && <SourceIndicator source={source} />}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((match, i) => (
                <TalentResultCard key={`${match.profile_id ?? "anon"}-${i}`} match={match} />
              ))}
            </div>

            {query.hasNextPage && (
              <div className="flex justify-center pt-1">
                <Button
                  variant="secondary"
                  loading={query.isFetchingNextPage}
                  onClick={() => void query.fetchNextPage()}
                >
                  {tc("loadMore")}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
