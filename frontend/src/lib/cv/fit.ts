import type { JobFitResult } from "@/lib/api";

/**
 * Product fit tiers from docs/CV_STUDIO_SPEC.md §3 ("Score bands").
 * These describe a deterministic **product** fit score, never AI confidence.
 *
 * Owner decision 2026-07-07: exactly THREE colour bands (no blue/black tier).
 * The full colour semantics stay red/amber/green so the ring and every band
 * bar read the same way an HR reviewer would triage:
 *   - `weak`   (< 50)   → red     "not there yet"
 *   - `mid`    (50–79)  → amber    "usable with work"
 *   - `strong` (>= 80)  → green    "ready"
 */
export type FitTier = "strong" | "mid" | "weak";

/** Score → tier. The single source of truth for the whole fit UI. */
export function fitTier(score: number): FitTier {
  if (score >= 80) return "strong";
  if (score >= 50) return "mid";
  return "weak";
}

/** Meter/fill (ring stroke, band fill) color token per tier (DESIGN.md families). */
export const FIT_TIER_FILL: Record<FitTier, string> = {
  strong: "var(--teal-500)",
  mid: "var(--amber-500)",
  weak: "var(--red-500)",
};

/** Score/label text color token per tier (AA contrast on light surfaces). */
export const FIT_TIER_TEXT: Record<FitTier, string> = {
  strong: "var(--teal-600)",
  mid: "var(--amber-700)",
  weak: "var(--brand-red)",
};

/**
 * Single fill-colour helper so the total-score ring and every band bar can
 * never diverge — always derive colour from the numeric score here.
 */
export function fitColor(score: number): string {
  return FIT_TIER_FILL[fitTier(score)];
}

/** Single text-colour helper (score number, tier label). */
export function fitTextColor(score: number): string {
  return FIT_TIER_TEXT[fitTier(score)];
}

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
