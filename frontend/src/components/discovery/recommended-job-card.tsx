"use client";

import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";
import { Briefcase, MapPin, CurrencyCircleDollar, Star } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { StatusBadge, SponsoredLabel } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { ReasonChips, SourceBadge, FitScore } from "./reason-chips";
import { useImpression } from "@/lib/discovery/use-impression";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { recordJobEngagement, useJobImpression } from "@/lib/analytics/job-engagement";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import { cn } from "@/lib/utils";
import type {
  CoarseSignalTags,
  DiscoverySourceSurface,
  JobEngagementSource,
  RecommendedJob,
} from "@/lib/api";

/** Best-effort mapping to the coarser job-engagement source vocabulary. */
function engagementSourceFor(
  surface: DiscoverySourceSurface,
  isSponsored: boolean,
): JobEngagementSource {
  if (isSponsored) return "sponsored";
  if (surface.includes("recommended")) return "recommendation";
  if (surface === "search" || surface === "search_recommended") return "search";
  return "organic";
}

/**
 * A ranked job card for recommendation/sponsored/similar rails. Visually
 * separates the four inventory classes (organic, recommended, sponsored,
 * curated) via distinct accents + badges, with a NON-REMOVABLE sponsored
 * disclosure on paid inventory. Self-tracks a one-shot `impression` (when 40%
 * visible) and a `click` event; analytics never block the link navigation.
 */
export function RecommendedJobCard({
  item,
  surface,
  renderId,
  signalTags,
  showScore = true,
}: {
  item: RecommendedJob;
  /** Inventory-classed surface, already resolved for this item's source. */
  surface: DiscoverySourceSurface;
  /** Stable per-rail-render id for idempotency keys. */
  renderId: string;
  /** Coarse signals (e.g. current search term) merged onto the guest session. */
  signalTags?: CoarseSignalTags;
  showScore?: boolean;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const salary = formatSalary(item.salary, locale);

  const isSponsored = item.source === "sponsored" || Boolean(item.sponsored_disclosure);
  const placementId = isSponsored ? item.placement_id : null;

  const impression = useMemo(
    () => ({
      event_type: "impression" as const,
      source_surface: surface,
      target_type: "job" as const,
      target_id: item.id,
      placement_id: placementId,
      idempotency_key: `${renderId}:${item.id}:impression`,
      signal_tags: signalTags,
    }),
    [surface, item.id, placementId, renderId, signalTags],
  );
  const discoveryRef = useImpression<HTMLLIElement>(impression);
  const engagementSource = engagementSourceFor(surface, isSponsored);
  const jobEngagementRef = useJobImpression<HTMLLIElement>(item.id, engagementSource);

  function setRefs(node: HTMLLIElement | null) {
    discoveryRef.current = node;
    jobEngagementRef.current = node;
  }

  function handleClick() {
    recordDiscoveryEvent({
      event_type: "click",
      source_surface: surface,
      target_type: "job",
      target_id: item.id,
      placement_id: placementId,
      idempotency_key: `${renderId}:${item.id}:click`,
      signal_tags: signalTags,
    });
    recordJobEngagement(item.id, "cta_click", engagementSource);
  }

  // Fit score is shown only when there is genuine CV evidence. Guest/session
  // recommendations can still be useful, but they are NOT a CV match.
  const hasCvFit = item.reason_codes.some((r) => r.code === "cv_fit");
  const displayScore =
    showScore && (hasCvFit || Boolean(item.recommended_cv_id));

  // Distinct accent per inventory class (never color-only: badges carry text).
  const accent = isSponsored
    ? "border-l-[3px] border-l-[var(--brand-red)]"
    : item.source === "recommended"
      ? "border-l-[3px] border-l-[var(--brand-primary)]"
      : item.source === "curated"
        ? "border-l-[3px] border-l-[var(--brand-teal)]"
        : "";

  return (
    <li ref={setRefs}>
      <div
        className={cn(
          "marketplace-card marketplace-card-hover group relative flex h-full min-h-[200px] flex-col rounded-[14px] p-5 has-[a:focus-visible]:border-[var(--brand-primary)] has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-[var(--brand-primary)]/30",
          accent,
        )}
      >
        {/* Stretched primary navigation (carries the click analytics). */}
        <Link
          href={`/jobs/${item.id}`}
          onClick={handleClick}
          aria-label={item.title}
          className="absolute inset-0 z-0 rounded-xl outline-none"
        />

        {/* Top-right cluster: inventory class badge + Heart save. */}
        <div className="absolute right-3 top-3 z-10 flex flex-wrap items-center justify-end gap-1.5">
          {isSponsored && item.sponsored_disclosure && (
            <SponsoredLabel label={item.sponsored_disclosure.label} />
          )}
          {!isSponsored && <SourceBadge source={item.source} />}
          {item.is_featured && (
            <StatusBadge tone="featured">
              <Star aria-hidden weight="fill" className="size-3" />
              {t("featured")}
            </StatusBadge>
          )}
          <SaveJobButton jobId={item.id} size="sm" initialSaved={item.is_saved ?? false} />
        </div>

        <div className="pointer-events-none relative z-[1] flex h-full flex-col">
          <div className="mb-3 flex items-start gap-2">
            {item.company ? (
              <CompanyAvatar
                name={item.company.display_name}
                logoUrl={item.company.logo_url}
                size="sm"
              />
            ) : (
              <span
                aria-hidden
                className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm"
              >
                <Briefcase weight="duotone" className="size-5 text-white" />
              </span>
            )}
          </div>

          <h3 className="line-clamp-2 pr-10 text-base font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
            {item.title}
          </h3>

          {item.company && (
            <p className="mt-1 truncate text-sm font-medium text-[var(--text-secondary)]">
              {item.company.display_name}
            </p>
          )}

          <dl className="mt-3 flex flex-col gap-1.5 text-sm text-[var(--text-secondary)]">
            <div className="flex items-center gap-2">
              <Briefcase aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
              <dt className="sr-only">{t("employmentType")}</dt>
              <dd>
                {labels.employmentType(item.employment_type, item.employment_type_label)}
                {" · "}
                {labels.locationType(item.location_type, item.location_type_label)}
              </dd>
            </div>
            <div className="flex items-center gap-2">
              <MapPin aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
              <dt className="sr-only">{t("location")}</dt>
              <dd className="truncate">
                {formatLocation(item.location_city, item.location_country)}
              </dd>
            </div>
            {salary && (
              <div className="flex items-center gap-2">
                <CurrencyCircleDollar aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--text-muted)]" />
                <dt className="sr-only">{t("salary")}</dt>
                <dd>{salary}</dd>
              </div>
            )}
          </dl>

          {/* Why this item appears (user-safe reason codes). */}
          {item.reason_codes.length > 0 && (
            <ReasonChips reasons={item.reason_codes} className="mt-3" />
          )}

          {displayScore && (
            <div className="mt-auto pt-3">
              <FitScore score={item.score} />
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
