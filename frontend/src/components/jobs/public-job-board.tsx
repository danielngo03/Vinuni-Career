"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowSquareOut,
  Briefcase,
  Buildings,
  CaretDown,
  CaretRight,
  Check,
  Clock,
  CurrencyCircleDollar,
  Heart,
  ListBullets,
  MapPin,
  MagnifyingGlass,
  MapTrifold,
  SlidersHorizontal,
  Sparkle,
  SquaresFour,
  Star,
  WarningCircle,
  WifiSlash,
  X,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { MarketplaceBannerCard } from "@/components/discovery/marketplace-banner-card";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import {
  Button,
  EmptyState,
  Input,
  Select,
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
  type JobSummary,
  type MarketplaceBanner,
  type PublicJobDetail,
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

const SALARY_OPTIONS = [
  { value: "", key: "salaryAny", min: null, max: null },
  { value: "0-10000000", key: "salaryUnder10", min: 0, max: 10_000_000 },
  { value: "10000000-30000000", key: "salary10to30", min: 10_000_000, max: 30_000_000 },
  { value: "30000000-", key: "salary30plus", min: 30_000_000, max: null },
] as const;

const EXPERIENCE_OPTIONS = [
  { value: "", key: "experienceAny", min: null, max: null },
  { value: "0-0", key: "experienceNone", min: 0, max: 0 },
  { value: "0-1", key: "experience0to1", min: 0, max: 1 },
  { value: "1-3", key: "experience1to3", min: 1, max: 3 },
  { value: "3-5", key: "experience3to5", min: 3, max: 5 },
  { value: "5-", key: "experience5plus", min: 5, max: null },
] as const;

function salaryBounds(value: string) {
  return SALARY_OPTIONS.find((option) => option.value === value) ?? SALARY_OPTIONS[0];
}

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
  const [location, setLocation] = useState(initialLocation);
  const [provinceCodes, setProvinceCodes] = useState<string[]>(
    initialProvince ? [initialProvince] : [],
  );
  const [wardCodes, setWardCodes] = useState<string[]>(
    initialWard ? [initialWard] : [],
  );
  const [selectedIndustryIds, setSelectedIndustryIds] = useState<string[]>([]);
  const [activeProvinceCode, setActiveProvinceCode] = useState(initialProvince);
  const [postedWithin, setPostedWithin] = useState("");
  const [salaryBand, setSalaryBand] = useState("");
  const [experienceBand, setExperienceBand] = useState("");
  const [openFilterMenu, setOpenFilterMenu] = useState<
    "industry" | "location" | "advanced" | null
  >(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [sort, setSort] = useState<SortMode>("relevant");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const salary = salaryBounds(salaryBand);
  const experience = experienceBounds(experienceBand);
  const pageSize = viewMode === "grid" ? GRID_PAGE_SIZE : LIST_PAGE_SIZE;

  useEffect(() => {
    setPage(1);
  }, [
    search,
    employment,
    location,
    selectedIndustryIds,
    provinceCodes,
    wardCodes,
    postedWithin,
    salaryBand,
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
      location,
      selectedIndustryIds.join(","),
      provinceCodes.join(","),
      wardCodes.join(","),
      postedWithin,
      salaryBand,
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
        location_type: location || undefined,
        ...industryFilterParams,
        province_codes: provinceCodes.join(",") || undefined,
        ward_codes: wardCodes.join(",") || undefined,
        posted_within_days: postedWithin ? Number(postedWithin) : undefined,
        salary_min: salary.min,
        salary_max: salary.max,
        experience_min_years: experience.min,
        experience_max_years: experience.max,
        sort,
      }),
    retry: false,
  });

  const jobs: JobSummary[] = query.data?.data ?? [];
  const total = query.data?.page.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (selectedJobId && !jobs.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(null);
    }
  }, [jobs, selectedJobId]);

  const selectedSummary = jobs.find((job) => job.id === selectedJobId) ?? null;

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
  const salaryOptions = SALARY_OPTIONS.map((option) => ({
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
      location ||
      selectedIndustryIds.length > 0 ||
      provinceCodes.length > 0 ||
      wardCodes.length > 0 ||
      postedWithin ||
      salaryBand ||
      experienceBand,
  );
  const advancedFilterCount = [
    employment,
    location,
    postedWithin,
    salaryBand,
    experienceBand,
  ].filter(Boolean).length;

  const previewBanners = [
    overviewQuery.data?.hero_campaign,
    overviewQuery.data?.sponsored_banner,
  ].filter(Boolean) as MarketplaceBanner[];
  const promotedJob =
    overviewQuery.data?.sponsored_jobs?.[0] ??
    overviewQuery.data?.featured_jobs?.[0] ??
    null;

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setEmployment("");
    setLocation("");
    setSelectedIndustryIds([]);
    setProvinceCodes([]);
    setWardCodes([]);
    setActiveProvinceCode("");
    setPostedWithin("");
    setSalaryBand("");
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
          <div className="grid gap-3 xl:grid-cols-[220px_minmax(460px,1fr)_240px_auto]">
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
            <div className="flex gap-2">
              <AdvancedFiltersMenu
                open={openFilterMenu === "advanced"}
                onOpenChange={(open) => setOpenFilterMenu(open ? "advanced" : null)}
                advancedFilterCount={advancedFilterCount}
                employmentOptions={employmentOptions}
                locationOptions={locationOptions}
                postedOptions={postedOptions}
                salaryOptions={salaryOptions}
                experienceOptions={experienceOptions}
                employment={employment}
                location={location}
                postedWithin={postedWithin}
                salaryBand={salaryBand}
                experienceBand={experienceBand}
                onEmploymentChange={setEmployment}
                onLocationChange={setLocation}
                onPostedWithinChange={setPostedWithin}
                onSalaryBandChange={setSalaryBand}
                onExperienceBandChange={setExperienceBand}
                onClear={clearFilters}
                hasFilters={hasFilters}
              />
              <Button
                variant="ghost"
                onClick={clearFilters}
                disabled={!hasFilters}
                className="hidden h-11 2xl:inline-flex"
              >
                {t("clearFilters")}
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <section
            className="min-w-0"
            aria-label={t("listRegionLabel")}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]" role="status">
                  {query.isPending
                    ? tc("loading")
                    : t("resultCount", { count: total ?? jobs.length })}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {t("resultHelper")}
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
                    onClick={() => setViewMode("list")}
                    className={cn(
                      "flex size-8 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]",
                      viewMode === "list" && "bg-[var(--text-primary)] text-[var(--surface-card)] hover:text-[var(--surface-card)]",
                    )}
                  >
                    <ListBullets aria-hidden weight="bold" className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={t("viewGrid")}
                    onClick={() => setViewMode("grid")}
                    className={cn(
                      "flex size-8 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]",
                      viewMode === "grid" && "bg-[var(--text-primary)] text-[var(--surface-card)] hover:text-[var(--surface-card)]",
                    )}
                  >
                    <SquaresFour aria-hidden weight="bold" className="size-4" />
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
                      viewMode === "grid" ? "grid gap-3 sm:grid-cols-2" : "space-y-3",
                    )}
                  >
                    {jobs.map((job, index) => (
                      <li key={job.id}>
                        {viewMode === "list" && index === 3 && promotedJob && promotedJob.id !== job.id && (
                          <PromotedInlineJob job={promotedJob} />
                        )}
                        <TrackedItem
                          surface="search"
                          targetType="job"
                          targetId={job.id}
                          renderId={`jobs-board-${job.id}`}
                          signalTags={{
                            search_terms: search ? [search] : undefined,
                            company_ids: [job.org_id],
                            work_mode: job.location_type,
                            city: job.location_city ?? undefined,
                          }}
                        >
                          <JobListItem
                            job={job}
                            active={job.id === selectedJobId}
                            onSelect={() => setSelectedJobId(job.id)}
                            mode={viewMode}
                          />
                        </TrackedItem>
                      </li>
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

          <aside
            className="hidden min-w-0 xl:block"
            aria-label={t("detailPreviewRegionLabel")}
          >
            <div className="sticky top-24 space-y-4">
              {selectedSummary ? (
                <JobPreviewPanel
                  summary={selectedSummary}
                  detail={detailQuery.data}
                  loading={detailQuery.isPending && Boolean(selectedJobId)}
                  onClose={() => setSelectedJobId(null)}
                />
              ) : (
                <PreviewAdStack banners={previewBanners} promotedJob={promotedJob} />
              )}
            </div>
          </aside>
        </div>
      </div>
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

function AdvancedFiltersMenu({
  open,
  onOpenChange,
  advancedFilterCount,
  employmentOptions,
  locationOptions,
  postedOptions,
  salaryOptions,
  experienceOptions,
  employment,
  location,
  postedWithin,
  salaryBand,
  experienceBand,
  onEmploymentChange,
  onLocationChange,
  onPostedWithinChange,
  onSalaryBandChange,
  onExperienceBandChange,
  onClear,
  hasFilters,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  advancedFilterCount: number;
  employmentOptions: FilterOption[] | null;
  locationOptions: FilterOption[] | null;
  postedOptions: FilterOption[];
  salaryOptions: FilterOption[];
  experienceOptions: FilterOption[];
  employment: string;
  location: string;
  postedWithin: string;
  salaryBand: string;
  experienceBand: string;
  onEmploymentChange: (value: string) => void;
  onLocationChange: (value: string) => void;
  onPostedWithinChange: (value: string) => void;
  onSalaryBandChange: (value: string) => void;
  onExperienceBandChange: (value: string) => void;
  onClear: () => void;
  hasFilters: boolean;
}) {
  const t = useTranslations("jobs");

  return (
    <div className="relative">
      <Button
        variant="secondary"
        onClick={() => onOpenChange(!open)}
        className={cn(
          "h-11 whitespace-nowrap",
          open && "border-[var(--text-primary)] bg-[var(--surface-card)]",
        )}
      >
        <SlidersHorizontal aria-hidden weight="bold" className="size-4" />
        <span className="hidden sm:inline">{t("advancedFilters")}</span>
        {advancedFilterCount > 0 && (
          <span className="ml-1 inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--text-primary)] px-1.5 text-xs font-bold text-[var(--surface-card)]">
            {advancedFilterCount}
          </span>
        )}
      </Button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] z-40 w-[min(420px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_24px_70px_rgba(11,34,57,0.16)]">
          <div className="grid gap-4 p-4">
            {employmentOptions && (
              <Select
                label={t("filterTypeLabel")}
                value={employment}
                onChange={(event) => onEmploymentChange(event.target.value)}
                options={employmentOptions}
              />
            )}
            {locationOptions && (
              <Select
                label={t("filterModeLabel")}
                value={location}
                onChange={(event) => onLocationChange(event.target.value)}
                options={locationOptions}
              />
            )}
            <Select
              label={t("postedFilterLabel")}
              value={postedWithin}
              onChange={(event) => onPostedWithinChange(event.target.value)}
              options={postedOptions}
            />
            <Select
              label={t("salaryFilterLabel")}
              value={salaryBand}
              onChange={(event) => onSalaryBandChange(event.target.value)}
              options={salaryOptions}
            />
            <Select
              label={t("experienceFilterLabel")}
              value={experienceBand}
              onChange={(event) => onExperienceBandChange(event.target.value)}
              options={experienceOptions}
            />
          </div>
          <div className="flex items-center justify-between border-t border-[var(--border-default)] px-4 py-3">
            <button
              type="button"
              onClick={onClear}
              disabled={!hasFilters}
              className="cursor-pointer text-sm font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--text-secondary)] disabled:text-[var(--text-muted)]"
            >
              {t("clearFilters")}
            </button>
            <Button variant="primary" onClick={() => onOpenChange(false)}>
              {t("applyFilters")}
            </Button>
          </div>
        </div>
      )}
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

function JobListItem({
  job,
  active,
  onSelect,
  mode,
}: {
  job: JobSummary;
  active: boolean;
  onSelect: () => void;
  mode: ViewMode;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const salary = jobSalaryLabel(job, locale) ?? t("salaryUndisclosed");
  const posted = formatRelativeTime(job.published_at, locale);
  const rating = ratingText(job);

  return (
    <div
      className={cn(
        "group rounded-2xl border bg-[var(--surface-card)] shadow-sm transition-colors",
        mode === "grid" ? "h-full p-3" : "p-4",
        active
          ? "border-[var(--brand-primary)] shadow-[0_16px_42px_rgba(11,34,57,0.12)]"
          : "border-[var(--border-default)] hover:border-[var(--border-strong)]",
      )}
    >
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
          <span className="flex flex-wrap items-center gap-1.5">
            {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
            {job.is_featured && (
              <StatusBadge tone="featured">
                <Star aria-hidden weight="fill" className="size-3" />
                {t("featured")}
              </StatusBadge>
            )}
          </span>
          <span
            className={cn(
              "mt-2 block line-clamp-2 font-bold leading-snug text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]",
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
        <div className={cn("relative z-10 flex shrink-0 items-center", mode === "grid" ? "gap-1" : "gap-1.5")}>
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

function PreviewAdStack({
  banners,
  promotedJob,
}: {
  banners: MarketplaceBanner[];
  promotedJob: JobSummary | null;
}) {
  const t = useTranslations("jobs");
  const slots = banners.slice(0, 2);

  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_18px_50px_rgba(11,34,57,0.08)]">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--brand-primary)]">
          <Sparkle aria-hidden weight="duotone" className="size-5" />
        </span>
        <div>
          <h2 className="text-base font-bold text-[var(--text-primary)]">
            {t("previewAdsTitle")}
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            {t("previewAdsBody")}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {slots.map((banner, index) => (
          <MarketplaceBannerCard
            key={banner.placement_id ?? `banner-${index}`}
            banner={banner}
            variant="hero"
            className="rounded-2xl"
          />
        ))}
        {slots.length < 2 && promotedJob && (
          <Link
            href={`/jobs/${promotedJob.id}`}
            className="group flex items-center gap-4 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 transition-colors hover:border-[var(--border-strong)]"
          >
            <CompanyAvatar
              name={promotedJob.company?.display_name ?? promotedJob.title}
              logoUrl={promotedJob.company?.logo_url}
              size="md"
            />
            <span className="min-w-0 flex-1">
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-[0.1em] text-[var(--text-secondary)]">
                {t("promotedTitle")}
              </span>
              <span className="mt-1 block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                {promotedJob.title}
              </span>
              <span className="mt-1 block truncate text-xs text-[var(--text-muted)]">
                {compactJobLocation(promotedJob)}
              </span>
            </span>
            <ArrowSquareOut aria-hidden weight="bold" className="size-4 text-[var(--text-secondary)]" />
          </Link>
        )}
        {slots.length === 0 && !promotedJob && (
          <div className="rounded-2xl border border-dashed border-[var(--border-default)] bg-[var(--surface-secondary)] p-8 text-center">
            <Briefcase aria-hidden weight="duotone" className="mx-auto size-10 text-[var(--text-muted)]" />
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              {t("previewEmptyTitle")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function JobPreviewPanel({
  summary,
  detail,
  loading,
  onClose,
}: {
  summary: JobSummary | null;
  detail: PublicJobDetail | undefined;
  loading: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const [tab, setTab] = useState<"description" | "requirements" | "benefits" | "reviews" | "locations">("description");

  if (!summary) {
    return (
      <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-8 text-center">
        <Briefcase aria-hidden weight="duotone" className="mx-auto size-10 text-[var(--text-muted)]" />
        <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
          {t("previewEmptyTitle")}
        </p>
      </div>
    );
  }

  const job = detail ?? summary;
  const salary = jobSalaryLabel(job, locale) ?? t("salaryUndisclosed");
  const posted = formatRelativeTime(job.published_at, locale);
  const rating = job.company?.rating;

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_18px_50px_rgba(11,34,57,0.10)]">
      <div className="border-b border-[var(--border-default)] p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
              {job.is_featured && (
                <StatusBadge tone="featured">
                  <Star aria-hidden weight="fill" className="size-3" />
                  {t("featured")}
                </StatusBadge>
              )}
            </div>
            <h2 className="text-2xl font-extrabold leading-tight tracking-tight text-[var(--text-primary)]">
              {job.title}
            </h2>
            {job.company && (
              <div className="mt-3 flex items-center gap-2">
                <CompanyAvatar
                  name={job.company.display_name}
                  logoUrl={job.company.logo_url}
                  size="sm"
                />
                <span className="flex min-w-0 items-center gap-1 text-sm font-semibold text-[var(--text-secondary)]">
                  <span className="truncate">{job.company.display_name}</span>
                  {job.company.is_verified && (
                    <VerifiedBadge label={t("verified")} className="[&_svg]:size-3.5" />
                  )}
                  {rating?.overall_avg != null && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-secondary)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
                      <Star aria-hidden weight="fill" className="size-3.5 text-amber-500" />
                      {rating.overall_avg.toFixed(1)}
                    </span>
                  )}
                </span>
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <SaveJobButton jobId={job.id} size="md" initialSaved={job.is_saved ?? false} />
            <button
              type="button"
              aria-label={t("closePreview")}
              onClick={onClose}
              className="flex size-10 items-center justify-center rounded-full border border-[var(--border-default)] text-[var(--text-muted)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            >
              <X aria-hidden weight="bold" className="size-4" />
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-2 sm:grid-cols-2">
          <PreviewFact icon={MapPin} label={t("location")} value={compactJobLocation(job)} />
          <PreviewFact
            icon={Briefcase}
            label={t("employmentType")}
            value={`${labels.employmentType(job.employment_type, job.employment_type_label)} · ${labels.locationType(job.location_type, job.location_type_label)}`}
          />
          <PreviewFact icon={CurrencyCircleDollar} label={t("salary")} value={salary} />
          <PreviewFact
            icon={Clock}
            label={t("posted")}
            value={posted ?? t("noDeadline")}
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <Link
            href={`/jobs/${job.id}`}
            className="inline-flex h-9 items-center justify-center rounded-full bg-[var(--btn-primary-bg)] px-5 text-sm font-semibold text-[var(--btn-primary-fg)] shadow-[var(--shadow-brand)] transition-colors hover:bg-[var(--btn-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {t("apply")}
          </Link>
          {job.company && (
            <Link
              href={`/companies/${job.company.slug}`}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-full border border-[var(--border-strong)] bg-[var(--surface-card)] px-5 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-subtle)] hover:border-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <Buildings aria-hidden weight="duotone" className="size-4" />
              {t("viewCompany")}
            </Link>
          )}
        </div>
      </div>

      <div className="flex overflow-x-auto border-b border-[var(--border-default)] px-5">
        {(["description", "requirements", "benefits", "reviews", "locations"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={cn(
              "relative px-3 py-3 text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
              tab === value
                ? "text-[var(--text-primary)] after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-[var(--brand-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]",
            )}
          >
            {t(`previewTabs.${value}`)}
          </button>
        ))}
      </div>

      <div className="min-h-[250px] p-6">
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-10/12" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : (
          <>
            {tab === "description" && (
              <PreviewText value={detail?.description ?? t("previewLoadingHint")} />
            )}
            {tab === "requirements" && (
              <div className="space-y-5">
                <PreviewText value={detail?.requirements ?? t("noRequirements")} />
                {job.required_skills.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {job.required_skills.slice(0, 10).map((skill) => (
                      <span
                        key={skill}
                        className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
            {tab === "benefits" && (
              <PreviewText value={detail?.benefits ?? t("noBenefits")} />
            )}
            {tab === "reviews" && (
              <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-4">
                {rating?.overall_avg != null ? (
                  <>
                    <p className="flex items-center gap-2 text-2xl font-extrabold text-[var(--text-primary)]">
                      <Star aria-hidden weight="fill" className="size-5 text-amber-500" />
                      {rating.overall_avg.toFixed(1)}
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      {t("ratingSummary", { count: rating.review_count })}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-[var(--text-secondary)]">
                    {t("noReviews")}
                  </p>
                )}
              </div>
            )}
            {tab === "locations" && (
              <div className="space-y-2">
                {(job.locations.length > 0 ? job.locations : []).map((item, index) => (
                  <div
                    key={`${item.province_code ?? item.city ?? "location"}-${index}`}
                    className="flex items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-3"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-card)] text-[var(--text-secondary)]">
                      <MapTrifold aria-hidden weight="duotone" className="size-4" />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {formatJobLocationItem(item)}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {labels.locationType(item.type, item.type)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function PreviewFact({
  icon: Icon,
  label,
  value,
}: {
  icon: Icon;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl bg-[var(--surface-secondary)] px-3 py-2">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)]">
        <Icon aria-hidden weight="duotone" className="size-3.5" />
        {label}
      </p>
      <p className="mt-1 line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function PreviewText({ value }: { value: string }) {
  return (
    <div className="prose prose-sm max-w-none text-[var(--text-secondary)] prose-p:my-2 prose-li:my-1">
      <p className="whitespace-pre-line leading-7">{value}</p>
    </div>
  );
}
