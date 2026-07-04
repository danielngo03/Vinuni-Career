import type { JobFitResult } from "@/lib/api";

/**
 * Product fit tiers from docs/CV_STUDIO_SPEC.md §3 ("Score bands").
 * These describe a deterministic **product** fit score, never AI confidence.
 */
export type FitTier = "strong" | "good" | "possible" | "weak";

export function fitTier(score: number): FitTier {
  if (score >= 85) return "strong";
  if (score >= 70) return "good";
  if (score >= 50) return "possible";
  return "weak";
}

/** Meter/fill color token per tier (DESIGN.md families). */
export const FIT_TIER_FILL: Record<FitTier, string> = {
  strong: "var(--teal-500)",
  good: "var(--brand-mid-blue)",
  possible: "var(--amber-500)",
  weak: "var(--red-500)",
};

/** Score/label text color token per tier (AA contrast on light surfaces). */
export const FIT_TIER_TEXT: Record<FitTier, string> = {
  strong: "var(--teal-600)",
  good: "var(--blue-600)",
  possible: "var(--amber-700)",
  weak: "var(--brand-red)",
};

/**
 * Stable ranking matching the backend tie-break: score desc, then freshest
 * (smaller `last_updated_days`), then id. Pure; never mutates the input.
 */
export function rankByScore<T extends JobFitResult>(results: readonly T[]): T[] {
  return [...results].sort(
    (a, b) =>
      b.score - a.score ||
      a.last_updated_days - b.last_updated_days ||
      a.cv_id.localeCompare(b.cv_id),
  );
}
