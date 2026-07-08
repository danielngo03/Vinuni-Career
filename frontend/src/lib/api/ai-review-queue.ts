import { api, apiFetch } from "./client";
import type { ApiEnvelope } from "./types";

/* ------------------------------- Wire types ------------------------------- */

export type AiReviewItemType = "job" | "event";

/**
 * A job or event that AI/rule moderation FLAGGED for a human's final say (B-579).
 * The flag is advisory — a moderator upholds it (rejects the item) or dismisses
 * it (clears the flag). Only user-safe reason LABELS are exposed here; no model,
 * confidence, provider, or token internals ever appear on this surface.
 */
export interface AiReviewQueueItem {
  item_type: AiReviewItemType;
  id: string;
  title: string;
  org_id: string;
  status: string;
  status_label: string;
  moderation_status: string;
  moderation_status_label?: string | null;
  /** Structured moderation reason code (stable key), or null. Not shown raw. */
  flag_reason_code?: string | null;
  /** Localized, user-safe flag reason label — the only reason text to render. */
  flag_reason_label?: string | null;
  /** Optional free-text moderation note attached to the flag. */
  flag_note?: string | null;
  flagged_at?: string | null;
  submitted_at?: string | null;
  /** Whether a human moderator has already engaged with (claimed) the item. */
  human_acted?: boolean;
  claimed_at?: string | null;
  /** Backend-authoritative deep link to the item's record. */
  detail_url: string;
  due_by?: string | null;
  age_hours?: number | null;
  is_overdue?: boolean;
}

export interface AiReviewQueueCounts {
  job: number;
  event: number;
  total: number;
}

export interface AiReviewQueueResult {
  items: AiReviewQueueItem[];
  counts: AiReviewQueueCounts;
}

/** Result of a human uphold/dismiss decision on a flag. */
export interface AiReviewDecisionResult {
  item_type: AiReviewItemType;
  decision: "uphold" | "dismiss";
  item: Record<string, unknown>;
}

/* --------------------------------- Calls ---------------------------------- */

export const aiReviewQueueApi = {
  /**
   * List flagged jobs + events awaiting human review, plus badge counts. The
   * counts travel in the envelope `meta` alongside the item list.
   */
  async list(opts?: {
    limit?: number;
    locale?: string;
  }): Promise<AiReviewQueueResult> {
    const res = await apiFetch<ApiEnvelope<AiReviewQueueItem[]>>(
      "/university/moderation/ai-review-queue",
      {
        method: "GET",
        query: { limit: opts?.limit, locale: opts?.locale },
      },
    );
    const counts = (res.meta?.counts as AiReviewQueueCounts | undefined) ?? {
      job: 0,
      event: 0,
      total: res.data.length,
    };
    return { items: res.data, counts };
  },

  /** Lightweight badge count (drives the moderation "AI review" tab badge). */
  counts(): Promise<AiReviewQueueCounts> {
    return api.get<AiReviewQueueCounts>(
      "/university/moderation/ai-review-queue/counts",
    );
  },

  /**
   * Uphold the AI flag — the human agrees, rejecting the item. A non-empty
   * reason is always required; `reason_code` optionally overrides the flag's own
   * structured reason on the resulting reject.
   */
  uphold(
    itemType: AiReviewItemType,
    id: string,
    body: { reason: string; reason_code?: string | null },
    locale?: string,
  ): Promise<AiReviewDecisionResult> {
    return api.post<AiReviewDecisionResult>(
      `/university/moderation/ai-review-queue/${itemType}/${id}/uphold`,
      body,
      { query: locale ? { locale } : undefined },
    );
  },

  /** Dismiss the AI flag — the human overrides it, clearing the flag. */
  dismiss(
    itemType: AiReviewItemType,
    id: string,
    body: { reason: string },
    locale?: string,
  ): Promise<AiReviewDecisionResult> {
    return api.post<AiReviewDecisionResult>(
      `/university/moderation/ai-review-queue/${itemType}/${id}/dismiss`,
      body,
      { query: locale ? { locale } : undefined },
    );
  },
};
