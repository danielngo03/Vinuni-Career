import type { BulkAdvanceResult, PipelineCard } from "@/lib/api";

/** A card is flagged "stale" once it has sat in a column past this threshold. */
export const STALE_DAYS = 7;

/** Minimum rollback-reason length required by the backend (ADR-0005 §5). */
export const MIN_REASON = 20;

/** Whole days a card has sat in its current stage, or null when it has no
 *  stage row yet (the "new" pre-pipeline bucket has a null `entered_at`). */
export function daysInStage(enteredAt: string | null | undefined): number | null {
  if (!enteredAt) return null;
  const t = new Date(enteredAt).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

/** Anonymity-safe display handle. Prefers the revealed name, else UV-xxxx. */
export function cardHandle(card: PipelineCard): string {
  if (card.is_anonymous && card.applicant.anonymous_id) {
    return card.applicant.anonymous_id;
  }
  return card.applicant.display_name ?? card.applicant.anonymous_id ?? "—";
}


/**
 * Group a bulk-advance batch result (BUSINESS_LOGIC §3.6) into product-facing
 * buckets so the board can honestly report "N advanced · M couldn't (reason)".
 * Pure + i18n-free: the caller composes the localized summary from these counts.
 */
export interface BulkAdvanceBreakdown {
  advanced: number;
  scorecardBlocked: number;
  thresholdBlocked: number;
  otherBlocked: number;
  skipped: number;
  errors: number;
}

export function groupBulkAdvance(
  result: BulkAdvanceResult,
): BulkAdvanceBreakdown {
  const blocked = result.results.filter((r) => r.outcome === "blocked");
  const scorecardBlocked = blocked.filter(
    (r) => r.reason === "scorecard_required",
  ).length;
  const thresholdBlocked = blocked.filter(
    (r) => r.reason === "score_below_threshold",
  ).length;
  return {
    advanced: result.advanced,
    scorecardBlocked,
    thresholdBlocked,
    otherBlocked: blocked.length - scorecardBlocked - thresholdBlocked,
    skipped: result.skipped,
    errors: result.errors,
  };
}
