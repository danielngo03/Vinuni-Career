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

/* --------------------------------- Sorting -------------------------------- */

/**
 * Triage sort keys. DEFAULT is `needs_action` (NOT best match): sorting a queue
 * by fit buries fresh/unreviewed candidates and breaks review SLA + fairness.
 * `best_match` is a SECONDARY sort a recruiter switches to for shortlisting.
 */
export const SORT_KEYS = [
  "needs_action",
  "newest",
  "oldest",
  "best_match",
  "status",
] as const;

export type SortKey = (typeof SORT_KEYS)[number];

/** Needs-action bucket: submitted first, then under_review, then decided. */
function actionBucket(status: string): number {
  if (status === "submitted") return 0;
  if (status === "under_review") return 1;
  return 2; // rejected / withdrawn / hired — decided
}

/** Stable status grouping order for the "by status" sort. */
const STATUS_ORDER: Record<string, number> = {
  submitted: 0,
  under_review: 1,
  hired: 2,
  rejected: 3,
  withdrawn: 4,
};

function appliedTime(r: PartnerApplication): number {
  return new Date(r.applied_at).getTime() || 0;
}

/** Freshness of the last transition (falls back to applied). */
function activityTime(r: PartnerApplication): number {
  return new Date(r.last_status_at ?? r.applied_at).getTime() || 0;
}

/**
 * Pure, stable sort of the loaded rows for the given key. Never mutates input.
 * The returned order is the single source of truth for both the table AND the
 * drawer's prev/next navigation snapshot.
 */
export function sortRows(
  rows: readonly PartnerApplication[],
  key: SortKey,
): PartnerApplication[] {
  const withIndex = rows.map((row, index) => ({ row, index }));
  const cmp = (a: PartnerApplication, b: PartnerApplication): number => {
    switch (key) {
      case "needs_action": {
        const ba = actionBucket(a.status);
        const bb = actionBucket(b.status);
        if (ba !== bb) return ba - bb;
        // submitted/under_review: oldest first (protect SLA);
        // decided: most-recent first.
        return ba === 2
          ? activityTime(b) - activityTime(a)
          : activityTime(a) - activityTime(b);
      }
      case "newest":
        return appliedTime(b) - appliedTime(a);
      case "oldest":
        return appliedTime(a) - appliedTime(b);
      case "best_match": {
        const sa = a.fit?.score ?? -1;
        const sb = b.fit?.score ?? -1;
        if (sb !== sa) return sb - sa; // highest fit first; unscored last
        return appliedTime(a) - appliedTime(b); // tie-break: oldest first
      }
      case "status": {
        const oa = STATUS_ORDER[a.status] ?? 99;
        const ob = STATUS_ORDER[b.status] ?? 99;
        if (oa !== ob) return oa - ob;
        return appliedTime(b) - appliedTime(a);
      }
      default:
        return 0;
    }
  };
  return withIndex
    .sort((x, y) => cmp(x.row, y.row) || x.index - y.index)
    .map((x) => x.row);
}

/* ---------------------------- Screening answers --------------------------- */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True when a screening-answer key is an opaque id (no question text to show). */
export function isOpaqueQuestionKey(key: string): boolean {
  return UUID_RE.test(key) || /^q?_?\d+$/i.test(key);
}
