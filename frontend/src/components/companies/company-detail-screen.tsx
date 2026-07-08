"use client";

import { useEffect, useId } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Buildings,
  LightbulbFilament,
  MapPin,
  UsersThree,
  CalendarBlank,
  Globe,
  Briefcase,
  SealCheck,
  Sparkle,
  WarningCircle,
  Star,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { CompanyAvatar } from "./company-avatar";
import { JobRow } from "@/components/jobs/job-row";
import { CompanyReviewsSection } from "@/components/reviews/company-reviews-section";
import { ReportButton } from "@/components/report/report-button";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { companySignalTags } from "@/lib/discovery/signal-tags";
import { ApiError, companiesApi } from "@/lib/api";

type InsightKey =
  | "insightHiringHigh"
  | "insightHiringMid"
  | "insightHiringSingle"
  | "insightRatingHigh"
  | "insightRatingGood"
  | "insightVerified"
  | "insightEstablished"
  | "insightGrowth";

interface Insight {
  key: InsightKey;
  values?: Record<string, string | number>;
}

function deriveCareerInsights(company: {
  active_job_count: number;
  rating: { overall_avg: number | null; review_count: number } | null;
  is_verified: boolean;
  company_size: string | null;
  founded_year: number | null;
}): Insight[] {
  const out: Insight[] = [];
  const { active_job_count, rating, is_verified, company_size, founded_year } = company;

  if (active_job_count >= 5) {
    out.push({ key: "insightHiringHigh", values: { count: active_job_count } });
  } else if (active_job_count >= 2) {
    out.push({ key: "insightHiringMid", values: { count: active_job_count } });
  } else if (active_job_count === 1) {
    out.push({ key: "insightHiringSingle" });
  }

  if (rating?.overall_avg != null && rating.review_count >= 3) {
    const avg = rating.overall_avg.toFixed(1);
    if (rating.overall_avg >= 4.0) {
      out.push({ key: "insightRatingHigh", values: { avg, count: rating.review_count } });
    } else if (rating.overall_avg >= 3.5) {
      out.push({ key: "insightRatingGood", values: { avg, count: rating.review_count } });
    }
  }

  if (is_verified) {
    out.push({ key: "insightVerified" });
  }

  if (out.length < 3) {
    const sizeLower = (company_size ?? "").toLowerCase();
    const isLarge = ["501", "1000", "1001", "5000"].some((s) => sizeLower.startsWith(s));
    const isSmall =
      !isLarge &&
      (sizeLower.startsWith("1-") ||
        sizeLower.startsWith("11-") ||
        sizeLower.startsWith("51-"));
    const recentlyFounded =
      founded_year != null && founded_year >= 2015;

    if (isLarge) {
      out.push({ key: "insightEstablished" });
    } else if (isSmall && recentlyFounded) {
      out.push({ key: "insightGrowth" });
    }
  }

  return out.slice(0, 3);
}

export function CompanyDetailScreen({ slug }: { slug: string }) {
  const t = useTranslations("companies");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const renderId = useId();

  const query = useQuery({
    queryKey: ["companies", "detail", slug],
    queryFn: () => companiesApi.getBySlug(slug),
    retry: false,
  });

  const company = query.data;
  const careerInsights = company ? deriveCareerInsights(company) : [];

  // Record a privacy-safe `view` discovery event once the real company loads,
  // so browsing feeds the coarse-signal ranker (company id + coarse industry).
  useEffect(() => {
    if (!company) return;
    recordDiscoveryEvent({
      event_type: "view",
      source_surface: "company_profile",
      target_type: "company",
      target_id: company.id,
      idempotency_key: `${renderId}:${company.id}:view`,
      signal_tags: companySignalTags(company),
    });
  }, [company, renderId]);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-6">
      <Link
        href="/companies"
        className="mb-6 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowLeft aria-hidden weight="bold" className="size-4" />
        {t("backToDirectory")}
      </Link>

      {query.isError ? (
        query.error instanceof ApiError && query.error.isNotFound ? (
          <EmptyState
            kind="empty"
            icon={Buildings}
            title={t("notFoundTitle")}
            description={t("notFoundBody")}
            action={
              <Link href="/companies">
                <Button variant="secondary">{t("backToDirectory")}</Button>
              </Link>
            }
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
      ) : query.isPending ? (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <Skeleton className="size-16 rounded-2xl" />
            <div className="flex-1">
              <Skeleton className="h-7 w-1/2" />
              <Skeleton className="mt-2 h-4 w-1/3" />
            </div>
          </div>
          <Skeleton className="mt-6 h-24 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : company ? (
        <>
          <header className="rounded-2xl border border-white/60 bg-white/82 p-5 shadow-[0_2px_16px_rgba(11,34,57,0.06)] backdrop-blur-md sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              <CompanyAvatar
                name={company.display_name}
                logoUrl={company.logo_url}
                size="lg"
              />
              <div className="min-w-0 flex-1">
                <h1 className="flex flex-wrap items-center gap-2 text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl">
                  <span>{company.display_name}</span>
                  {company.is_verified && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2.5 py-0.5 text-xs font-semibold text-[var(--brand-teal)]">
                      <SealCheck
                        aria-hidden
                        weight="fill"
                        className="size-4"
                      />
                      {t("verifiedPartner")}
                    </span>
                  )}
                </h1>

                <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-[var(--text-secondary)]">
                  {company.industry && (
                    <Meta icon={Buildings} label={t("industry")}>
                      {company.industry}
                    </Meta>
                  )}
                  {company.company_size && (
                    <Meta icon={UsersThree} label={t("size")}>
                      {company.company_size}
                    </Meta>
                  )}
                  {company.headquarters_city && (
                    <Meta icon={MapPin} label={t("hq")}>
                      {company.headquarters_city}
                    </Meta>
                  )}
                  {company.founded_year != null && (
                    <Meta icon={CalendarBlank} label={t("founded")}>
                      {company.founded_year}
                    </Meta>
                  )}
                </dl>

                {/* Quick-scan stats strip */}
                <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5">
                  {company.active_job_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                      <Briefcase aria-hidden weight="duotone" className="size-4" />
                      {t("openRolesCount", { count: company.active_job_count })}
                    </span>
                  )}
                  {company.rating && company.rating.overall_avg != null && (
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--text-secondary)]">
                      <Star aria-hidden weight="fill" className="size-4 text-[var(--brand-amber,#d97706)]" />
                      {company.rating.overall_avg.toFixed(1)}
                      <span className="font-normal text-[var(--text-muted)]">
                        ({t("reviewCount", { count: company.rating.review_count })})
                      </span>
                    </span>
                  )}
                  {company.website_url && (
                    <a
                      href={company.website_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                    >
                      <Globe aria-hidden weight="duotone" className="size-4" />
                      {t("visitWebsite")}
                    </a>
                  )}
                  <ReportButton
                    entityType="company"
                    entityId={company.id}
                    entityLabel={company.display_name}
                    className="ml-auto"
                  />
                </div>
              </div>
            </div>
          </header>

          {company.description && (
            <section className="mt-6">
              <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
                {t("about")}
              </h2>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
                {company.description}
              </p>
            </section>
          )}

          {/* AI Career Intelligence panel */}
          {careerInsights.length > 0 && (
            <section
              className="mt-6 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-5 backdrop-blur-xl"
              aria-label={t("aiCareerInsightsTitle")}
            >
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-xl icon-chip-info shadow-sm">
                  <Sparkle aria-hidden weight="duotone" className="size-4 text-white" />
                </span>
                {t("aiCareerInsightsTitle")}
              </h2>
              <ul className="space-y-2">
                {careerInsights.map((insight) => (
                  <li key={insight.key} className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]">
                    <LightbulbFilament
                      aria-hidden
                      weight="duotone"
                      className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]"
                    />
                    {insight.values ? t(insight.key, insight.values as Record<string, string>) : t(insight.key)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
              {t("openRoles")}
              <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)] ring-1 ring-white/50">
                {company.active_job_count}
              </span>
            </h2>

            {company.active_jobs.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {company.active_jobs.map((job) => (
                  <li key={job.id}>
                    <JobRow job={job} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                kind="empty"
                icon={Briefcase}
                title={t("noRolesTitle")}
                description={t("noRolesBody")}
                action={
                  <Link href="/jobs">
                    <Button variant="secondary">{t("browseAllJobs")}</Button>
                  </Link>
                }
              />
            )}
          </section>

          <CompanyReviewsSection slug={slug} rating={company.rating} />
        </>
      ) : null}
    </div>
  );
}

function Meta({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Icon
        aria-hidden
        weight="duotone"
        className="size-4 shrink-0 text-[var(--text-muted)]"
      />
      <dt className="sr-only">{label}</dt>
      <dd className="font-medium text-[var(--text-primary)]">{children}</dd>
    </div>
  );
}
