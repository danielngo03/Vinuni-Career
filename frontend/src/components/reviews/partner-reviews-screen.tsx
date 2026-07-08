"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { LightbulbFilament, Sparkle, Star } from "@phosphor-icons/react";
import { EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { organizationApi, companiesApi } from "@/lib/api";
import { CompanyReviewsSection } from "@/components/reviews/company-reviews-section";
import { StarDisplay } from "./star-rating";

function RatingSkeletons() {
  return (
    <div className="mt-8 space-y-4">
      <Skeleton className="h-28 w-full rounded-2xl" />
      <Skeleton className="h-24 w-full rounded-2xl" />
      <Skeleton className="h-24 w-full rounded-2xl" />
    </div>
  );
}

export function PartnerReviewsScreen() {
  const t = useTranslations("partnerReviews");

  const orgQuery = useQuery({
    queryKey: ["org", "profile"],
    queryFn: () => organizationApi.get(),
    retry: false,
  });

  const slug = orgQuery.data?.slug;

  const companyQuery = useQuery({
    queryKey: ["company", slug],
    queryFn: () => companiesApi.getBySlug(slug!),
    enabled: !!slug,
    retry: false,
  });

  const displayName = orgQuery.data?.display_name ?? "";
  const isVerified = orgQuery.data?.is_verified ?? false;

  if (orgQuery.isPending || (slug && companyQuery.isPending)) {
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <RatingSkeletons />
      </>
    );
  }

  if (orgQuery.isError || !slug) {
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <div className="mt-8">
          <EmptyState
            kind="error"
            icon={Star}
            title={t("errorTitle")}
            description={t("errorBody")}
          />
        </div>
      </>
    );
  }

  const rating = companyQuery.data?.rating ?? null;

  return (
    <>
      <PageHeader
        title={t("title")}
        description={
          displayName
            ? t("subtitleNamed", { name: displayName })
            : t("subtitle")
        }
      />

      {/* Rating overview strip */}
      {rating && rating.overall_avg != null && (
        <div className="mt-6 flex items-center gap-4 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 ">
          <div className="flex flex-col items-center gap-0.5 pr-4 border-r border-[var(--border-default)]">
            <span className="text-3xl font-bold text-[var(--text-primary)]">
              {rating.overall_avg.toFixed(1)}
            </span>
            <StarDisplay value={rating.overall_avg} size={16} />
            <span className="text-xs text-[var(--text-muted)]">
              {t("basedOn", { count: rating.review_count })}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {isVerified && (
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--brand-primary)]/30 bg-[var(--brand-primary)]/10 px-2.5 py-0.5 text-xs font-semibold text-[var(--brand-primary)]">
                {t("verifiedBadge")}
              </span>
            )}
            <p className="text-sm text-[var(--text-secondary)]">
              {t("respondCta")}
            </p>
          </div>
        </div>
      )}

      {/* ── AI Employer Brand Insights ── */}
      {rating && (() => {
        type ReviewInsightKey = "insightHighRating" | "insightGoodRating" | "insightFewReviews" | "insightNoReviews" | "insightVerified";
        const insights: ReviewInsightKey[] = [];
        if (rating.review_count === 0) {
          insights.push("insightNoReviews");
        } else {
          if (rating.overall_avg != null && rating.overall_avg >= 4.0) insights.push("insightHighRating");
          else if (rating.overall_avg != null && rating.overall_avg >= 3.5) insights.push("insightGoodRating");
          if (rating.review_count < 5) insights.push("insightFewReviews");
          if (isVerified) insights.push("insightVerified");
        }
        if (!insights.length) return null;
        return (
          <section
            aria-label={t("aiInsightsTitle")}
            className="mt-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{t("aiInsightsTitle")}</p>
            </div>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Full review list — reuses public section with partner persona auto-detected */}
      <CompanyReviewsSection slug={slug} rating={rating} />
    </>
  );
}
