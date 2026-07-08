"use client";

import { useId, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowRight, MapPin } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { DisclosureLabel } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { useImpression } from "@/lib/discovery/use-impression";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { formatLocation } from "@/lib/jobs/format";
import { cn } from "@/lib/utils";
import type { InventoryDisclosure, MarketplaceBanner } from "@/lib/api";

/**
 * Editorial marketplace campaign banner (spec §5/§7). Renders an approved
 * `creative` image with a responsive focal-point crop + the polished, class-keyed
 * disclosure label, or — when no creative exists — an institutional text card.
 * A `vinuni_curated` source renders distinctly (curated, NEVER paid).
 *
 * Paid (`partner`) placements self-track a one-shot `impression` + `click`
 * carrying the `placement_id`, so paid inventory is measured separately. The
 * curated fallback carries no placement and is not tracked as paid inventory.
 *
 * `variant="hero"` is the wide homepage banner; `variant="rail"` is the compact
 * right-rail banner. Renders nothing when neither a creative nor a job exists.
 */
export function MarketplaceBannerCard({
  banner,
  variant,
  className,
}: {
  banner: MarketplaceBanner;
  variant: "hero" | "rail";
  className?: string;
}) {
  const t = useTranslations("discovery");
  const tJobs = useTranslations("jobs");
  const renderId = useId();
  const [imgFailed, setImgFailed] = useState(false);

  const { job, creative } = banner;
  // Prefer the polished class-keyed disclosure; fall back to the legacy alias.
  const disclosure = (banner.disclosure ??
    banner.sponsored_disclosure) as InventoryDisclosure | undefined;

  const isPaidPartner =
    banner.source === "partner" && Boolean(banner.placement_id);
  const placementId = isPaidPartner ? banner.placement_id : null;
  const surface =
    variant === "hero" ? "homepage_sponsored" : "right_rail_banner";

  const trackingId = job?.id ?? banner.placement_id ?? null;

  // Impression analytics ONLY for paid placements (curated has no placement).
  const impression = useMemo(
    () =>
      placementId && trackingId
        ? ({
            event_type: "impression" as const,
            source_surface: surface as
              | "homepage_sponsored"
              | "right_rail_banner",
            target_type: "banner" as const,
            target_id: trackingId,
            placement_id: placementId,
            idempotency_key: `${renderId}:${placementId}:impression`,
          })
        : null,
    [placementId, trackingId, surface, renderId],
  );
  const ref = useImpression<HTMLDivElement>(impression);

  function handleClick() {
    if (!placementId || !trackingId) return;
    recordDiscoveryEvent({
      event_type: "click",
      source_surface: surface,
      target_type: "banner",
      target_id: trackingId,
      placement_id: placementId,
      idempotency_key: `${renderId}:${placementId}:click`,
    });
  }

  const href = creative?.click_target ?? (job ? `/jobs/${job.id}` : null);
  if (!href || !disclosure) return null;

  const showImage = Boolean(creative?.image_url) && !imgFailed;
  // Nothing renderable: no usable image AND no job to describe → hide the slot.
  if (!showImage && !job) return null;

  const fx = Math.round((creative?.focal_point?.x ?? 0.5) * 100);
  const fy = Math.round((creative?.focal_point?.y ?? 0.5) * 100);
  const altText = creative?.alt ?? job?.title ?? disclosure.label;
  const captionTitle = job?.title ?? creative?.alt ?? disclosure.label;

  return (
    <div
      ref={ref}
      className={cn(
        "overflow-hidden rounded-xl border border-white/60 bg-white/82 shadow-[0_2px_16px_rgba(11,34,57,0.08)] backdrop-blur-md",
        className,
      )}
    >
      <Link
        href={href}
        onClick={handleClick}
        className="group block outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        {showImage ? (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={creative!.image_url}
              alt={altText ?? ""}
              onError={() => setImgFailed(true)}
              loading="lazy"
              className={cn(
                "w-full object-cover",
                variant === "hero"
                  ? "aspect-[16/9] sm:aspect-[4/1]"
                  : "aspect-[4/5]",
              )}
              style={{ objectPosition: `${fx}% ${fy}%` }}
            />
            <span className="pointer-events-none absolute right-3 top-3 z-10">
              <DisclosureLabel disclosure={disclosure} />
            </span>
            {/* Caption overlay for legibility + clear intent. */}
            <div className="absolute inset-x-0 bottom-0 flex items-center gap-3 bg-gradient-to-t from-black/65 via-black/30 to-transparent px-4 pb-3 pt-10">
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 text-sm font-bold text-white sm:text-base">
                  {captionTitle}
                </p>
                {job?.company && (
                  <p className="mt-0.5 line-clamp-1 text-xs font-medium text-white/85">
                    {job.company.display_name}
                  </p>
                )}
              </div>
              <ArrowRight
                aria-hidden
                weight="bold"
                className="size-5 shrink-0 text-white transition-transform group-hover:translate-x-0.5"
              />
            </div>
          </div>
        ) : (
          // No creative image — institutional text card (still labelled + linked).
          <div>
            <div className="flex items-center justify-end bg-white/40 px-4 py-2">
              <DisclosureLabel disclosure={disclosure} />
            </div>
            <div
              className={cn(
                "flex items-start gap-3 p-4",
                variant === "hero" && "sm:items-center sm:gap-5 sm:p-5",
              )}
            >
              {job && (
                <CompanyAvatar
                  name={job.company?.display_name ?? job.title}
                  logoUrl={job.company?.logo_url}
                  size={variant === "hero" ? "lg" : "md"}
                />
              )}
              <div className="min-w-0 flex-1">
                <h3
                  className={cn(
                    "font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]",
                    variant === "hero" ? "text-lg" : "line-clamp-2 text-base",
                  )}
                >
                  {captionTitle}
                </h3>
                {job?.company && (
                  <p className="mt-0.5 truncate text-sm font-medium text-[var(--text-secondary)]">
                    {job.company.display_name}
                  </p>
                )}
                {job && (
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <MapPin
                      aria-hidden
                      weight="duotone"
                      className="size-3.5 shrink-0"
                    />
                    {formatLocation(job.location_city, job.location_country)}
                  </p>
                )}
              </div>
              <span className="mt-1 inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                {job ? tJobs("apply") : t("viewAll")}
                <ArrowRight aria-hidden weight="bold" className="size-4" />
              </span>
            </div>
          </div>
        )}
      </Link>
    </div>
  );
}
