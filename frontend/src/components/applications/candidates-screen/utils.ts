import type { ApiListEnvelope, PartnerApplication } from "@/lib/api";
import type { InfiniteData } from "@tanstack/react-query";

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

export type ForJobData = InfiniteData<ApiListEnvelope<PartnerApplication>>;

export function nowIso() {
  return new Date().toISOString();
}
