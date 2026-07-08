"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Buildings,
  MagnifyingGlass,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { Button, EmptyState, Input, Select, Skeleton } from "@/components/ui";
import { CompanyCard } from "./company-card";
import { ApiError, companiesApi, type CompanySummary } from "@/lib/api";

const PAGE_LIMIT = 12;

/**
 * Public partner directory. Server-side keyword + industry filtering with
 * cursor "load more" pagination. Industry options accumulate from results that
 * have been seen so the dropdown stays stable while filtering.
 */
export function CompaniesDirectory() {
  const t = useTranslations("companies");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");

  // Deep links from the header mega-menu / gateway arrive with `?q=` and
  // `?industry=` so the directory opens pre-filtered (SCREEN_SPECS §1.1).
  const searchParams = useSearchParams();
  const industryParam = searchParams.get("industry") ?? "";
  const qParam = searchParams.get("q") ?? "";

  const [searchInput, setSearchInput] = useState(qParam);
  const [search, setSearch] = useState(qParam);
  const [industry, setIndustry] = useState(industryParam);
  const [seenIndustries, setSeenIndustries] = useState<string[]>(
    industryParam ? [industryParam] : [],
  );

  // Debounce the keyword so we don't refetch on every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  // Honor industry deep links arriving while already mounted (same-route nav).
  // The selected value is seeded into the dropdown so it renders as active even
  // before any result carrying that industry has been seen.
  useEffect(() => {
    if (!industryParam) return;
    setIndustry(industryParam);
    setSeenIndustries((prev) =>
      prev.includes(industryParam) ? prev : [...prev, industryParam],
    );
  }, [industryParam]);

  const query = useInfiniteQuery({
    queryKey: ["companies", "directory", search, industry],
    queryFn: ({ pageParam }) =>
      companiesApi.list({
        cursor: pageParam,
        limit: PAGE_LIMIT,
        q: search || undefined,
        industry: industry || undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const companies: CompanySummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const total = query.data?.pages[0]?.page.total;

  // Accumulate industries we have ever seen for a stable filter dropdown.
  useEffect(() => {
    setSeenIndustries((prev) => {
      const next = new Set(prev);
      for (const c of companies) if (c.industry) next.add(c.industry);
      return next.size === prev.length ? prev : [...next];
    });
  }, [companies]);

  const industryOptions = useMemo(
    () => [
      { value: "", label: t("allIndustries") },
      ...[...seenIndustries]
        .sort((a, b) => a.localeCompare(b))
        .map((v) => ({ value: v, label: v })),
    ],
    [t, seenIndustries],
  );

  const hasFilters = Boolean(search || industry);

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setIndustry("");
  }

  return (
    <div className="career-container py-8 lg:py-10">
      <header className="marketplace-card mb-5 rounded-[20px] p-5 sm:p-6">
        <p className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
          <Buildings aria-hidden weight="duotone" className="size-3.5" />
          VinUni Partner Network
        </p>
        <h1 className="text-[2rem] font-extrabold tracking-tight text-[var(--text-primary)] sm:text-[2.55rem]">
          {t("title")}
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
          {t("subtitle")}
        </p>
      </header>

      <div className="marketplace-card mb-5 grid grid-cols-1 gap-3 rounded-[18px] p-3 sm:grid-cols-[1fr_260px]">
        <div className="relative">
          <MagnifyingGlass
            aria-hidden
            weight="duotone"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <Input
            type="search"
            aria-label={t("searchLabel")}
            placeholder={t("searchPlaceholder")}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="h-11 rounded-xl bg-[var(--surface-secondary)] pl-9"
          />
        </div>
        <Select
          aria-label={t("filterIndustryLabel")}
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          options={industryOptions}
        />
      </div>

      <p className="mb-4 text-sm text-[var(--text-secondary)]" role="status">
        {query.isPending
          ? tc("loading")
          : t("resultCount", { count: total ?? companies.length })}
      </p>

      {query.isError ? (
        <EmptyState
          kind={
            query.error instanceof ApiError &&
            query.error.code === "NETWORK_ERROR"
              ? "offline"
              : "error"
          }
          icon={
            query.error instanceof ApiError &&
            query.error.code === "NETWORK_ERROR"
              ? WifiSlash
              : WarningCircle
          }
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : query.isPending ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="marketplace-card min-h-[150px] rounded-[14px] p-5"
            >
              <div className="flex items-center gap-3">
                <Skeleton className="size-12 rounded-xl" />
                <div className="flex-1">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="mt-2 h-4 w-1/2" />
                </div>
              </div>
              <Skeleton className="mt-4 h-4 w-1/3" />
              <Skeleton className="mt-2 h-4 w-1/4" />
            </div>
          ))}
        </div>
      ) : companies.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={Buildings}
          title={hasFilters ? t("noMatchTitle") : t("emptyTitle")}
          description={hasFilters ? t("noMatchBody") : t("emptyBody")}
          action={
            hasFilters ? (
              <Button variant="secondary" onClick={clearFilters}>
                {t("clearFilters")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {companies.map((company) => (
              <li key={company.id}>
                <CompanyCard company={company} />
              </li>
            ))}
          </ul>

          {query.hasNextPage && (
            <div className="mt-8 flex justify-center">
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
    </div>
  );
}
