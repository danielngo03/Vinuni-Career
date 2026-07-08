"use client";

import { useId } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CaretRight,
  Clock,
  GraduationCap,
  MapPin,
  Sparkle,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Skeleton } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { discoveryApi, jobsApi, marketplaceApi } from "@/lib/api";
import type { JobSummary, RecommendedJob } from "@/lib/api";
import { EMPLOYMENT_TYPES, LOCATION_TYPES } from "@/lib/api";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatJobLocationItem, formatLocation } from "@/lib/jobs/format";
import {
  FooterLink,
  MegaHeading,
  PublicMegaMenuFrame,
  InlineArrow,
  listLinkClass,
  pillLinkClass,
  spotlightCardClass,
  usePublicMegaMenuState,
} from "./public-mega-menu-frame";
import {
  MegaCampaignCard,
  MegaPromoCard,
  jobPromoFrom,
} from "./mega-campaign-card";

const JOB_TYPE_ICONS: Record<string, Icon> = {
  full_time: Briefcase,
  part_time: Clock,
  internship: GraduationCap,
  contract: Sparkle,
};

const ROLE_FAMILY_COPY: Record<
  string,
  { vi: { label: string; term: string }; en: { label: string; term: string } }
> = {
  software_engineering: {
    vi: { label: "Kỹ sư phần mềm", term: "software engineer" },
    en: { label: "Software engineering", term: "software engineer" },
  },
  data_ai: {
    vi: { label: "Dữ liệu & AI", term: "data" },
    en: { label: "Data & AI", term: "data" },
  },
  product: {
    vi: { label: "Sản phẩm", term: "product manager" },
    en: { label: "Product", term: "product manager" },
  },
  design: {
    vi: { label: "Thiết kế", term: "designer" },
    en: { label: "Design", term: "designer" },
  },
  business: {
    vi: { label: "Kinh doanh", term: "business analyst" },
    en: { label: "Business", term: "business analyst" },
  },
};

function roleFamilyCopy(roleFamily: string, locale: string) {
  const copy = ROLE_FAMILY_COPY[roleFamily]?.[locale === "vi" ? "vi" : "en"];
  if (copy) return copy;
  const label = roleFamily.replaceAll("_", " ");
  return { label, term: label };
}

export function JobsMegaMenu({ isActive = false }: { isActive?: boolean }) {
  const t = useTranslations("jobMenu");
  const tNav = useTranslations("nav");
  const tCompanies = useTranslations("companies");
  const locale = useLocale();
  const labels = useJobLabels();
  const menu = usePublicMegaMenuState();

  const recommendationQuery = useQuery({
    queryKey: ["jobs", "mega-recommendations"],
    queryFn: () => discoveryApi.recommendations({ limit: 4 }),
    enabled: menu.hasOpened,
    retry: false,
    staleTime: 45_000,
  });
  const overviewQuery = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    enabled: menu.hasOpened,
    retry: false,
    staleTime: 60_000,
  });
  const configQuery = useQuery({
    queryKey: ["jobs", "config"],
    queryFn: () => jobsApi.getConfig(),
    enabled: menu.hasOpened,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const personalized = Boolean(recommendationQuery.data?.personalized);
  const recommendedJobs = (recommendationQuery.data?.items ?? []).slice(0, 4);
  const fallbackJobs = [
    ...(overviewQuery.data?.featured_jobs ?? []),
    ...(overviewQuery.data?.recent_jobs ?? []),
  ].slice(0, 4);
  const jobs = recommendedJobs.length > 0 ? recommendedJobs : fallbackJobs;
  const employmentTypes = configQuery.data?.employment_types ?? EMPLOYMENT_TYPES;
  const locationTypes = configQuery.data?.location_types ?? LOCATION_TYPES;
  const popularRoles = (overviewQuery.data?.popular_roles ?? []).slice(0, 5);
  const campaign = overviewQuery.data?.sponsored_banner ?? overviewQuery.data?.hero_campaign;
  const promoJob = jobPromoFrom(
    overviewQuery.data?.sponsored_jobs?.[0] ??
      overviewQuery.data?.featured_jobs?.[0] ??
      jobs[0],
  );

  return (
    <PublicMegaMenuFrame
      menu={menu}
      href="/jobs"
      label={tNav("jobs")}
      panelId="jobs-mega-menu"
      panelLabel={t("label")}
      isActive={isActive}
    >
      <div className="grid gap-x-6 gap-y-5 p-5 md:grid-cols-[1.18fr_0.9fr_0.95fr]">
        <section aria-labelledby="mega-jobs-featured">
          <MegaHeading id="mega-jobs-featured">
            {personalized ? t("recommendedJobs") : t("featuredJobs")}
          </MegaHeading>
          <ul className="mt-3 flex flex-col gap-1">
            {(recommendationQuery.isPending || overviewQuery.isPending) && menu.hasOpened
              ? Array.from({ length: 4 }).map((_, i) => (
                  <li key={i} className="flex items-center gap-2.5 px-2 py-2">
                    <Skeleton className="size-9 rounded-lg" />
                    <div className="min-w-0 flex-1">
                      <Skeleton className="h-4 w-44" />
                      <Skeleton className="mt-1.5 h-3 w-28" />
                    </div>
                  </li>
                ))
              : jobs.length > 0
                ? jobs.map((job) => (
                    <JobMegaRow
                      key={job.id}
                      job={job}
                      verifiedLabel={tCompanies("verified")}
                    />
                  ))
                : (
                  <li className="rounded-xl bg-[var(--surface-secondary)] px-3 py-3 text-sm text-[var(--text-muted)]">
                    {t("emptyJobs")}
                  </li>
                )}
          </ul>
          <FooterLink href="/jobs" label={t("viewAllJobs")} />
        </section>

        <section aria-labelledby="mega-jobs-filters">
          <MegaHeading id="mega-jobs-filters">{t("browseByType")}</MegaHeading>
          <ul className="mt-3 flex flex-col gap-0.5">
            {employmentTypes.map((type) => {
              const TypeIcon = JOB_TYPE_ICONS[type] ?? Briefcase;
              return (
                <li key={type}>
                  <Link
                    href={`/jobs?employment_type=${encodeURIComponent(type)}`}
                    className={listLinkClass}
                  >
                    <TypeIcon aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--brand-primary)]" />
                    <span className="truncate">{labels.employmentType(type)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>

          <MegaHeading id="mega-jobs-location" className="mt-5">
            {t("browseByLocation")}
          </MegaHeading>
          <div className="mt-3 flex flex-wrap gap-2">
            {locationTypes.map((type) => (
              <Link
                key={type}
                href={`/jobs?location_type=${encodeURIComponent(type)}`}
                className={pillLinkClass}
              >
                {labels.locationType(type)}
              </Link>
            ))}
          </div>
        </section>

        <section aria-labelledby="mega-jobs-roles">
          <MegaHeading id="mega-jobs-roles">{t("spotlight")}</MegaHeading>
          <MegaCampaignCard banner={campaign} className="mt-3" />
          {!campaign && promoJob && (
            <MegaPromoCard
              {...promoJob}
              eyebrow={t("featuredJobs")}
              surface="mega_jobs_recommended"
              targetType="job"
              renderId="mega-job-promo"
              className="mt-3"
            />
          )}
          <MegaHeading id="mega-jobs-popular" className="mt-5">
            {t("popularRoles")}
          </MegaHeading>
          <ul className="mt-3 flex flex-col gap-1">
            {popularRoles.length > 0
              ? popularRoles.map((role) => {
                  const { label, term } = roleFamilyCopy(role.role_family, locale);
                  return (
                    <li key={role.role_family}>
                      <Link
                        href={`/jobs?q=${encodeURIComponent(term)}`}
                        className="group flex items-center justify-between gap-3 rounded-xl border border-transparent px-2.5 py-2 outline-none transition-colors hover:border-[var(--border-default)] hover:bg-[var(--surface-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                      >
                        <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
                          {label}
                        </span>
                        <span className="shrink-0 rounded-full bg-[var(--surface-secondary)] px-2 py-0.5 text-xs font-semibold text-[var(--text-muted)] group-hover:bg-[var(--surface-card)]">
                          {role.job_count}
                        </span>
                      </Link>
                    </li>
                  );
                })
              : (
                <li>
                  <Link href="/jobs" className={spotlightCardClass}>
                    <span className="flex size-10 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                      <Briefcase aria-hidden weight="duotone" className="size-5 text-white" />
                    </span>
                    <span className="text-sm font-bold text-[var(--text-primary)]">
                      {t("allJobs")}
                    </span>
                    <span className="text-sm text-[var(--text-secondary)]">
                      {t("allJobsBlurb")}
                    </span>
                    <InlineArrow>{t("viewAllJobs")}</InlineArrow>
                  </Link>
                </li>
              )}
          </ul>
        </section>
      </div>
    </PublicMegaMenuFrame>
  );
}

function JobMegaRow({
  job,
  verifiedLabel,
}: {
  job: JobSummary | RecommendedJob;
  verifiedLabel: string;
}) {
  const labels = useJobLabels();
  const renderId = useId();
  const location =
    job.locations && job.locations.length > 0
      ? job.locations.map(formatJobLocationItem).filter(Boolean).join(" · ")
      : formatLocation(job.location_city, job.location_country);

  return (
    <li>
      <TrackedItem
        surface="mega_jobs_recommended"
        targetType="job"
        targetId={job.id}
        renderId={`mega-job-${renderId}`}
        signalTags={{
          search_terms: [job.title],
          company_ids: [job.org_id],
          work_mode: job.location_type,
        }}
      >
        <Link
          href={`/jobs/${job.id}`}
          className="group flex items-start gap-2.5 rounded-xl px-2.5 py-2 outline-none transition-colors hover:bg-[var(--surface-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <CompanyAvatar
            name={job.company?.display_name ?? job.title}
            logoUrl={job.company?.logo_url}
            size="sm"
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
              {job.title}
            </span>
            {job.company && (
              <span className="mt-0.5 flex min-w-0 items-center gap-1 text-xs font-medium text-[var(--text-secondary)]">
                <span className="truncate">{job.company.display_name}</span>
                {job.company.is_verified && (
                  <VerifiedBadge label={verifiedLabel} className="[&_svg]:size-3" />
                )}
              </span>
            )}
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--text-muted)]">
              <span>
                {labels.employmentType(job.employment_type, job.employment_type_label)}
              </span>
              <span className="flex items-center gap-1">
                <MapPin aria-hidden weight="duotone" className="size-3" />
                {location}
              </span>
            </span>
          </span>
          <CaretRight
            aria-hidden
            weight="bold"
            className="mt-1 size-3.5 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
          />
        </Link>
      </TrackedItem>
    </li>
  );
}
