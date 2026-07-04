/**
 * Company reviews API (Module 13 / ADR-0013).
 *
 * Public list + student CRUD + report; university moderation under /admin/reviews.
 * The public payload never includes a reviewer id and masks the author when the
 * review is anonymous. Labels (trust/status) arrive already localized.
 */
import { api } from "./client";

export interface ReviewRatings {
  overall: number;
  work_life_balance: number;
  culture_values: number;
  compensation: number;
  career_growth: number;
  interview_experience: number | null;
}

export interface CompanyReview {
  id: string;
  title: string;
  body: string;
  pros: string | null;
  cons: string | null;
  ratings: ReviewRatings;
  trust_label: string;
  is_anonymous: boolean;
  author_name: string;
  helpful_count: number;
  /** null when caller is a guest; true/false when authenticated. */
  my_vote: boolean | null;
  partner_response: string | null;
  partner_response_at: string | null;
  published_at: string | null;
  created_at: string | null;
}

/** Author's own view — adds status + version for edit/optimistic lock. */
export interface OwnReview extends Omit<CompanyReview, "author_name"> {
  status: string;
  status_label: string;
  version: number;
}

/** Moderator view — author identity always present (accountability). */
export interface ModerationReview extends CompanyReview {
  status: string;
  status_label: string;
  version: number;
  report_count: number;
  org_id: string;
}

/** Aggregate block embedded on the public company profile. */
export interface CompanyRating {
  review_count: number;
  overall_avg: number | null;
  overall_raw_avg: number | null;
  categories: {
    work_life_balance: number | null;
    culture_values: number | null;
    compensation: number | null;
    career_growth: number | null;
    interview_experience: number | null;
  };
  distribution: Record<string, number>;
}

export interface ReviewWriteBody {
  title: string;
  body: string;
  pros?: string | null;
  cons?: string | null;
  is_anonymous: boolean;
  ratings: ReviewRatings;
  version?: number;
}

export interface ModerationQueue {
  items: ModerationReview[];
  total: number;
  counts: { pending: number; flagged: number };
}

export const reviewsApi = {
  listForCompany(slug: string, locale: string): Promise<{ items: CompanyReview[]; count: number }> {
    return api.get(`/companies/${slug}/reviews`, {
      skipAuth: true,
      query: { locale },
    });
  },
  getMine(slug: string, locale: string): Promise<OwnReview> {
    return api.get(`/companies/${slug}/reviews/mine`, { query: { locale } });
  },
  submit(slug: string, body: ReviewWriteBody, locale: string): Promise<OwnReview> {
    return api.post(`/companies/${slug}/reviews`, body, { query: { locale } });
  },
  update(reviewId: string, body: ReviewWriteBody, locale: string): Promise<OwnReview> {
    return api.patch(`/reviews/${reviewId}`, body, { query: { locale } });
  },
  remove(reviewId: string): Promise<void> {
    return api.delete(`/reviews/${reviewId}`);
  },
  report(reviewId: string, reasonCode: string, note?: string): Promise<{ status: string }> {
    return api.post(`/reviews/${reviewId}/report`, { reason_code: reasonCode, note });
  },
  /** Mark a review helpful. Returns updated count + my_vote. */
  voteHelpful(reviewId: string): Promise<{ helpful_count: number; my_vote: boolean }> {
    return api.post(`/reviews/${reviewId}/helpful`, {});
  },
  /** Remove helpful vote. Returns updated count + my_vote. */
  removeHelpfulVote(reviewId: string): Promise<{ helpful_count: number; my_vote: boolean }> {
    return api.delete(`/reviews/${reviewId}/helpful`);
  },
  /** Partner adds public response to a review scoped to their org. */
  addPartnerResponse(reviewId: string, response: string): Promise<{ status: string }> {
    return api.post(`/reviews/${reviewId}/response`, { response });
  },
  // University moderation
  moderationQueue(status: string | undefined, locale: string): Promise<ModerationQueue> {
    return api.get("/admin/reviews", {
      query: { status: status ?? undefined, locale },
    });
  },
  publish(reviewId: string, locale: string): Promise<ModerationReview> {
    return api.post(`/admin/reviews/${reviewId}/publish`, {}, { query: { locale } });
  },
  removeByModerator(reviewId: string, reason: string, note: string | undefined, locale: string): Promise<ModerationReview> {
    return api.post(`/admin/reviews/${reviewId}/remove`, { reason, note }, { query: { locale } });
  },
  restore(reviewId: string, locale: string): Promise<ModerationReview> {
    return api.post(`/admin/reviews/${reviewId}/restore`, {}, { query: { locale } });
  },
};
