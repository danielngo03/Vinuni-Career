"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowSquareOut,
  Briefcase,
  CaretDown,
  CaretRight,
  Check,
  Clock,
  CurrencyCircleDollar,
  FunnelSimple,
  GridFour,
  Heart,
  MapPin,
  MagnifyingGlass,
  MapTrifold,
  Rows,
  Sparkle,
  Star,
  WarningCircle,
  WifiSlash,
  X,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { jobSignalTags } from "@/lib/discovery/signal-tags";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { JobDetailModal } from "@/components/jobs/job-detail-modal";
import { FitScoreRing, FitScoreRingSkeleton } from "@/components/jobs/fit-score-ring";
import { useBatchFitScores } from "@/hooks/use-batch-fit-scores";
import {
  Button,
  EmptyState,
  Input,
  Sheet,
  Skeleton,
  SponsoredLabel,
  StatusBadge,
} from "@/components/ui";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import {
  ApiError,
  jobsApi,
  locationsApi,
  marketplaceApi,
  searchApi,
  type IndustryBranch,
  type IndustryLeaf,
  type IndustryRoot,
  type JobFitScoreEntry,
  type JobStudentFitSummary,
  type JobSummary,
} from "@/lib/api";
import type { Province, Ward } from "@/lib/api/locations";
import { formatRelativeTime } from "@/lib/format";
import {
  formatJobLocationItem,
  formatLocation,
  jobSalaryLabel,
} from "@/lib/jobs/format";
import { industryFilterParamsForSelection } from "@/lib/jobs/industry-filter";
import { useJobLabels } from "@/lib/jobs/labels";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

const LIST_PAGE_SIZE = 10;
const GRID_PAGE_SIZE = 20;

type ViewMode = "list" | "grid";
type SortMode =
  | "relevant"
  | "newest"
  | "featured"
  | "deadline_soon"
  | "salary_high"
  | "salary_low";

const SORT_OPTIONS: { value: SortMode; key: string }[] = [
  { value: "relevant", key: "sortRelevant" },
  { value: "newest", key: "sortNewest" },
  { value: "featured", key: "sortFeatured" },
  { value: "deadline_soon", key: "sortDeadlineSoon" },
  { value: "salary_high", key: "sortSalaryHigh" },
  { value: "salary_low", key: "sortSalaryLow" },
];

const POSTED_OPTIONS = [
  { value: "", key: "postedAny" },
  { value: "7", key: "posted7" },
  { value: "30", key: "posted30" },
] as const;

// Salary slider bounds (VND / month). The right thumb at the ceiling means
// "no upper limit" so we send salary_max = null in that case.
const SALARY_FLOOR = 0;
const SALARY_CEIL = 100_000_000;
const SALARY_STEP = 5_000_000;

const EXPERIENCE_OPTIONS = [
  { value: "", key: "experienceAny", min: null, max: null },
  { value: "0-0", key: "experienceNone", min: 0, max: 0 },
  { value: "0-1", key: "experience0to1", min: 0, max: 1 },
  { value: "1-3", key: "experience1to3", min: 1, max: 3 },
  { value: "3-5", key: "experience3to5", min: 3, max: 5 },
  { value: "5-", key: "experience5plus", min: 5, max: null },
] as const;

function experienceBounds(value: string) {
  return (
    EXPERIENCE_OPTIONS.find((option) => option.value === value) ??
    EXPERIENCE_OPTIONS[0]
  );
}

function compactJobLocation(job: JobSummary) {
  const locations =
    job.locations && job.locations.length > 0
      ? job.locations.map(formatJobLocationItem).filter(Boolean)
      : [formatLocation(job.location_city, job.location_country)];
  if (locations.length <= 1) return locations[0] || "—";
  return `${locations[0]} +${locations.length - 1}`;
}

function ratingText(job: JobSummary) {
  const rating = job.company?.rating;
  if (!rating || rating.overall_avg == null) return null;
  return `${rating.overall_avg.toFixed(1)} (${rating.review_count})`;
}

type IndustryNode = IndustryRoot | IndustryBranch | IndustryLeaf;
type FilterOption = { value: string; label: string; disabled?: boolean };

function industryName(node: IndustryNode, locale: string) {
  return locale === "vi" ? node.name_vi : node.name_en;
}

function flattenIndustryTree(roots: IndustryRoot[]): IndustryNode[] {
  const nodes: IndustryNode[] = [];
  for (const root of roots) {
    nodes.push(root);
    for (const branch of root.children) {
      nodes.push(branch);
      for (const leaf of branch.children) nodes.push(leaf);
    }
  }
  return nodes;
}

function industryMatches(node: IndustryNode, locale: string, term: string) {
  if (!term.trim()) return true;
  const needle = term.trim().toLowerCase();
  return (
    industryName(node, locale).toLowerCase().includes(needle) ||
    node.name_vi.toLowerCase().includes(needle) ||
    node.name_en.toLowerCase().includes(needle) ||
    node.slug.replaceAll("-", " ").toLowerCase().includes(needle)
  );
}

function industrySelectionLabel(
  roots: IndustryRoot[],
  selectedIds: string[],
  locale: string,
  fallback: string,
  countLabel: (count: number) => string,
) {
  if (selectedIds.length === 0) return fallback;
  const nodes = flattenIndustryTree(roots);
  const first = nodes.find((node) => node.id === selectedIds[0]);
  if (selectedIds.length === 1 && first) return industryName(first, locale);
  return countLabel(selectedIds.length);
}

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
  const [locationTypes, setLocationTypes] = useState<string[]>(
    initialLocation ? [initialLocation] : [],
  );
  const [provinceCodes, setProvinceCodes] = useState<string[]>(
    initialProvince ? [initialProvince] : [],
  );
  const [wardCodes, setWardCodes] = useState<string[]>(
    initialWard ? [initialWard] : [],
  );
  const [selectedIndustryIds, setSelectedIndustryIds] = useState<string[]>([]);
  const [activeProvinceCode, setActiveProvinceCode] = useState(initialProvince);
  const [postedWithin, setPostedWithin] = useState("");
  const [salaryMin, setSalaryMin] = useState(SALARY_FLOOR);
  const [salaryMax, setSalaryMax] = useState(SALARY_CEIL);
  const [experienceBand, setExperienceBand] = useState("");
  const [openFilterMenu, setOpenFilterMenu] = useState<
    "industry" | "location" | null
  >(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [sort, setSort] = useState<SortMode>("relevant");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const salaryActive = salaryMin > SALARY_FLOOR || salaryMax < SALARY_CEIL;
  const experience = experienceBounds(experienceBand);
  const pageSize = viewMode === "grid" ? GRID_PAGE_SIZE : LIST_PAGE_SIZE;

  useEffect(() => {
    setPage(1);
  }, [
    search,
    employment,
    locationTypes,
    selectedIndustryIds,
    provinceCodes,
    wardCodes,
    postedWithin,
    salaryMin,
    salaryMax,
    experienceBand,
    viewMode,
    sort,
  ]);

  const industriesQuery = useQuery({
    queryKey: ["industries", "tree"],
    queryFn: async () => (await searchApi.industryTree()) ?? [],
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const industryFilterParams = useMemo(
    () => industryFilterParamsForSelection(industriesQuery.data ?? [], selectedIndustryIds),
    [industriesQuery.data, selectedIndustryIds],
  );

  const query = useQuery({
    queryKey: [
      "jobs",
      "public",
      search,
      employment,
      locationTypes.join(","),
      selectedIndustryIds.join(","),
      provinceCodes.join(","),
      wardCodes.join(","),
      postedWithin,
      salaryMin,
      salaryMax,
      experienceBand,
      sort,
      page,
      pageSize,
    ],
    queryFn: () =>
      jobsApi.listPublic({
        page,
        limit: pageSize,
        q: search || undefined,
        employment_type: employment || undefined,
        location_types: locationTypes.join(",") || undefined,
        ...industryFilterParams,
        province_codes: provinceCodes.join(",") || undefined,
        ward_codes: wardCodes.join(",") || undefined,
        posted_within_days: postedWithin ? Number(postedWithin) : undefined,
        salary_min: salaryMin > SALARY_FLOOR ? salaryMin : null,
        salary_max: salaryMax < SALARY_CEIL ? salaryMax : null,
        experience_min_years: experience.min,
        experience_max_years: experience.max,
        sort,
      }),
    retry: false,
  });

  const jobs: JobSummary[] = query.data?.data ?? [];
  const total = query.data?.page.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  // Batch fit scores — authenticated students only. Fetched async after the
  // job list renders. Silent failure: badge simply does not appear on error.
  const isStudent =
    authStatus === "authenticated" && persona === "student";
  const jobIds = useMemo(() => jobs.map((job) => job.id), [jobs]);
  const { scores: batchFitScores, loading: batchFitLoading } =
    useBatchFitScores(jobIds, isStudent);

  useEffect(() => {
    if (selectedJobId && !jobs.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(null);
    }
  }, [jobs, selectedJobId]);

  const selectedSummary = jobs.find((job) => job.id === selectedJobId) ?? null;
  const selectedFitScore =
    (selectedJobId ? batchFitScores[selectedJobId]?.score ?? null : null) ??
    selectedSummary?.student_fit?.score ??
    null;

  const detailQuery = useQuery({
    queryKey: ["jobs", "public-detail-preview", selectedJobId],
    queryFn: () => jobsApi.getPublic(selectedJobId!),
    enabled: Boolean(selectedJobId),
    retry: false,
    staleTime: 60_000,
  });

  const configQuery = useQuery({
    queryKey: ["jobs", "config"],
    queryFn: () => jobsApi.getConfig(),
    staleTime: Infinity,
    retry: false,
  });

  const provincesQuery = useQuery({
    queryKey: ["locations", "provinces"],
    queryFn: () => locationsApi.listProvinces(),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const wardsQuery = useQuery({
    queryKey: ["locations", "wards", activeProvinceCode],
    queryFn: () => locationsApi.listWards(activeProvinceCode),
    enabled: Boolean(activeProvinceCode),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const overviewQuery = useQuery({
    queryKey: ["marketplace", "overview", "jobs-board"],
    queryFn: () => marketplaceApi.overview(),
    retry: false,
    staleTime: 60_000,
  });

  const employmentOptions = configQuery.data
    ? [
        { value: "", label: t("filterAllTypes") },
        ...configQuery.data.employment_types.map((value) => ({
          value,
          label: t(`enums.employmentType.${value}`),
        })),
      ]
    : null;

  const locationOptions = configQuery.data
    ? [
        { value: "", label: t("filterAllModes") },
        ...configQuery.data.location_types.map((value) => ({
          value,
          label: t(`enums.locationType.${value}`),
        })),
      ]
    : null;

  const provinces = provincesQuery.data?.items ?? [];
  const wards = wardsQuery.data?.items ?? [];
  const industries = industriesQuery.data ?? [];

  const postedOptions = POSTED_OPTIONS.map((option) => ({
    value: option.value,
    label: t(option.key),
  }));
  const experienceOptions = EXPERIENCE_OPTIONS.map((option) => ({
    value: option.value,
    label: t(option.key),
  }));
  const sortOptions = SORT_OPTIONS.map((option) => ({
    value: option.value,
    label: t(option.key),
  }));

  const hasFilters = Boolean(
    search ||
      employment ||
      locationTypes.length > 0 ||
      selectedIndustryIds.length > 0 ||
      provinceCodes.length > 0 ||
      wardCodes.length > 0 ||
      postedWithin ||
      salaryActive ||
      experienceBand,
  );
  const sidebarFilterCount = [
    locationTypes.length > 0,
    Boolean(postedWithin),
    salaryActive,
    Boolean(experienceBand),
  ].filter(Boolean).length;

  const promotedJob =
    overviewQuery.data?.sponsored_jobs?.[0] ??
    overviewQuery.data?.featured_jobs?.[0] ??
    null;

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setEmployment("");
    setLocationTypes([]);
    setSelectedIndustryIds([]);
    setProvinceCodes([]);
    setWardCodes([]);
    setActiveProvinceCode("");
    setPostedWithin("");
    setSalaryMin(SALARY_FLOOR);
    setSalaryMax(SALARY_CEIL);
    setExperienceBand("");
  }

  // Clears only the left-rail facets (work mode / posted / salary / experience);
  // the top-bar search, industry, location, and type stay intact.
  function clearFacets() {
    setLocationTypes([]);
    setPostedWithin("");
    setSalaryMin(SALARY_FLOOR);
    setSalaryMax(SALARY_CEIL);
    setExperienceBand("");
  }

  return (
    <div className="min-h-[calc(100vh-90px)] bg-[var(--surface-page)]">
      <div className="border-b border-[var(--border-default)] bg-[var(--surface-card)]/95">
        <div className="career-container py-4">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.14em] text-[var(--brand-primary)]">
                <Briefcase aria-hidden weight="duotone" className="size-3.5" />
                {t("boardKicker")}
              </p>
              <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--text-primary)]">
                {t("boardTitle")}
              </h1>
            </div>
            {authStatus === "authenticated" && persona === "student" && (
              <Link
                href="/student/saved"
                className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] shadow-sm transition-colors hover:border-[var(--brand-primary)]/50 hover:text-[var(--brand-primary)]"
              >
                <Heart aria-hidden weight="duotone" className="size-4" />
                {t("savedJobsCta")}
              </Link>
            )}
          </div>

        </div>
      </div>

      <div className="career-container py-4">
        <div className="z-20 mb-4 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3 shadow-[0_10px_30px_rgba(11,34,57,0.07)]">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[220px_minmax(340px,1fr)_240px_200px]">
            <IndustryFilter
              industries={industries}
              selectedIds={selectedIndustryIds}
              onSelectedIdsChange={setSelectedIndustryIds}
              open={openFilterMenu === "industry"}
              onOpenChange={(open) => setOpenFilterMenu(open ? "industry" : null)}
            />

            <div className="relative">
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
                onChange={(event) => setSearchInput(event.target.value)}
                className="h-11 rounded-xl bg-[var(--surface-secondary)] pl-10 pr-10"
              />
              {searchInput && (
                <button
                  type="button"
                  aria-label={t("clearSearch")}
                  onClick={() => setSearchInput("")}
                  className="absolute right-2 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-card)] hover:text-[var(--text-primary)]"
                >
                  <X aria-hidden weight="bold" className="size-3.5" />
                </button>
              )}
            </div>

            <LocationFilter
              provinces={provinces}
              wards={wards}
              loadingWards={wardsQuery.isLoading}
              selectedProvinceCodes={provinceCodes}
              selectedWardCodes={wardCodes}
              activeProvinceCode={activeProvinceCode}
              onActiveProvinceChange={setActiveProvinceCode}
              onProvinceCodesChange={setProvinceCodes}
              onWardCodesChange={setWardCodes}
              open={openFilterMenu === "location"}
              onOpenChange={(open) => setOpenFilterMenu(open ? "location" : null)}
              compact
            />
            <TypeFilter
              value={employment}
              options={employmentOptions}
              onChange={setEmployment}
            />
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
          {/* Left facet rail (desktop) */}
          <aside
            className="hidden min-w-0 xl:block"
            aria-label={t("filtersTitle")}
          >
            <div className="sticky top-24">
              {/* Header row — aligned on the same baseline as the results
                  header on the right so the two columns line up. */}
              <div className="mb-3 flex min-h-9 items-center justify-between gap-2">
                <p className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                  <FunnelSimple aria-hidden weight="bold" className="size-4" />
                  {t("filtersTitle")}
                </p>
                <button
                  type="button"
                  onClick={clearFacets}
                  disabled={sidebarFilterCount === 0}
                  className="text-xs font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--text-secondary)] disabled:text-[var(--text-muted)]"
                >
                  {t("clearFilters")}
                </button>
              </div>
              <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_10px_30px_rgba(11,34,57,0.06)]">
                <JobFilterSidebar
                  locationOptions={locationOptions}
                  postedOptions={postedOptions}
                  experienceOptions={experienceOptions}
                  locationTypes={locationTypes}
                  postedWithin={postedWithin}
                  salaryMin={salaryMin}
                  salaryMax={salaryMax}
                  experienceBand={experienceBand}
                  onLocationTypesChange={setLocationTypes}
                  onPostedWithinChange={setPostedWithin}
                  onSalaryChange={(min, max) => {
                    setSalaryMin(min);
                    setSalaryMax(max);
                  }}
                  onExperienceBandChange={setExperienceBand}
                />
              </div>
            </div>
          </aside>

          <section
            className="min-w-0"
            aria-label={t("listRegionLabel")}
          >
            <div className="mb-3 flex min-h-9 flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {/* Mobile facet trigger */}
                <button
                  type="button"
                  onClick={() => setFiltersOpen(true)}
                  className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 text-sm font-semibold text-[var(--text-primary)] shadow-sm transition-colors hover:border-[var(--border-strong)] xl:hidden"
                >
                  <FunnelSimple aria-hidden weight="bold" className="size-4" />
                  {t("openFilters")}
                  {sidebarFilterCount > 0 && (
                    <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--text-primary)] px-1.5 text-xs font-bold text-[var(--surface-card)]">
                      {sidebarFilterCount}
                    </span>
                  )}
                </button>
                <p className="text-sm font-semibold text-[var(--text-primary)]" role="status">
                  {query.isPending
                    ? tc("loading")
                    : t("resultCount", { count: total ?? jobs.length })}
                </p>
              </div>
              <div className="flex shrink-0 items-center justify-end gap-2">
                <SortMenu
                  value={sort}
                  options={sortOptions}
                  onChange={(value) => setSort(value as SortMode)}
                />
                <div className="flex rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] p-1 shadow-sm">
                  <button
                    type="button"
                    aria-label={t("viewList")}
                    aria-pressed={viewMode === "list"}
                    onClick={() => setViewMode("list")}
                    className={cn(
                      "flex size-8 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]",
                      viewMode === "list" && "bg-[var(--text-primary)] text-[var(--surface-card)] hover:text-[var(--surface-card)]",
                    )}
                  >
                    <Rows aria-hidden weight="bold" className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={t("viewGrid")}
                    aria-pressed={viewMode === "grid"}
                    onClick={() => setViewMode("grid")}
                    className={cn(
                      "flex size-8 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]",
                      viewMode === "grid" && "bg-[var(--text-primary)] text-[var(--surface-card)] hover:text-[var(--surface-card)]",
                    )}
                  >
                    <GridFour aria-hidden weight="bold" className="size-4" />
                  </button>
                </div>
              </div>
            </div>

            <div>
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
                <JobListSkeleton />
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
                  <ul
                    className={cn(
                      "grid gap-3",
                      viewMode === "grid"
                        ? "grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
                        : "md:grid-cols-2",
                    )}
                  >
                    {jobs.map((job, index) => (
                      <Fragment key={job.id}>
                        {index === 3 && promotedJob && promotedJob.id !== job.id && (
                          <li className="col-span-full">
                            <PromotedInlineJob job={promotedJob} />
                          </li>
                        )}
                        <li>
                          <TrackedItem
                            surface="search"
                            targetType="job"
                            targetId={job.id}
                            renderId={`jobs-board-${job.id}`}
                            signalTags={jobSignalTags(job, {
                              searchTerms: search ? [search] : undefined,
                            })}
                          >
                            <JobListItem
                              job={job}
                              active={job.id === selectedJobId}
                              onSelect={() => setSelectedJobId(job.id)}
                              mode={viewMode}
                              batchFitScore={batchFitScores[job.id] ?? null}
                              batchFitLoading={batchFitLoading && isStudent}
                            />
                          </TrackedItem>
                        </li>
                      </Fragment>
                    ))}
                  </ul>

                  <PaginationControls
                    page={page}
                    pageCount={pageCount}
                    onPageChange={setPage}
                  />
                </>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* Job detail drawer (replaces the old right-side preview panel) */}
      <JobDetailModal
        open={Boolean(selectedJobId)}
        summary={selectedSummary}
        detail={detailQuery.data}
        loading={detailQuery.isPending && Boolean(selectedJobId)}
        onClose={() => setSelectedJobId(null)}
        fitScore={selectedFitScore}
        isStudent={isStudent}
      />

      {/* Mobile facet sheet */}
      <Sheet
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        side="left"
        title={t("filtersTitle")}
        closeLabel={t("closePreview")}
      >
        <div className="mb-3 flex justify-end">
          <button
            type="button"
            onClick={clearFacets}
            disabled={sidebarFilterCount === 0}
            className="text-xs font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--text-secondary)] disabled:text-[var(--text-muted)]"
          >
            {t("clearFilters")}
          </button>
        </div>
        <JobFilterSidebar
          locationOptions={locationOptions}
          postedOptions={postedOptions}
          experienceOptions={experienceOptions}
          locationTypes={locationTypes}
          postedWithin={postedWithin}
          salaryMin={salaryMin}
          salaryMax={salaryMax}
          experienceBand={experienceBand}
          onLocationTypesChange={setLocationTypes}
          onPostedWithinChange={setPostedWithin}
          onSalaryChange={(min, max) => {
            setSalaryMin(min);
            setSalaryMax(max);
          }}
          onExperienceBandChange={setExperienceBand}
        />
      </Sheet>
    </div>
  );
}

function SortMenu({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const t = useTranslations("jobs");
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={`${t("sortLabel")}: ${selected?.label ?? ""}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "flex h-9 min-w-[170px] cursor-pointer items-center justify-between gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm font-semibold text-[var(--text-primary)] shadow-sm transition-colors hover:border-[var(--border-strong)]",
          open && "border-[var(--text-primary)]",
        )}
      >
        <span className="truncate">{selected?.label}</span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-4 shrink-0 text-[var(--text-muted)] transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+0.4rem)] z-40 w-56 overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-1.5 shadow-[0_18px_45px_rgba(11,34,57,0.14)]">
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]",
                  active && "bg-[var(--text-primary)] font-semibold text-[var(--surface-card)] hover:bg-[var(--text-primary)] hover:text-[var(--surface-card)]",
                )}
              >
                <span>{option.label}</span>
                {active && <Check aria-hidden weight="bold" className="size-4" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TypeFilter({
  value,
  options,
  onChange,
}: {
  value: string;
  options: FilterOption[] | null;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("jobs");
  const [open, setOpen] = useState(false);
  const selected = options?.find((option) => option.value === value) ?? null;
  const label = value && selected ? selected.label : t("filterTypeLabel");

  return (
    <div className="relative">
      <button
        type="button"
        disabled={!options}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-11 w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 text-left text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--border-strong)] disabled:cursor-not-allowed disabled:opacity-60",
          open && "border-[var(--text-primary)] bg-[var(--surface-card)]",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          <Briefcase aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
          <span className="truncate">{label}</span>
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-4 shrink-0 text-[var(--text-muted)] transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && options && (
        <div className="absolute right-0 top-[calc(100%+0.4rem)] z-40 w-full min-w-[200px] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-1.5 shadow-[0_18px_45px_rgba(11,34,57,0.14)]">
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value || "all"}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]",
                  active &&
                    "bg-[var(--text-primary)] font-semibold text-[var(--surface-card)] hover:bg-[var(--text-primary)] hover:text-[var(--surface-card)]",
                )}
              >
                <span className="truncate">{option.label}</span>
                {active && <Check aria-hidden weight="bold" className="size-4 shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function JobFilterSidebar({
  locationOptions,
  postedOptions,
  experienceOptions,
  locationTypes,
  postedWithin,
  salaryMin,
  salaryMax,
  experienceBand,
  onLocationTypesChange,
  onPostedWithinChange,
  onSalaryChange,
  onExperienceBandChange,
}: {
  locationOptions: FilterOption[] | null;
  postedOptions: FilterOption[];
  experienceOptions: FilterOption[];
  locationTypes: string[];
  postedWithin: string;
  salaryMin: number;
  salaryMax: number;
  experienceBand: string;
  onLocationTypesChange: (value: string[]) => void;
  onPostedWithinChange: (value: string) => void;
  onSalaryChange: (min: number, max: number) => void;
  onExperienceBandChange: (value: string) => void;
}) {
  const t = useTranslations("jobs");
  // Multi-select work modes: drop the synthetic "all" option; an empty
  // selection already means "any".
  const workModes = (locationOptions ?? []).filter((option) => option.value);

  return (
    <div className="space-y-5">
      {workModes.length > 0 && (
        <CheckboxGroup
          label={t("filterModeLabel")}
          options={workModes}
          values={locationTypes}
          onChange={onLocationTypesChange}
        />
      )}
      <div>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
          {t("salaryFilterLabel")}
        </p>
        <SalaryRangeSlider min={salaryMin} max={salaryMax} onChange={onSalaryChange} />
      </div>
      <FacetGroup
        label={t("experienceFilterLabel")}
        options={experienceOptions}
        value={experienceBand}
        onChange={onExperienceBandChange}
      />
      <FacetGroup
        label={t("postedFilterLabel")}
        options={postedOptions}
        value={postedWithin}
        onChange={onPostedWithinChange}
      />
    </div>
  );
}

function CheckboxGroup({
  label,
  options,
  values,
  onChange,
}: {
  label: string;
  options: FilterOption[];
  values: string[];
  onChange: (values: string[]) => void;
}) {
  function toggle(value: string) {
    onChange(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }

  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </p>
      <div className="space-y-0.5">
        {options.map((option) => {
          const checked = values.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              role="checkbox"
              aria-checked={checked}
              onClick={() => toggle(option.value)}
              className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-[var(--surface-secondary)]"
            >
              <span
                className={cn(
                  "flex size-[18px] shrink-0 items-center justify-center rounded-md border transition-colors",
                  checked
                    ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
                    : "border-[var(--border-strong)] bg-[var(--surface-card)]",
                )}
              >
                {checked && <Check aria-hidden weight="bold" className="size-3" />}
              </span>
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {option.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SalaryRangeSlider({
  min,
  max,
  onChange,
}: {
  min: number;
  max: number;
  onChange: (min: number, max: number) => void;
}) {
  const t = useTranslations("jobs");
  const span = SALARY_CEIL - SALARY_FLOOR;
  const pct = (value: number) => ((value - SALARY_FLOOR) / span) * 100;
  const million = (value: number) => t("salaryMillion", { value: Math.round(value / 1_000_000) });
  const thumb =
    "pointer-events-none absolute inset-0 h-5 w-full appearance-none bg-transparent " +
    "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:size-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[var(--text-primary)] [&::-webkit-slider-thumb]:bg-[var(--surface-card)] [&::-webkit-slider-thumb]:shadow-sm " +
    "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:size-4 [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[var(--text-primary)] [&::-moz-range-thumb]:bg-[var(--surface-card)] [&::-moz-range-track]:bg-transparent";

  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-xs font-semibold text-[var(--text-primary)]">
        <span>{min <= SALARY_FLOOR ? t("salaryAny") : million(min)}</span>
        <span>{max >= SALARY_CEIL ? t("salaryNoLimit") : million(max)}</span>
      </div>
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[var(--surface-secondary)]" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-[var(--text-primary)]"
          style={{ left: `${pct(min)}%`, right: `${100 - pct(max)}%` }}
        />
        <input
          type="range"
          aria-label={`${t("salaryFilterLabel")} (min)`}
          min={SALARY_FLOOR}
          max={SALARY_CEIL}
          step={SALARY_STEP}
          value={min}
          onChange={(event) =>
            onChange(Math.min(Number(event.target.value), max - SALARY_STEP), max)
          }
          className={thumb}
        />
        <input
          type="range"
          aria-label={`${t("salaryFilterLabel")} (max)`}
          min={SALARY_FLOOR}
          max={SALARY_CEIL}
          step={SALARY_STEP}
          value={max}
          onChange={(event) =>
            onChange(min, Math.max(Number(event.target.value), min + SALARY_STEP))
          }
          className={thumb}
        />
      </div>
    </div>
  );
}

function FacetGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: FilterOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value || "all"}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={cn(
                "cursor-pointer rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                active
                  ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
                  : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function IndustryFilter({
  industries,
  selectedIds,
  onSelectedIdsChange,
  open,
  onOpenChange,
}: {
  industries: IndustryRoot[];
  selectedIds: string[];
  onSelectedIdsChange: (value: string[]) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const [query, setQuery] = useState("");
  const [activeRootId, setActiveRootId] = useState("");
  const [activeBranchId, setActiveBranchId] = useState("");

  const selected = new Set(selectedIds);
  const filteredRoots = industries.filter((root) => {
    if (industryMatches(root, locale, query)) return true;
    return root.children.some((branch) => {
      if (industryMatches(branch, locale, query)) return true;
      return branch.children.some((leaf) => industryMatches(leaf, locale, query));
    });
  });
  const activeRoot = industries.find((root) => root.id === activeRootId) ?? null;
  const branches = activeRoot
    ? activeRoot.children.filter((branch) => {
        if (industryMatches(branch, locale, query)) return true;
        return branch.children.some((leaf) => industryMatches(leaf, locale, query));
      })
    : [];
  const activeBranch =
    branches.find((branch) => branch.id === activeBranchId) ?? null;
  const leaves = activeBranch
    ? activeBranch.children.filter((leaf) => industryMatches(leaf, locale, query))
    : [];
  const panelStage = activeBranch ? "leaf" : activeRoot ? "branch" : "root";
  const label = industrySelectionLabel(
    industries,
    selectedIds,
    locale,
    t("industryFilterLabel"),
    (count) => t("industryFilterSelected", { count }),
  );

  function toggle(id: string) {
    onSelectedIdsChange(selected.has(id) ? [] : [id]);
  }

  function clearIndustry() {
    onSelectedIdsChange([]);
  }

  function nodeButton(
    node: IndustryNode,
    options?: {
      active?: boolean;
      onActivate?: () => void;
      showArrow?: boolean;
      muted?: boolean;
    },
  ) {
    const checked = selected.has(node.id);
    return (
      <button
        key={node.id}
        type="button"
        onMouseEnter={options?.onActivate}
        onFocus={options?.onActivate}
        onClick={() => {
          options?.onActivate?.();
          toggle(node.id);
        }}
        className={cn(
          "flex w-full cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors hover:bg-[var(--surface-secondary)]",
          options?.active && "bg-[var(--surface-secondary)]",
          checked && "bg-[var(--surface-secondary)] text-[var(--text-primary)]",
          options?.muted && "opacity-60",
        )}
      >
        <span
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded-md border",
            checked
              ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
              : "border-[var(--border-default)] bg-[var(--surface-card)]",
          )}
        >
          {checked && <Check aria-hidden weight="bold" className="size-3.5" />}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--text-primary)]">
          {industryName(node, locale)}
        </span>
        {options?.showArrow && (
          <CaretRight
            aria-hidden
            weight="bold"
            className="size-4 shrink-0 text-[var(--text-muted)]"
          />
        )}
      </button>
    );
  }

  const panel = (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_24px_70px_rgba(11,34,57,0.16)]",
        panelStage === "root" && "w-[min(420px,calc(100vw-2rem))]",
        panelStage === "branch" && "w-[min(720px,calc(100vw-2rem))]",
        panelStage === "leaf" && "w-[min(980px,calc(100vw-2rem))]",
      )}
    >
      <div className="border-b border-[var(--border-default)] p-4">
        <div className="relative">
          <MagnifyingGlass
            aria-hidden
            weight="duotone"
            className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("industrySearchPlaceholder")}
            className="h-11 w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] pl-10 pr-3 text-sm font-semibold outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--text-primary)]"
          />
        </div>
      </div>
      <div
        className={cn(
          "grid min-h-[360px]",
          panelStage === "root" && "md:grid-cols-1",
          panelStage === "branch" && "md:grid-cols-2",
          panelStage === "leaf" && "md:grid-cols-[1fr_1fr_1.15fr]",
        )}
      >
        <div
          className={cn(
            "border-b border-[var(--border-default)] p-4 md:border-b-0",
            panelStage !== "root" && "md:border-r",
          )}
        >
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("industryRootLabel")}
          </p>
          <div className="max-h-[285px] space-y-1 overflow-y-auto pr-1">
            {filteredRoots.map((root) =>
              nodeButton(root, {
                active: activeRoot?.id === root.id,
                showArrow: root.children.length > 0,
                onActivate: () => {
                  setActiveRootId(root.id);
                  setActiveBranchId("");
                },
              }),
            )}
          </div>
        </div>
        {activeRoot && (
          <div className="border-b border-[var(--border-default)] p-4 md:border-b-0 md:border-r">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("industryBranchLabel")}
            </p>
            <div className="max-h-[285px] space-y-1 overflow-y-auto pr-1">
              {branches.length > 0 ? (
                branches.map((branch) =>
                  nodeButton(branch, {
                    active: activeBranch?.id === branch.id,
                    showArrow: branch.children.length > 0,
                    onActivate: () => setActiveBranchId(branch.id),
                  }),
                )
              ) : (
                <p className="rounded-2xl bg-[var(--surface-secondary)] p-4 text-sm font-medium text-[var(--text-muted)]">
                  {t("chooseIndustryRootFirst")}
                </p>
              )}
            </div>
          </div>
        )}
        {activeBranch && (
          <div className="p-4">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("industryLeafLabel")}
            </p>
            <div className="max-h-[285px] space-y-1 overflow-y-auto pr-1">
              {leaves.length > 0 ? (
                leaves.map((leaf) => nodeButton(leaf))
              ) : (
                <div className="flex h-52 flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] text-center">
                  <Briefcase
                    aria-hidden
                    weight="duotone"
                    className="size-10 text-[var(--text-muted)]"
                  />
                  <p className="mt-3 text-sm font-medium text-[var(--text-secondary)]">
                    {t("chooseIndustryBranchFirst")}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3">
        <button
          type="button"
          onClick={clearIndustry}
          disabled={selectedIds.length === 0}
          className="cursor-pointer text-sm font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--text-secondary)] disabled:text-[var(--text-muted)]"
        >
          {t("clearIndustry")}
        </button>
        <Button variant="primary" onClick={() => onOpenChange(false)}>
          {t("applyFilters")}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className={cn(
          "flex h-11 w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 text-left text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--border-strong)]",
          open && "border-[var(--text-primary)] bg-[var(--surface-card)]",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          <Briefcase
            aria-hidden
            weight="duotone"
            className="size-4 shrink-0 text-[var(--text-muted)]"
          />
          <span className="truncate">{label}</span>
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className="size-4 shrink-0 text-[var(--text-muted)]"
        />
      </button>
      {open && (
        <div className="absolute left-0 top-[calc(100%+0.5rem)] z-40">
          {panel}
        </div>
      )}
    </div>
  );
}

function LocationFilter({
  provinces,
  wards,
  loadingWards,
  selectedProvinceCodes,
  selectedWardCodes,
  activeProvinceCode,
  onActiveProvinceChange,
  onProvinceCodesChange,
  onWardCodesChange,
  open,
  onOpenChange,
  compact,
}: {
  provinces: Province[];
  wards: Ward[];
  loadingWards: boolean;
  selectedProvinceCodes: string[];
  selectedWardCodes: string[];
  activeProvinceCode: string;
  onActiveProvinceChange: (value: string) => void;
  onProvinceCodesChange: (value: string[]) => void;
  onWardCodesChange: (value: string[]) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  compact: boolean;
}) {
  const t = useTranslations("jobs");
  const [provinceSearch, setProvinceSearch] = useState("");
  const [wardSearch, setWardSearch] = useState("");

  const filteredProvinces = provinces.filter((item) =>
    (item.full_name || item.name).toLowerCase().includes(provinceSearch.toLowerCase()),
  );
  const filteredWards = wards.filter((item) =>
    (item.full_name || item.name).toLowerCase().includes(wardSearch.toLowerCase()),
  );
  const activeProvince = provinces.find((item) => item.code === activeProvinceCode);
  const selectedCount = selectedProvinceCodes.length + selectedWardCodes.length;
  const label =
    selectedCount === 0
      ? t("locationFilterLabel")
      : t("locationFilterSelected", { count: selectedCount });

  function toggleProvince(code: string) {
    const exists = selectedProvinceCodes.includes(code);
    onProvinceCodesChange(
      exists
        ? selectedProvinceCodes.filter((item) => item !== code)
        : [...selectedProvinceCodes, code],
    );
    onActiveProvinceChange(code);
  }

  function toggleWard(code: string) {
    const exists = selectedWardCodes.includes(code);
    onWardCodesChange(
      exists
        ? selectedWardCodes.filter((item) => item !== code)
        : [...selectedWardCodes, code],
    );
  }

  function clearLocation() {
    onProvinceCodesChange([]);
    onWardCodesChange([]);
    onActiveProvinceChange("");
  }

  const panel = (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_24px_70px_rgba(11,34,57,0.16)]",
        compact ? "w-[min(760px,calc(100vw-2rem))]" : "w-full shadow-none",
      )}
    >
      <div className="grid min-h-[360px] md:grid-cols-2">
        <div className="border-b border-[var(--border-default)] p-4 md:border-b-0 md:border-r">
          <div className="relative">
            <MagnifyingGlass
              aria-hidden
              weight="duotone"
              className="pointer-events-none absolute left-0 top-1/2 size-5 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              value={provinceSearch}
              onChange={(event) => setProvinceSearch(event.target.value)}
              placeholder={t("provinceSearchPlaceholder")}
              className="h-11 w-full border-b border-[var(--border-default)] bg-transparent pl-8 text-sm font-semibold outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--text-primary)]"
            />
          </div>
          <div className="mt-4 max-h-[285px] space-y-1 overflow-y-auto pr-1">
            {filteredProvinces.map((item) => {
              const selected = selectedProvinceCodes.includes(item.code);
              const active = activeProvinceCode === item.code;
              return (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => toggleProvince(item.code)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors hover:bg-[var(--surface-secondary)]",
                    active && "bg-[var(--surface-secondary)]",
                    selected && "bg-[var(--surface-secondary)] text-[var(--text-primary)]",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-5 shrink-0 items-center justify-center rounded-md border",
                      selected
                        ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
                        : "border-[var(--border-default)] bg-[var(--surface-card)]",
                    )}
                  >
                    {selected && <Check aria-hidden weight="bold" className="size-3.5" />}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--text-primary)]">
                    {item.full_name || item.name}
                  </span>
                  <CaretRight
                    aria-hidden
                    weight="bold"
                    className="size-4 shrink-0 text-[var(--text-muted)]"
                  />
                </button>
              );
            })}
          </div>
        </div>

        <div className="p-4">
          <div className="relative">
            <MagnifyingGlass
              aria-hidden
              weight="duotone"
              className="pointer-events-none absolute left-0 top-1/2 size-5 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              value={wardSearch}
              onChange={(event) => setWardSearch(event.target.value)}
              placeholder={t("wardSearchPlaceholder")}
              className="h-11 w-full border-b border-[var(--border-default)] bg-transparent pl-8 text-sm font-semibold outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--text-primary)]"
            />
          </div>
          <div className="mt-4 max-h-[285px] space-y-1 overflow-y-auto pr-1">
            {!activeProvinceCode ? (
              <div className="flex h-52 flex-col items-center justify-center rounded-2xl bg-[var(--surface-secondary)] text-center">
                <MapTrifold aria-hidden weight="duotone" className="size-10 text-[var(--text-muted)]" />
                <p className="mt-3 text-sm font-semibold text-[var(--text-secondary)]">
                  {t("chooseProvinceFirst")}
                </p>
              </div>
            ) : loadingWards ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, index) => (
                  <Skeleton key={index} className="h-10 rounded-xl" />
                ))}
              </div>
            ) : (
              <>
                {activeProvince && (
                  <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    {activeProvince.full_name || activeProvince.name}
                  </p>
                )}
                {filteredWards.map((item) => {
                  const selected = selectedWardCodes.includes(item.code);
                  return (
                    <button
                      key={item.code}
                      type="button"
                      onClick={() => toggleWard(item.code)}
                      className={cn(
                        "flex w-full cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors hover:bg-[var(--surface-secondary)]",
                        selected && "bg-[var(--surface-secondary)] text-[var(--text-primary)]",
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-md border",
                          selected
                            ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
                            : "border-[var(--border-default)] bg-[var(--surface-card)]",
                        )}
                      >
                        {selected && <Check aria-hidden weight="bold" className="size-3.5" />}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--text-primary)]">
                        {item.full_name || item.name}
                      </span>
                    </button>
                  );
                })}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3">
        <button
          type="button"
          onClick={clearLocation}
          className="cursor-pointer text-sm font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--text-secondary)] disabled:text-[var(--text-muted)]"
          disabled={selectedCount === 0}
        >
          {t("clearLocation")}
        </button>
        <Button variant="primary" onClick={() => onOpenChange(false)}>
          {t("applyFilters")}
        </Button>
      </div>
    </div>
  );

  if (!compact) return panel;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className={cn(
          "flex h-11 w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 text-left text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--border-strong)]",
          open && "border-[var(--text-primary)] bg-[var(--surface-card)]",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          <MapPin aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
          <span className="truncate">{label}</span>
        </span>
        <CaretDown aria-hidden weight="bold" className="size-4 shrink-0 text-[var(--text-muted)]" />
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] z-40">
          {panel}
        </div>
      )}
    </div>
  );
}

function JobListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 7 }).map((_, index) => (
        <div
          key={index}
          className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4"
        >
          <div className="flex gap-3">
            <Skeleton className="size-12 rounded-xl" />
            <div className="min-w-0 flex-1">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="mt-3 h-4 w-1/2" />
              <Skeleton className="mt-3 h-4 w-2/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PaginationControls({
  page,
  pageCount,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  const t = useTranslations("jobs");
  if (pageCount <= 1) return null;
  const pages = Array.from({ length: Math.min(5, pageCount) }, (_, index) => {
    const start = Math.min(Math.max(page - 2, 1), Math.max(pageCount - 4, 1));
    return start + index;
  });

  return (
    <nav className="mt-6 flex flex-wrap items-center justify-center gap-2" aria-label={t("paginationLabel")}>
      <Button
        variant="secondary"
        disabled={page <= 1}
        onClick={() => onPageChange(Math.max(1, page - 1))}
      >
        {t("paginationPrev")}
      </Button>
      {pages.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onPageChange(item)}
          className={cn(
            "flex size-9 items-center justify-center rounded-full border text-sm font-semibold transition-colors",
            item === page
              ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
              : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]",
          )}
        >
          {item}
        </button>
      ))}
      <Button
        variant="secondary"
        disabled={page >= pageCount}
        onClick={() => onPageChange(Math.min(pageCount, page + 1))}
      >
        {t("paginationNext")}
      </Button>
    </nav>
  );
}

function fitToneClass(score: number | null | undefined) {
  if (score == null) return "border-[var(--border-default)] text-[var(--text-secondary)]";
  if (score >= 80) return "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]";
  if (score >= 65) return "border-[var(--border-strong)] text-[var(--text-primary)]";
  if (score >= 50) return "border-[var(--border-default)] text-[var(--text-primary)]";
  return "border-[var(--border-default)] text-[var(--text-secondary)]";
}

function JobFitDropdown({
  fit,
  mode,
}: {
  fit: JobStudentFitSummary | null | undefined;
  mode: ViewMode;
}) {
  const t = useTranslations("jobs");
  const [open, setOpen] = useState(false);

  if (!fit) return null;

  const hasScore = typeof fit.score === "number";
  const title = hasScore ? t("fitScoreShort", { score: fit.score }) : t("fitNoCvShort");
  const recommendedTitle = fit.recommended_cv_title;

  return (
    <div className="relative mt-3">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className={cn(
          "inline-flex max-w-full cursor-pointer items-center gap-1.5 rounded-full border bg-[var(--surface-card)] px-2.5 py-1.5 text-left text-xs font-bold transition-colors hover:border-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-primary)]/15",
          fitToneClass(fit.score),
          mode === "grid" && "px-2 py-1 text-[11px]",
        )}
        aria-expanded={open}
      >
        <Sparkle aria-hidden weight="duotone" className="size-3.5 shrink-0" />
        <span className="truncate">{title}</span>
        {recommendedTitle && mode === "list" && (
          <span className="hidden max-w-[180px] truncate font-semibold text-current/70 md:inline">
            {t("fitCvPrefix")}: {recommendedTitle}
          </span>
        )}
        {fit.cv_scores.length > 0 && (
          <CaretDown aria-hidden weight="bold" className="size-3 shrink-0 opacity-70" />
        )}
      </button>

      {open && fit.cv_scores.length > 0 && (
        <div
          className={cn(
            "absolute left-0 top-[calc(100%+0.45rem)] z-30 w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_22px_60px_rgba(11,34,57,0.16)]",
            mode === "grid" && "w-[min(320px,calc(100vw-2rem))]",
          )}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-[var(--border-default)] px-3.5 py-3">
            <p className="text-sm font-bold text-[var(--text-primary)]">
              {t("fitCvScoresTitle")}
            </p>
            {fit.signal === "low_signal" && (
              <span className="text-[11px] font-semibold text-[var(--text-muted)]">
                {t("fitLowSignal")}
              </span>
            )}
          </div>
          <div className="max-h-72 overflow-y-auto p-2">
            {fit.cv_scores.map((cv) => (
              <div
                key={cv.cv_id}
                className={cn(
                  "rounded-xl px-3 py-2.5 transition-colors",
                  cv.recommended
                    ? "bg-[var(--surface-secondary)]"
                    : "hover:bg-[var(--surface-secondary)]",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-[var(--text-primary)]">
                      {cv.title}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-semibold text-[var(--text-muted)]">
                      {cv.recommended && (
                        <span className="inline-flex items-center gap-1 text-[var(--text-primary)]">
                          <Check aria-hidden weight="bold" className="size-3" />
                          {t("fitRecommended")}
                        </span>
                      )}
                      {cv.gap_count > 0 && (
                        <span>{t("fitGapCount", { count: cv.gap_count })}</span>
                      )}
                      {cv.stale && <span>{t("fitStaleCv")}</span>}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-1 text-xs font-bold text-[var(--text-primary)]">
                    {cv.score}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function JobListItem({
  job,
  active,
  onSelect,
  mode,
  batchFitScore,
  batchFitLoading,
}: {
  job: JobSummary;
  active: boolean;
  onSelect: () => void;
  mode: ViewMode;
  batchFitScore?: JobFitScoreEntry | null;
  batchFitLoading?: boolean;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const salary = jobSalaryLabel(job, locale) ?? t("salaryUndisclosed");
  const posted = formatRelativeTime(job.published_at, locale);
  const rating = ratingText(job);

  // Fit score for the per-card ring. Prefer the embedded student_fit summary
  // (which also drives the breakdown dropdown); otherwise use the async batch
  // score. `null` = no eligible fit, so no ring is drawn.
  const ringScore =
    typeof job.student_fit?.score === "number"
      ? job.student_fit.score
      : typeof batchFitScore?.score === "number"
        ? batchFitScore.score
        : null;
  const ringSize = mode === "grid" ? "sm" : "md";
  // Only show a loading ring when we have no embedded fit and the batch call
  // is still in flight for this authenticated student.
  const showRingSkeleton =
    ringScore === null && !job.student_fit && Boolean(batchFitLoading);
  const hasCornerDisclosure = job.is_sponsored || job.is_featured;

  return (
    <div
      onClick={onSelect}
      className={cn(
        "group relative cursor-pointer rounded-2xl border bg-[var(--surface-card)] shadow-sm transition-colors",
        mode === "grid" ? "h-full p-3" : "p-4",
        active
          ? "border-[var(--brand-primary)] shadow-[0_16px_42px_rgba(11,34,57,0.12)]"
          : "border-[var(--border-default)] hover:border-[var(--border-strong)]",
      )}
    >
      {/* Sponsored / featured disclosure — absolutely positioned so it never
          adds layout height. Every card's title therefore starts at the same
          vertical position and sponsored + organic cards are equal height.
          Pinned to the top-left corner, clear of the ring/save/open actions.
          The amber sponsored label is non-removable (CLAUDE.md / ads policy). */}
      {hasCornerDisclosure && (
        <div
          onClick={(event) => event.stopPropagation()}
          className="pointer-events-none absolute left-3 top-0 z-20 flex -translate-y-1/2 items-center gap-1.5"
        >
          {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
          {job.is_featured && (
            <StatusBadge tone="featured" className="shadow-sm">
              <Star aria-hidden weight="fill" className="size-3" />
              {t("featured")}
            </StatusBadge>
          )}
        </div>
      )}

      <div className={cn("flex items-start", mode === "grid" ? "gap-2.5" : "gap-3")}>
        <CompanyAvatar
          name={job.company?.display_name ?? job.title}
          logoUrl={job.company?.logo_url}
          size={mode === "grid" ? "sm" : "md"}
        />
        <button
          type="button"
          onClick={onSelect}
          className="min-w-0 flex-1 cursor-pointer text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <span
            className={cn(
              "block line-clamp-2 font-bold leading-snug text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]",
              mode === "grid" ? "text-sm" : "text-base",
            )}
          >
            {job.title}
          </span>
          {job.company && (
            <span
              className={cn(
                "mt-1 flex min-w-0 flex-wrap items-center gap-1 font-medium text-[var(--text-secondary)]",
                mode === "grid" ? "text-xs" : "text-sm",
              )}
            >
              <span className="truncate">{job.company.display_name}</span>
              {job.company.is_verified && (
                <VerifiedBadge label={t("verified")} className="[&_svg]:size-3.5" />
              )}
              {rating && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-600">
                  <Star aria-hidden weight="fill" className="size-3.5" />
                  {rating}
                </span>
              )}
            </span>
          )}
        </button>
        <div
          onClick={(event) => event.stopPropagation()}
          className={cn("relative z-10 flex shrink-0 items-center", mode === "grid" ? "gap-1.5" : "gap-2")}
        >
          {ringScore !== null ? (
            <FitScoreRing score={ringScore} size={ringSize} />
          ) : showRingSkeleton ? (
            <FitScoreRingSkeleton size={ringSize} />
          ) : null}
          <div className={cn("flex items-center", mode === "grid" ? "gap-1" : "gap-1.5")}>
            <SaveJobButton jobId={job.id} size="sm" initialSaved={job.is_saved ?? false} />
            <Link
              href={`/jobs/${job.id}`}
              aria-label={t("openFullJob")}
              className={cn(
                "flex items-center justify-center rounded-full border border-[var(--border-default)] text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)]/50 hover:text-[var(--brand-primary)]",
                mode === "grid" ? "size-8" : "size-9",
              )}
            >
              <ArrowSquareOut aria-hidden weight="bold" className="size-4" />
            </Link>
          </div>
        </div>
      </div>

      <div
        className={cn(
          "mt-3 flex flex-wrap items-center gap-y-1 font-medium text-[var(--text-muted)]",
          mode === "grid" ? "gap-x-2 text-[11px] leading-5" : "gap-x-3 text-xs",
        )}
      >
        <span>
          {labels.employmentType(job.employment_type, job.employment_type_label)}
          {" · "}
          {labels.locationType(job.location_type, job.location_type_label)}
        </span>
        <span className="flex items-center gap-1">
          <MapPin aria-hidden weight="duotone" className="size-3.5" />
          {compactJobLocation(job)}
        </span>
        <span className="flex items-center gap-1">
          <CurrencyCircleDollar aria-hidden weight="duotone" className="size-3.5" />
          {salary}
        </span>
        {posted && (
          <span className="flex items-center gap-1">
            <Clock aria-hidden weight="duotone" className="size-3.5" />
            {posted}
          </span>
        )}
      </div>

      {/* Breakdown chip for the embedded student_fit summary (recommended CV,
          per-CV scores). The headline score itself now lives in the ring above;
          this stays as the drill-down affordance. */}
      <JobFitDropdown fit={job.student_fit} mode={mode} />
    </div>
  );
}

function PromotedInlineJob({ job }: { job: JobSummary }) {
  const t = useTranslations("jobs");
  return (
    <TrackedItem
      surface="search_sponsored"
      targetType="job"
      targetId={job.id}
      renderId={`jobs-board-promoted-${job.id}`}
      className="mb-3"
    >
      <Link
        href={`/jobs/${job.id}`}
        className="group flex items-center gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-sm outline-none transition-colors hover:border-[var(--border-strong)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-subtle)] text-[var(--text-primary)]">
          <Sparkle aria-hidden weight="duotone" className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
            {t("promotedTitle")}
          </span>
          <span className="mt-1 block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
            {job.title}
          </span>
        </span>
        <ArrowSquareOut
          aria-hidden
          weight="bold"
          className="size-4 shrink-0 text-[var(--text-secondary)]"
        />
      </Link>
    </TrackedItem>
  );
}
