"use client";

import { useId, useMemo, useState } from "react";
import { ArrowRight, Megaphone } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { DisclosureLabel } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { useImpression } from "@/lib/discovery/use-impression";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { cn } from "@/lib/utils";
import type {
  DiscoverySourceSurface,
  DiscoveryTargetType,
  EventSummary,
  InventoryDisclosure,
  JobSummary,
  MarketplaceBanner,
} from "@/lib/api";

export function MegaCampaignCard({
  banner,
  className,
}: {
  banner: MarketplaceBanner | null | undefined;
  className?: string;
}) {
  const renderId = useId();
  const [imgFailed, setImgFailed] = useState(false);
  const disclosure = (banner?.disclosure ??
    banner?.sponsored_disclosure) as InventoryDisclosure | undefined;
  const job = banner?.job;
  const creative = banner?.creative;
  const href = creative?.click_target ?? (job ? `/jobs/${job.id}` : null);
  const placementId = banner?.source === "partner" ? banner.placement_id : null;
  const trackingId = job?.id ?? banner?.placement_id ?? null;
  const showImage = Boolean(creative?.image_url) && !imgFailed;

  const impression = useMemo(
    () =>
      href && disclosure && (showImage || job) && placementId && trackingId
        ? ({
            event_type: "impression" as const,
            source_surface: "mega_sponsored" as const,
            target_type: "banner" as const,
            target_id: trackingId,
            placement_id: placementId,
            idempotency_key: `${renderId}:${placementId}:impression`,
          })
        : null,
    [href, disclosure, showImage, job, placementId, trackingId, renderId],
  );
  const ref = useImpression<HTMLDivElement>(impression);

  if (!banner || !href || !disclosure || (!showImage && !job)) return null;

  function handleClick() {
    if (!placementId || !trackingId) return;
    recordDiscoveryEvent({
      event_type: "click",
      source_surface: "mega_sponsored",
      target_type: "banner",
      target_id: trackingId,
      placement_id: placementId,
      idempotency_key: `${renderId}:${placementId}:click`,
    });
  }

  const fx = Math.round((creative?.focal_point?.x ?? 0.5) * 100);
  const fy = Math.round((creative?.focal_point?.y ?? 0.5) * 100);
  const title = job?.title ?? creative?.alt ?? disclosure.label;

  return (
    <div
      ref={ref}
      className={cn(
        "overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)]",
        className,
      )}
    >
      <Link
        href={href}
        onClick={handleClick}
        className="group block outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        {showImage ? (
          <div className="relative aspect-[16/7] overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={creative!.image_url}
              alt={creative?.alt ?? title}
              onError={() => setImgFailed(true)}
              className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
              style={{ objectPosition: `${fx}% ${fy}%` }}
            />
            <span className="absolute left-3 top-3">
              <DisclosureLabel disclosure={disclosure} />
            </span>
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 via-black/30 to-transparent px-3 pb-3 pt-10">
              <p className="line-clamp-1 text-sm font-bold text-white">{title}</p>
              {job?.company && (
                <p className="mt-0.5 line-clamp-1 text-xs font-medium text-white/85">
                  {job.company.display_name}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <DisclosureLabel disclosure={disclosure} />
              <Megaphone
                aria-hidden
                weight="duotone"
                className="size-5 text-[var(--brand-primary)]"
              />
            </div>
            <div className="flex items-start gap-3">
              {job && (
                <CompanyAvatar
                  name={job.company?.display_name ?? job.title}
                  logoUrl={job.company?.logo_url}
                  size="sm"
                />
              )}
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                  {title}
                </p>
                {job?.company && (
                  <p className="mt-0.5 truncate text-xs font-medium text-[var(--text-secondary)]">
                    {job.company.display_name}
                  </p>
                )}
              </div>
              <ArrowRight
                aria-hidden
                weight="bold"
                className="mt-1 size-4 shrink-0 text-[var(--brand-primary)] transition-transform group-hover:translate-x-0.5"
              />
            </div>
          </div>
        )}
      </Link>
    </div>
  );
}

export function MegaPromoCard({
  href,
  title,
  subtitle,
  eyebrow,
  imageUrl,
  logo,
  logoName,
  surface,
  targetType,
  targetId,
  renderId,
  className,
}: {
  href: string;
  title: string;
  subtitle?: string | null;
  eyebrow: string;
  imageUrl?: string | null;
  logo?: string | null;
  logoName?: string | null;
  surface: DiscoverySourceSurface;
  targetType: DiscoveryTargetType;
  targetId: string;
  renderId: string;
  className?: string;
}) {
  return (
    <TrackedItem
      surface={surface}
      targetType={targetType}
      targetId={targetId}
      renderId={renderId}
      className={className}
    >
      <Link
        href={href}
        className="group block overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/50 hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        {imageUrl ? (
          <div className="relative aspect-[16/7] overflow-hidden bg-[var(--surface-tertiary)]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt={title}
              className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            />
          </div>
        ) : null}
        <div className="p-4">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
            {eyebrow}
          </p>
          <div className="mt-2 flex items-start gap-3">
            {!imageUrl && (
              <CompanyAvatar
                name={logoName ?? title}
                logoUrl={logo}
                size="sm"
              />
            )}
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                {title}
              </p>
              {subtitle && (
                <p className="mt-1 line-clamp-2 text-xs font-medium text-[var(--text-secondary)]">
                  {subtitle}
                </p>
              )}
            </div>
            <ArrowRight
              aria-hidden
              weight="bold"
              className="mt-1 size-4 shrink-0 text-[var(--brand-primary)] transition-transform group-hover:translate-x-0.5"
            />
          </div>
        </div>
      </Link>
    </TrackedItem>
  );
}

export function jobPromoFrom(job: JobSummary | null | undefined) {
  if (!job) return null;
  return {
    href: `/jobs/${job.id}`,
    title: job.title,
    subtitle: job.company?.display_name ?? null,
    logo: job.company?.logo_url ?? null,
    logoName: job.company?.display_name ?? job.title,
    targetId: job.id,
  };
}

export function eventPromoFrom(event: EventSummary | null | undefined, subtitle: string) {
  if (!event) return null;
  return {
    href: `/events/${event.id}`,
    title: event.title,
    subtitle,
    imageUrl: event.cover_image_url,
    targetId: event.id,
  };
}
