"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations, useLocale } from "next-intl";
import { MagnifyingGlass, X, Briefcase, MapPin } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { jobsApi } from "@/lib/api";
import { searchApi } from "@/lib/api/search";
import { cn } from "@/lib/utils";
import { SearchMegaPanel } from "./search-mega-panel";
import type { IndustryLeaf } from "@/lib/api/search";

const DEFAULT_POPULAR_KEYWORDS = {
  vi: [
    "Data Analyst",
    "Software Engineer",
    "Business Analyst",
    "AI Engineer",
    "Marketing",
    "Finance",
  ],
  en: [
    "Data Analyst",
    "Software Engineer",
    "Business Analyst",
    "AI Engineer",
    "Marketing",
    "Finance",
  ],
} as const;

export function MarketplaceHero({
  tone = "light",
  variant = "full",
}: {
  tone?: "light" | "dark";
  variant?: "full" | "search";
}) {
  const t = useTranslations("marketplace");
  const tJobs = useTranslations("jobs");
  const locale = useLocale();
  const router = useRouter();

  const [keyword, setKeyword] = useState("");
  const [locationKeyword, setLocationKeyword] = useState("");
  const [employment, setEmployment] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const employmentRef = useRef(employment);
  employmentRef.current = employment;

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setPanelOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPanelOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const navigate = useCallback(
    (q: string) => {
      const query = [q.trim(), locationKeyword.trim()].filter(Boolean).join(" ");
      if (query) searchApi.log(query, locale).catch(() => {});
      const params = new URLSearchParams();
      if (query) params.set("q", query);
      if (employmentRef.current) params.set("employment_type", employmentRef.current);
      setPanelOpen(false);
      const qs = params.toString();
      router.push(qs ? `/jobs?${qs}` : "/jobs");
    },
    [locale, locationKeyword, router],
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      navigate(keyword);
    },
    [keyword, navigate],
  );

  const handleSelectKeyword = useCallback(
    (kw: string) => {
      setKeyword(kw);
      navigate(kw);
    },
    [navigate],
  );

  const handleSelectIndustry = useCallback(
    (leaf: IndustryLeaf) => {
      const name = locale === "vi" ? leaf.name_vi : leaf.name_en;
      setKeyword(name);
      navigate(name);
    },
    [locale, navigate],
  );

  // Personalized trending keywords — session-aware, backend-driven.
  // Returns null when offline or no data; the chip row is hidden entirely.
  const popularQuery = useQuery({
    queryKey: ["search", "popular", locale],
    queryFn: () => searchApi.popular(locale, 8),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const popularKeywords =
    popularQuery.data?.keywords && popularQuery.data.keywords.length > 0
      ? popularQuery.data.keywords
      : DEFAULT_POPULAR_KEYWORDS[locale === "vi" ? "vi" : "en"];

  // Job config — staleTime:Infinity as these are DB enum constants.
  // Shares cache with the job board's config query.
  const configQuery = useQuery({
    queryKey: ["jobs", "config"],
    queryFn: () => jobsApi.getConfig(),
    staleTime: Infinity,
    retry: false,
  });

  const employmentOptions = configQuery.data
    ? [
        { value: "", label: tJobs("filterAllTypes") },
        ...configQuery.data.employment_types.map((v) => ({
          value: v,
          label: tJobs(`enums.employmentType.${v}`),
        })),
      ]
    : null;
  const dark = tone === "dark";

  const searchSurface = (
    <>
      <div ref={wrapperRef} className="relative">
        <form role="search" aria-label={t("searchRegionLabel")} onSubmit={handleSubmit}>
          <div
            className={cn(
              "grid grid-cols-1 items-center gap-2.5 rounded-[14px] border p-2.5 transition-all duration-200 md:grid-cols-[minmax(0,1fr)_minmax(220px,0.66fr)_128px]",
              panelOpen
                ? "border-[var(--brand-primary)]/50 bg-[var(--surface-card)] shadow-[0_0_0_3px_rgba(45,95,166,0.10),0_8px_36px_rgba(11,34,57,0.14)]"
                : "border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_12px_36px_rgba(11,34,57,0.12),0_1px_8px_rgba(11,34,57,0.05)] hover:border-[var(--border-strong)]",
            )}
          >
            <div className="flex min-w-0 items-center rounded-[11px] border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3">
              <MagnifyingGlass
                aria-hidden
                weight="duotone"
                className="size-5 shrink-0 text-[var(--text-muted)]"
              />

              <input
                ref={inputRef}
                type="search"
                aria-label={t("searchLabel")}
                placeholder={t("searchPlaceholder")}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onFocus={() => setPanelOpen(true)}
                autoComplete="off"
                className="mx-3 min-w-0 flex-1 bg-transparent py-3 text-[0.95rem] font-medium text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
              />

              {keyword && (
                <button
                  type="button"
                  aria-label={t("clearKeyword")}
                  onClick={() => {
                    setKeyword("");
                    inputRef.current?.focus();
                  }}
                  className="flex size-6 shrink-0 items-center justify-center rounded-full text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)]"
                >
                  <X aria-hidden weight="bold" className="size-3.5" />
                </button>
              )}
            </div>

            <div className="flex min-w-0 items-center rounded-[11px] border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3">
              <MapPin
                aria-hidden
                weight="duotone"
                className="size-5 shrink-0 text-[var(--text-muted)]"
              />
              <input
                type="search"
                aria-label={tJobs("location")}
                placeholder={tJobs("location")}
                value={locationKeyword}
                onChange={(e) => setLocationKeyword(e.target.value)}
                autoComplete="off"
                className="mx-3 min-w-0 flex-1 bg-transparent py-3 text-[0.95rem] font-medium text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
              />
            </div>

            <button
              type="submit"
              className="flex h-11 shrink-0 items-center justify-center gap-2 rounded-[11px] bg-[var(--brand-primary)] px-5 text-sm font-semibold text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <MagnifyingGlass aria-hidden weight="bold" className="size-4" />
              <span>{t("searchButton")}</span>
            </button>
          </div>
        </form>

        <SearchMegaPanel
          visible={panelOpen}
          onSelectKeyword={handleSelectKeyword}
          onSelectIndustry={handleSelectIndustry}
        />
      </div>

      {/* Secondary row: employment filter + popular keywords (both backend-driven, hidden when offline) */}
      <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-2">
        {/* Employment type as pill select — only rendered once /jobs/config loads */}
        {employmentOptions && (
          <div className="relative flex items-center">
            <Briefcase
              aria-hidden
              weight="duotone"
              className="pointer-events-none absolute left-2.5 z-10 size-3.5 text-[var(--text-muted)]"
            />
            <select
              aria-label={tJobs("filterTypeLabel")}
              value={employment}
              onChange={(e) => setEmployment(e.target.value)}
              className={cn(
                "h-7 cursor-pointer appearance-none rounded-full border pl-7 pr-6 text-xs font-medium outline-none transition-colors focus-visible:ring-1 focus-visible:ring-[var(--brand-primary)]",
                dark
                  ? "border-white/20 bg-white/10 text-white/78 hover:bg-white/16"
                  : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
              )}
              style={{
                backgroundImage:
                  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' fill='none'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2394a3b8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
                backgroundRepeat: "no-repeat",
                backgroundPosition: "right 8px center",
              }}
            >
              {employmentOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        )}

        <span aria-hidden className={cn("select-none", dark ? "text-white/28" : "text-[var(--border-strong)]")}>·</span>
        <span className={cn("text-[0.72rem] font-semibold", dark ? "text-white/58" : "text-[var(--text-muted)]")}>
          {t("popularLabel")}
        </span>
        {popularKeywords.map((kw) => (
          <button
            key={kw}
            type="button"
            onClick={() => navigate(kw)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs font-medium outline-none transition-all focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
              dark
                ? "border-white/18 bg-white/8 text-white/76 hover:bg-white/16 hover:text-white"
                : "border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 text-[var(--text-secondary)] hover:border-[var(--brand-navy)]/25 hover:text-[var(--brand-navy)]",
            )}
          >
            {kw}
          </button>
        ))}
      </div>
    </>
  );

  if (variant === "search") {
    return <div className="relative overflow-visible">{searchSurface}</div>;
  }

  return (
    <div className="relative overflow-visible pb-1">
      {/* Hero headline */}
      <div className="mb-4">
        <h1
          className={cn(
            "text-[2rem] font-black leading-tight tracking-tight sm:text-[2.75rem] lg:text-[3.25rem]",
            dark ? "text-white" : "text-[var(--brand-navy)]",
          )}
        >
          {t.rich("heroHeadline", {
            highlight: (chunks) => (
              <span className={dark ? "text-[var(--blue-300)]" : "text-[var(--brand-primary)]"}>
                {chunks}
              </span>
            ),
          })}
        </h1>
        <p
          className={cn(
            "mt-3 max-w-[560px] text-sm leading-relaxed sm:text-base",
            dark ? "text-[var(--blue-100)]/86" : "text-[var(--text-secondary)]",
          )}
        >
          {t("heroSubtitle")}
        </p>
      </div>

      {searchSurface}
    </div>
  );
}
