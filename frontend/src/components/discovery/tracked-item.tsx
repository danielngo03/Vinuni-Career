"use client";

import { useMemo } from "react";
import { useImpression } from "@/lib/discovery/use-impression";
import { recordDiscoveryEvent } from "@/lib/discovery/analytics";
import { recordJobEngagement, useJobImpression } from "@/lib/analytics/job-engagement";
import type {
  CoarseSignalTags,
  DiscoverySourceSurface,
  DiscoveryTargetType,
  DiscoveryEventType,
  JobEngagementSource,
} from "@/lib/api";

/** Best-effort mapping from the discovery surface to the coarser job-engagement
 * source vocabulary (docs/PARTNER_RBAC_ANALYTICS_SPEC.md source-mix dimension). */
function engagementSourceFor(surface: DiscoverySourceSurface): JobEngagementSource {
  if (surface.includes("sponsored")) return "sponsored";
  if (surface.includes("recommended")) return "recommendation";
  if (surface === "search" || surface === "search_recommended") return "search";
  return "organic";
}

/**
 * Generic impression+click tracker for non-job cards (events, employer
 * spotlight) where the inner content is a self-contained Link. Wraps children in
 * a passive `<div>` that fires a one-shot `impression` when visible and a
 * `click` (defaulting to the surface's natural type) on pointer-down. Purely
 * additive — it never changes focus order or the accessibility tree.
 */
export function TrackedItem({
  surface,
  targetType,
  targetId,
  renderId,
  clickEvent = "click",
  placementId = null,
  signalTags,
  className,
  children,
}: {
  surface: DiscoverySourceSurface;
  targetType: DiscoveryTargetType;
  targetId: string;
  renderId: string;
  clickEvent?: DiscoveryEventType;
  placementId?: string | null;
  signalTags?: CoarseSignalTags;
  className?: string;
  children: React.ReactNode;
}) {
  const impression = useMemo(
    () => ({
      event_type: "impression" as const,
      source_surface: surface,
      target_type: targetType,
      target_id: targetId,
      placement_id: placementId,
      idempotency_key: `${renderId}:${targetId}:impression`,
      signal_tags: signalTags,
    }),
    [surface, targetType, targetId, placementId, renderId, signalTags],
  );
  const discoveryRef = useImpression<HTMLDivElement>(impression);
  const isJob = targetType === "job";
  const engagementSource = isJob ? engagementSourceFor(surface) : undefined;
  const jobEngagementRef = useJobImpression<HTMLDivElement>(
    isJob ? targetId : null,
    engagementSource,
  );

  function setRefs(node: HTMLDivElement | null) {
    discoveryRef.current = node;
    jobEngagementRef.current = node;
  }

  function handleClick() {
    recordDiscoveryEvent({
      event_type: clickEvent,
      source_surface: surface,
      target_type: targetType,
      target_id: targetId,
      placement_id: placementId,
      idempotency_key: `${renderId}:${targetId}:${clickEvent}`,
      signal_tags: signalTags,
    });
    if (isJob) {
      recordJobEngagement(targetId, "cta_click", engagementSource);
    }
  }

  return (
    <div ref={setRefs} onClickCapture={handleClick} className={className}>
      {children}
    </div>
  );
}
