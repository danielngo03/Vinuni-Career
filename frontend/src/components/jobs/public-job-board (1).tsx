"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  LightbulbFilament,
  MapPin,
  MagnifyingGlass,
  TrendUp,
  SlidersHorizontal,
  WarningCircle,
  WifiSlash,
  Heart,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import {
  Button,
  EmptyState,
  Input,
  Select,
  Sheet,
  Skeleton,
} from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { JobRow } from "./job-row";
import { JobBoardRail } from "./job-board-rail";
import { RecommendationRail } from "@/components/discovery/recommendation-rail";
import {
  ApiError,
  discoveryApi,
  jobsApi,
  locationsApi,
  type CoarseSignalTags,
  type JobSummary,
} from "@/lib/api";

const PAGE_LIMIT = 12;

/**
 * Public job board. Keyword + employment-type + work-mode filters are applied
 * server-side via the public listing contract and reflected in the query key so
 * results refetch on change. The initial keyword is read from the URL (`?q=`)
 * so the homepage search routes here seamlessly. On mobile the filters collapse
 * into a sheet (SCREEN_SPECS §1.1). Stable card grid with loading/empty/error
 * states per UI_QUALITY_BAR.md.
 */
export function PublicJobBoard() {
  const t = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const searchParams = useSearchParams();

  const initialQ = searchParams.get("q") ?? "";
  const initialEmployment = searchParams.get("employment_type") ?? "";
  const initialLocation = searchParams.get("location_type") ?? "";
  const initialProvince = searchParams.get("province_code") ?? "";
  const initialWard = searchParams.get("ward_code") ?? "";

  const authStatus = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);

  const [searchInput, setSearchInput] = useState(initialQ);
  const [search, setSearch] = useState(initialQ);
  const [employment, setEmployment] = useState(initialEmployment);
  const [location, setLocation] = useState(initialLocation);
  const [province, setProvince] = useState(initialProvince);
  const [ward, setWard] = useState(initialWard);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Debounce the keyword so we don't refetch on every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const query = useInfiniteQuery({
    queryKey: ["jobs", "public", search, employment, location, province, ward],
    queryFn: ({ pageParam }) =>
      jobsApi.listPublic({
        cursor: pageParam,
        limit: PAGE_LIMIT,
        q: search || undefined,
        employment_type: employment || undefined,
        location_type: location || undefined,
        province_code: province || undefined,
        ward_code: ward || undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const jobs: JobSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const total = query.data?.pages[0]?.page.total;

  // Job filter config — employment_types + location_types from backend.
  // Chips are hidden until this resolves; no static fallback.
  const configQuery = useQuery({
    queryKey: ["jobs", "config"],
    queryFn: () => jobsApi.getConfig(),
    staleTime: Infinity,
    retry: false,
  });

  // Province chips — only rendered when API data is available; no static fallback.
  const provincesQuery = useQuery({
    queryKey: ["locations", "provinces"],
    queryFn: () => locationsApi.listProvinces(),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const wardsQuery = useQuery({
    queryKey: ["locations", "wards", province],
    queryFn: () => locationsApi.listWards(province),
    enabled: Boolean(province),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const popularProvinces = (() => {
    const items = provincesQuery.data?.items;
    if (!items || items.length === 0) return null; // backend offline → render nothing
    const central = items.filter((p) => p.is_central);
    const others = items.filter((p) => !p.is_central);
    return [...central, ...others].slice(0, 8).map((p) => ({ code: p.code, label: p.name }));
  })();

  // Recommendation rail — honest source label; feeds coarse search signals so
  // guest recommendations improve over time. Hidden when there are no items.
  const recoQuery = useQuery({
    queryKey: ["jobs", "recommendations", search],
    queryFn: () => discoveryApi.recommendations({ q: search || undefined, limit: 6 }),
    retry: false,
  });
  const recoSignals: CoarseSignalTags | undefined = search
    ? { search_terms: [search] }
    : undefined;

  const employmentOptions = configQuery.data
    ? [
        { value: "", label: t("filterAllTypes") },
        ...configQuery.data.employment_types.map((v) => ({
          value: v,
          label: t(`enums.employmentType.${v}`),
        })),
      ]
    : null;

  const locationOptions = configQuery.data
    ? [
        { value: "", label: t("filterAllModes") },
        ...configQuery.data.location_types.map((v) => ({
          value: v,
          label: t(`enums.locationType.${v}`),
        })),
      ]
    : null;

  const provinceOptions = provincesQuery.data
    ? [
        { value: "", label: t("provinceAll") },
        ...provincesQuery.data.items.map((p) => ({
          value: p.code,
          label: p.full_name || p.name,
        })),
      ]
    : null;

  const wardOptions = province
    ? [
        { value: "", label: t("wardAll") },
        ...(wardsQuery.data?.items ?? []).map((w) => ({
          value: w.code,
          label: w.full_name || w.name,
        })),
      ]
    : [{ value: "", label: t("wardSelectProvinceFirst"), disabled: true }];

  const activeFilterCount =
    (employment ? 1 : 0) +
    (location ? 1 : 0) +
    (province ? 1 : 0) +
    (ward ? 1 : 0);
  const hasFilters = Boolean(search || employment || location || province || ward);

  function setProvinceFilter(value: string) {
    setProvince(value);
    setWard("");
  }

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setEmployment("");
    setLocation("");
    setProvince("");
    setWard("");
  }

  return (
    <div className="career-container py-6 lg:py-8">
      <header className="marketplace-card mb-5 overflow-hidden rounded-[20px]">
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="p-5 sm:p-6">
            <p className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
              <Briefcase aria-hidden weight="duotone" className="size-3.5" />
              VinUni Career Marketplace
            </p>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-[2rem] font-extrabold tracking-tight text-[var(--text-primary)] sm:text-[2.55rem]">
                  {t("boardTitle")}
                </h1>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
                  {t("boardSubtitle")}
                </p>
              </div>
              {authStatus === "authenticated" && persona === "student" && (
                <Link
                  href="/student/saved"
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-white px-4 py-2 text-sm font-semibold text-[var(--brand-primary)] shadow-sm transition-colors hover:border-[var(--brand-primary)]/40 hover:bg-[var(--blue-50)]"
                >
                  <Heart aria-hidden weight="duotone" className="size-4" />
                  {t("savedJobsCta")}
                </Link>
              )}
            </div>
          </div>
          <div className="hidden border-l border-[var(--border-default)] bg-[linear-gradient(135deg,var(--blue-50),var(--teal-50))] p-5 lg:flex lg:flex-col lg:justify-end">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
              {hasFilters ? t("clearFilters") : t("aiBoardInsightsTitle")}
            </p>
            <p className="mt-2 text-3xl font-extrabold text-[var(--brand-primary)]">
              {query.isPending ? "..." : new Intl.NumberFormat().format(total ?? jobs.length)}
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {t("resultCount", { count: total ?? jobs.length })}
            </p>
          </div>
        </div>
      </header>

      {/* Filter toolbar — chips on desktop, sheet on mobile. */}
      <div className="marketplace-card sticky top-[76px] z-20 mb-5 space-y-3 rounded-[18px] p-3 shadow-[0_10px_32px_rgba(11,34,57,0.08)]">
        {/* Search row */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <MagnifyingGlass
              aria-hidden
              weight="duotone"
              className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <Input
              type="search"
              aria-label={t("searchLabel")}
              placeholder={t("searchPlaceholder")}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="h-11 rounded-xl border-[var(--border-default)] bg-[var(--surface-secondary)] pl-10 pr-10"
            />
            {searchInput && (
              <button
                type="button"
                aria-label={t("clearFilters")}
                onClick={() => setSearchInput("")}
                className="absolute right-2 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-white hover:text-[var(--text-primary)]"
              >
                <X aria-hidden weight="bold" className="size-3.5" />
              </button>
            )}
          </div>
          {/* Mobile: open filter sheet */}
          <Button
            variant="secondary"
            onClick={() => setFiltersOpen(true)}
            className="lg:hidden"
          >
            <SlidersHorizontal aria-hidden weight="bold" className="size-4" />
            {t("filters")}
            {activeFilterCount > 0 && (
              <span className="ml-1 inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--brand-primary)] px-1.5 text-xs font-bold text-white">
                {activeFilterCount}
              </span>
            )}
          </Button>
          {/* Desktop: clear button */}
          <Button
            variant="ghost"
            onClick={clearFilters}
            disabled={!hasFilters}
            className="hidden h-11 lg:inline-flex"
          >
            {t("clearFilters")}
          </Button>
        </div>

        {/* Desktop: Employment type chips — only render when backend config is loaded */}
        {employmentOptions && (
          <div className="hidden flex-wrap gap-2 lg:flex">
            {employmentOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setEmployment(opt.value)}
                className={cn(
                  "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                  employment === opt.value
                    ? "bg-[var(--brand-primary)] text-white shadow-sm"
                    : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}

        {/* Desktop: Location type chips — only render when backend config is loaded */}
        {locationOptions && (
          <div className="hidden flex-wrap gap-2 lg:flex">
            {locationOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setLocation(opt.value)}
                className={cn(
                  "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                  location === opt.value
                    ? "bg-teal-600 text-white shadow-sm"
                    : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
        {provinceOptions && (
          <div className="hidden grid-cols-2 gap-3 lg:grid">
            <Select
              aria-label={t("filterProvinceLabel")}
              value={province}
              onChange={(e) => setProvinceFilter(e.target.value)}
              options={provinceOptions}
              className="border-[var(--border-default)] bg-[var(--surface-secondary)]"
            />
            <Select
              aria-label={t("filterWardLabel")}
              value={ward}
              onChange={(e) => setWard(e.target.value)}
              options={wardOptions}
              disabled={!province || wardsQuery.isLoading}
              className="border-[var(--border-default)] bg-[var(--surface-secondary)]"
            />
          </div>
        )}
      </div>

      <Sheet
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        title={t("filters")}
        closeLabel={tc("close")}
      >
        <div className="flex flex-col gap-4">
          {employmentOptions && (
            <Select
              label={t("filterTypeLabel")}
              value={employment}
              onChange={(e) => setEmployment(e.target.value)}
              options={employmentOptions}
            />
          )}
          {locationOptions && (
            <Select
              label={t("filterModeLabel")}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              options={locationOptions}
            />
          )}
          {provinceOptions && (
            <Select
              label={t("filterProvinceLabel")}
              value={province}
              onChange={(e) => setProvinceFilter(e.target.value)}
              options={provinceOptions}
            />
          )}
          <Select
            label={t("filterWardLabel")}
            value={ward}
            onChange={(e) => setWard(e.target.value)}
            options={wardOptions}
            disabled={!province || wardsQuery.isLoading}
          />
          <div className="mt-2 flex gap-2">
            <Button
              variant="ghost"
              onClick={clearFilters}
              disabled={!hasFilters}
              className="flex-1"
            >
              {t("clearFilters")}
            </Button>
            <Button
              variant="primary"
              onClick={() => setFiltersOpen(false)}
              className="flex-1"
            >
              {t("applyFilters")}
            </Button>
          </div>
        </div>
      </Sheet>

      {/* Province quick-filter chips — only rendered when provinces API is available */}
      {popularProvinces && (
        <div className="mb-5 flex items-center gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <MapPin aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
          <button
            type="button"
            onClick={() => setProvinceFilter("")}
            className={`inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
              !province
                ? "bg-[var(--brand-primary)] text-white shadow-sm"
                : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t("provinceAll")}
          </button>
          {popularProvinces.map((p) => (
            <button
              key={p.code}
              type="button"
              onClick={() => setProvinceFilter(province === p.code ? "" : p.code)}
              className={`inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
                province === p.code
                  ? "bg-[var(--brand-primary)] text-white shadow-sm"
                  : "border border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {/* Recommendation rail (honest source label; hide if empty). */}
      {recoQuery.data && recoQuery.data.items.length > 0 && (
        <RecommendationRail
          data={recoQuery.data}
          base="search"
          signalTags={recoSignals}
          className="mb-6"
          layout="dense"
        />
      )}

      {/* Two-column layout: job listing + right rail (rail hidden on mobile). */}
      <div className="grid grid-cols-1 gap-7 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 flex-1">
          {/* Result count (stable region) */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium text-[var(--text-secondary)]" role="status">
              {query.isPending
                ? tc("loading")
                : t("resultCount", { count: total ?? jobs.length })}
            </p>
            {hasFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {t("clearFilters")}
              </button>
            )}
          </div>

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
            <div className="career-list-surface divide-y divide-[var(--border-default)]">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="flex min-h-[104px] items-center gap-4 p-4"
                >
                  <Skeleton className="size-10 rounded-xl" />
                  <div className="min-w-0 flex-1">
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="mt-3 h-4 w-1/2" />
                    <Skeleton className="mt-2 h-4 w-2/5" />
                  </div>
                </div>
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={Briefcase}
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
              {/* Market highlights — deterministic public inventory signals, not CV-fit/AI. */}
              {!hasFilters && (() => {
                const now = Date.now();
                const soonCount = jobs.filter((j) => {
                  if (!j.application_deadline) return false;
                  const diff = new Date(j.application_deadline).getTime() - now;
                  return diff > 0 && diff <= 7 * 86_400_000;
                }).length;
                const featuredCount = jobs.filter((j) => j.is_featured).length;
                const remoteCount = jobs.filter((j) => j.location_type === "remote" || j.location_type === "hybrid").length;
                const insights: string[] = [];
                insights.push(t("aiBoardInsightTotal", { count: jobs.length }));
                if (soonCount > 0) insights.push(t("aiBoardInsightSoon", { count: soonCount }));
                if (featuredCount > 0) insights.push(t("aiBoardInsightFeatured", { count: featuredCount }));
                if (remoteCount > 0) insights.push(t("aiBoardInsightRemote", { count: remoteCount }));
                return (
                  <div className={cn(
                    "mb-5 rounded-[16px] border p-4",
                    "marketplace-card border-[var(--border-default)] bg-white",
                  )}>
                    <p className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                      <span className="flex size-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--brand-primary)] to-teal-600 shadow-sm">
                        <TrendUp aria-hidden weight="duotone" className="size-3.5 text-white" />
                      </span>
                      {t("aiBoardInsightsTitle")}
                    </p>
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {insights.map((text, i) => (
                        <li key={i} className="flex items-start gap-2 rounded-xl bg-[var(--surface-secondary)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                          <LightbulbFilament aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0 text-[var(--brand-primary)]" />
                          {text}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}

              <ul className="career-list-surface divide-y divide-[var(--border-default)]">
                {jobs.map((job) => (
                  <li key={job.id}>
                    <JobRow job={job} density="compact" />
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

        {/* Right rail — visible only on large screens */}
        <div className="hidden xl:block">
          <JobBoardRail />
        </div>
      </div>
    </div>
  );
}
