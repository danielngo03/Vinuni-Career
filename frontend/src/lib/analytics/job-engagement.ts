"use client";

import { useEffect, useRef } from "react";
import { analyticsApi } from "@/lib/api";
import type { JobEngagementEventType, JobEngagementSource } from "@/lib/api";

/**
 * Public job-engagement pixel (`POST /analytics/jobs/{job_id}/engagement`):
 * feeds the partner-facing `partner_job_metrics_daily` read model behind
 * Partner Dashboard V2's `job_performance` widget. This is a SEPARATE signal
 * from `lib/discovery/analytics.ts` (which drives the public discovery/ranking
 * read models) — both may legitimately fire for the same interaction.
 *
 * Fire-and-forget: never blocks render, never throws, best-effort only. A
 * genuine detail view / save / apply already has its own authoritative
 * backend write — only impression / cta_click / share_click belong here.
 */

const sentImpressions = new Set<string>();

export function recordJobEngagement(
  jobId: string,
  eventType: JobEngagementEventType,
  source?: JobEngagementSource,
): void {
  if (typeof window === "undefined") return;

  // Only de-dupe impressions (one per mount); clicks/shares are discrete
  // user actions and should each be recorded.
  const dedupeKey = `${jobId}:impression`;
  if (eventType === "impression") {
    if (sentImpressions.has(dedupeKey)) return;
    sentImpressions.add(dedupeKey);
  }

  void analyticsApi
    .recordJobEngagement(jobId, { event_type: eventType, source: source ?? null })
    .catch(() => {
      if (eventType === "impression") sentImpressions.delete(dedupeKey);
    });
}

/**
 * Fire a single `impression` engagement pixel the first time the referenced
 * element is >= 40% visible. Pass `null` to disable (non-job cards, or while
 * data is loading). Intentionally mirrors `lib/discovery/use-impression.ts`'s
 * threshold so both pixels fire at the same "seen" moment, but stays a
 * separate observer since the two feed separate read models.
 */
export function useJobImpression<T extends HTMLElement>(
  jobId: string | null,
  source?: JobEngagementSource,
): React.RefObject<T | null> {
  const ref = useRef<T | null>(null);
  const jobIdRef = useRef(jobId);
  jobIdRef.current = jobId;
  const sourceRef = useRef(source);
  sourceRef.current = source;

  useEffect(() => {
    const el = ref.current;
    if (!el || !jobIdRef.current) return;

    if (typeof IntersectionObserver === "undefined") {
      recordJobEngagement(jobIdRef.current, "impression", sourceRef.current);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.4) {
            if (jobIdRef.current) {
              recordJobEngagement(jobIdRef.current, "impression", sourceRef.current);
            }
            observer.disconnect();
            break;
          }
        }
      },
      { threshold: [0.4] },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [jobId]);

  return ref;
}
