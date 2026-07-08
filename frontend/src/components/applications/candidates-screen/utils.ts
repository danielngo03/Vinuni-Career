import type { ApiListEnvelope, PartnerApplication } from "@/lib/api";
import type { InfiniteData } from "@tanstack/react-query";

export const MIN_REASON = 20;

/**
 * Client-side refine of the loaded candidate list (ATS-style stage filter),
 * matching the REAL `application.status` vocabulary. `shortlisted` /
 * `interview` / `offer` are never `application.status` values — that progress
 * is tracked separately (pipeline stage / interviews / offers) — so they are
 * not valid filters here.
 */
export const STAGE_FILTERS = [
  "all",
  "submitted",
  "under_review",
  "rejected",
  "withdrawn",
  "hired",
] as const;

export const STAGE_CHIP_ACTIVE: Record<string, string> = {
  all: "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20",
  submitted: "border-[var(--gray-600)]/30 bg-[var(--gray-700)] text-white shadow-sm",
  under_review: "border-amber-400/30 bg-amber-500 text-white shadow-sm",
  rejected: "border-red-500/30 bg-red-600 text-white shadow-sm",
  withdrawn: "border-[var(--gray-300)]/30 bg-[var(--gray-400)] text-white shadow-sm",
  // v9 Monochrome reserves green for verified/success states.
  hired: "border-emerald-500/30 bg-emerald-600 text-white shadow-sm",
};

export type ForJobData = InfiniteData<ApiListEnvelope<PartnerApplication>>;

/**
 * `insightInterviewsActive` / `insightOfferSent` / `insightStrongPipeline`
 * were previously derived from `status === "interview"|"offer"|"shortlisted"`
 * — statuses the backend never emits on `application.status`, so those counts
 * were always zero (dead code). Interview/offer progress isn't present on this
 * list projection (`pipeline.offer` is detail-only), so those insights are
 * retired here rather than faked from unavailable data.
 */
export type CandidateInsightKey =
  | "insightReviewPending"
  | "insightAnonymousPending"
  | "insightHiresMade";

export function deriveCandidateInsights(
  rows: PartnerApplication[],
): CandidateInsightKey[] {
  const out: CandidateInsightKey[] = [];
  const submitted = rows.filter((r) => r.status === "submitted").length;
  const hired = rows.filter((r) => r.status === "hired").length;
  const anonymous = rows.filter(
    (r) => r.is_anonymous && r.reveal_status === "none",
  ).length;
  if (submitted > 2) out.push("insightReviewPending");
  if (hired > 0) out.push("insightHiresMade");
  if (anonymous > 0 && out.length < 2) out.push("insightAnonymousPending");
  return out.slice(0, 3);
}

export function nowIso() {
  return new Date().toISOString();
}
