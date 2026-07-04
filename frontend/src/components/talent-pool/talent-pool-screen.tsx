"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  MagnifyingGlass,
  UsersThree,
  WarningCircle,
  MapPin,
  GraduationCap,
  Briefcase,
  ArrowRight,
  Sparkle,
  LightbulbFilament,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, StatusBadge, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, talentPoolApi, type TalentCard } from "@/lib/api";
import { DEGREE_LEVELS, OPEN_TO_WORK_TYPES } from "@/lib/api/profile";
import { useProfileLabels } from "@/lib/profile/labels";
import { CompanyAvatar } from "@/components/companies/company-avatar";

const WORK_TYPE_CHIP_COLORS: Record<string, string> = {
  full_time: "bg-blue-100 text-blue-700",
  internship: "bg-violet-100 text-violet-700",
  part_time: "bg-amber-100 text-amber-700",
  contract: "bg-emerald-100 text-emerald-700",
};

function TalentCardRow({ card }: { card: TalentCard }) {
  const location = [card.location_city, card.location_country]
    .filter(Boolean)
    .join(", ");

  return (
    <Link
      href={`/partner/talent/${card.profile_id}`}
      className="group flex items-start gap-4 rounded-2xl border border-[var(--border-default)] bg-white p-5 outline-none transition-colors hover:border-[var(--brand-primary)]/60 hover:bg-white focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      {/* Avatar */}
      <div className="shrink-0">
        {card.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={card.avatar_url}
            alt=""
            className="h-12 w-12 rounded-full object-cover ring-2 ring-white/60"
          />
        ) : (
          <CompanyAvatar name={card.display_name} size="md" />
        )}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)] transition-colors">
              {card.display_name}
            </p>
            {card.headline && (
              <p className="mt-0.5 text-sm text-[var(--text-secondary)] line-clamp-1">
                {card.headline}
              </p>
            )}
          </div>
          {card.profile_completion >= 70 && (
            <StatusBadge tone="active">{card.profile_completion}%</StatusBadge>
          )}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--text-muted)]">
          {card.major && (
            <span className="flex items-center gap-1">
              <GraduationCap className="h-3.5 w-3.5" />
              {card.major}
              {card.graduation_year ? ` · ${card.graduation_year}` : ""}
            </span>
          )}
          {location && (
            <span className="flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" />
              {location}
            </span>
          )}
        </div>

        {card.open_to_work_type_labels.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {card.open_to_work_type_labels.map((label, i) => {
              const type = card.open_to_work_types[i] ?? "";
              return (
                <span
                  key={type}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    WORK_TYPE_CHIP_COLORS[type] ?? "bg-slate-100 text-slate-600"
                  }`}
                >
                  <Briefcase className="h-3 w-3" />
                  {label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      <ArrowRight
        className="mt-1 h-4 w-4 shrink-0 text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity"
        aria-hidden
      />
    </Link>
  );
}

export function TalentPoolScreen() {
  const t = useTranslations("talentPool");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const labels = useProfileLabels();

  const [keyword, setKeyword] = useState("");
  const [committedKeyword, setCommittedKeyword] = useState("");
  const [committedWorkType, setCommittedWorkType] = useState("");
  const [committedDegreeLevel, setCommittedDegreeLevel] = useState("");

  function applyFilters() {
    setCommittedKeyword(keyword);
  }

  const query = useInfiniteQuery({
    queryKey: ["talent-pool", committedKeyword, committedWorkType, committedDegreeLevel],
    queryFn: ({ pageParam }) =>
      talentPoolApi.search({
        keyword: committedKeyword || undefined,
        open_to_work_type: committedWorkType || undefined,
        degree_level: committedDegreeLevel || undefined,
        cursor: pageParam ?? undefined,
        limit: 20,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const allCards = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Filters */}
      <div className="mb-6 rounded-2xl border border-[var(--border-default)] bg-white p-4 space-y-3">
        {/* Keyword row */}
        <div className="flex gap-3">
          <div className="relative flex-1">
            <MagnifyingGlass
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-muted)]"
              aria-hidden
            />
            <input
              type="search"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyFilters()}
              placeholder={t("searchPlaceholder")}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
          </div>
          <Button variant="primary" onClick={applyFilters}>
            {t("search")}
          </Button>
        </div>

        {/* Work Type chips */}
        <div className="flex flex-wrap gap-2">
          {[{ value: "", label: t("anyWorkType") }, ...OPEN_TO_WORK_TYPES.map((wt) => ({ value: wt, label: labels.openToWork(wt) }))].map(
            (opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setCommittedWorkType(opt.value)}
                className={cn(
                  "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                  committedWorkType === opt.value
                    ? "bg-[var(--brand-primary)] text-white shadow-sm"
                    : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white ",
                )}
              >
                {opt.label}
              </button>
            ),
          )}
        </div>

        {/* Degree Level chips */}
        <div className="flex flex-wrap gap-2">
          {[{ value: "", label: t("anyDegree") }, ...DEGREE_LEVELS.map((d) => ({ value: d, label: labels.degree(d) }))].map(
            (opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setCommittedDegreeLevel(opt.value)}
                className={cn(
                  "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                  committedDegreeLevel === opt.value
                    ? "bg-[var(--brand-primary)] text-white shadow-sm"
                    : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white ",
                )}
              >
                {opt.label}
              </button>
            ),
          )}
        </div>
      </div>

      {/* Results */}
      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl" />
          ))}
        </div>
      ) : query.isError ? (
        query.error instanceof ApiError && query.error.isAuthError ? (
          <EmptyState
            kind="auth"
            icon={UsersThree}
            title={tStates("authTitle")}
            description={tStates("authBody")}
          />
        ) : (
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
        )
      ) : allCards.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={UsersThree}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <div className="space-y-3">
          {/* Result count summary */}
          {query.data?.pages[0]?.page.total !== null && query.data?.pages[0]?.page.total !== undefined && (
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              {t("resultsCount", { count: query.data.pages[0].page.total })}
            </p>
          )}
          {/* AI Talent Discovery Insights */}
          {allCards.length > 0 && (() => {
            const total = query.data?.pages[0]?.page.total ?? allCards.length;
            const highCompletion = allCards.filter((c) => c.profile_completion >= 80).length;
            const insights: string[] = [];
            if (total > 0) insights.push(t("aiInsightPool", { count: total }));
            if (highCompletion > 0) insights.push(t("aiInsightHighCompletion", { count: highCompletion }));
            const hasFilters = committedKeyword || committedWorkType || committedDegreeLevel;
            if (!hasFilters) insights.push(t("aiInsightRefine"));
            return (
              <div className={cn(
                "rounded-2xl border p-4",
                "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
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
          {allCards.map((card) => (
            <TalentCardRow key={card.profile_id} card={card} />
          ))}

          {query.hasNextPage && (
            <div className="flex justify-center pt-2">
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
    </>
  );
}
