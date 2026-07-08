/**
 * Pure state + formatting helpers for the partner campaign-analytics surfaces.
 *
 * Analytics is AGGREGATES-ONLY (spec §7): totals, CTR, apply-start rate, and a
 * daily series — never an individual viewer, session, or candidate. RBAC is
 * owner-scoped server-side; a cross-org / unknown placement is a non-enumerable
 * 404, which the UI renders as a clean not-authorized state (never leaking that
 * the placement exists).
 *
 * Framework-free so the empty / not-authorized derivation is unit-testable.
 */

import { ApiError } from "@/lib/api";
import type {
  AdAnalyticsCounters,
  OrgAnalytics,
  PlacementAnalytics,
} from "@/lib/api";

/** How the analytics fetch failed, mapped to a user-safe non-data state. */
export type AnalyticsErrorKind = "notAuthorized" | "error";

/**
 * Classify an analytics query error. A 404 (cross-org / unknown placement), a
 * 403 (missing `advertising:view`), or a 401 all resolve to `notAuthorized` so
 * the UI shows a calm "not available" state instead of a scary error and never
 * confirms the placement exists. Everything else is a retryable `error`.
 */
export function analyticsErrorKind(error: unknown): AnalyticsErrorKind {
  if (error instanceof ApiError) {
    if (error.isNotFound || error.isPermissionError || error.isAuthError) {
      return "notAuthorized";
    }
  }
  return "error";
}

/** True when a counter bag has no signal at all. */
export function countersAreEmpty(
  counters: AdAnalyticsCounters | null | undefined,
): boolean {
  if (!counters) return true;
  return (
    counters.impressions === 0 &&
    counters.clicks === 0 &&
    counters.views === 0 &&
    counters.apply_starts === 0 &&
    counters.save_intents === 0 &&
    counters.event_register_intents === 0
  );
}

/**
 * True when a placement has accrued no measurable activity yet (no daily rows
 * and zero totals) — render the honest "no data yet" empty state, not a chart of
 * zeroes.
 */
export function isPlacementAnalyticsEmpty(
  analytics: PlacementAnalytics | null | undefined,
): boolean {
  if (!analytics) return true;
  return analytics.day_count === 0 && countersAreEmpty(analytics.totals);
}

/** True when the org rollup has no campaigns with any measured activity. */
export function isOrgAnalyticsEmpty(
  analytics: OrgAnalytics | null | undefined,
): boolean {
  if (!analytics) return true;
  return analytics.campaign_count === 0 || countersAreEmpty(analytics.totals);
}

/** Format a nullable percentage from the API (already 0-100), or a dash. */
export function formatRatePct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** A whole-number count formatted for the active locale. */
export function formatCount(value: number, locale: string): string {
  return value.toLocaleString(locale === "vi" ? "vi-VN" : "en-US");
}

/** Impressions series (chronological) for a sparkline, from the daily rows. */
export function impressionsSeries(
  analytics: PlacementAnalytics | null | undefined,
): number[] {
  return (analytics?.daily ?? []).map((d) => d.impressions);
}
