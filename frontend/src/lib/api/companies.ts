import { api } from "./client";
import type { ApiListEnvelope } from "./types";
import type { JobSummary } from "./jobs";
import type { CompanyRating } from "./reviews";

/* ------------------------------- Wire types ------------------------------- */

/**
 * Public partner directory row. Mirrors the backend `CompanySummary`
 * projection — never carries owner/moderation internals. `logo_url` is
 * nullable; render an initials placeholder when it is null.
 */
/** Compact rating snippet included in the directory listing (overall only). */
export interface CompanyRatingSummary {
  overall_avg: number | null;
  review_count: number;
}

export interface CompanySummary {
  id: string;
  slug: string;
  display_name: string;
  logo_url: string | null;
  industry: string | null;
  company_size: string | null;
  headquarters_city: string | null;
  is_verified: boolean;
  trust_level: string;
  active_job_count: number;
  rating: CompanyRatingSummary | null;
}

/** Public partner detail. Adds profile copy + the company's open roles. */
export interface CompanyDetail extends CompanySummary {
  website_url: string | null;
  description: string | null;
  founded_year: number | null;
  verified_at: string | null;
  active_jobs: JobSummary[];
  /** Company-review aggregate (ADR-0013); null when no published reviews. */
  rating: CompanyRating | null;
}

/* --------------------------------- Calls ---------------------------------- */

export const companiesApi = {
  /** Public partner directory. Cursor pagination + keyword/industry filters. */
  list(opts?: {
    q?: string | null;
    industry?: string | null;
    cursor?: string | null;
    limit?: number;
  }): Promise<ApiListEnvelope<CompanySummary>> {
    return api.list<CompanySummary>("/companies", {
      skipAuth: true,
      query: {
        q: opts?.q ?? undefined,
        industry: opts?.industry ?? undefined,
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
      },
    });
  },

  /** Public partner detail by slug. Throws RESOURCE_NOT_FOUND (404) if not listable. */
  getBySlug(slug: string): Promise<CompanyDetail> {
    return api.get<CompanyDetail>(`/companies/${slug}`, { skipAuth: true });
  },
};
