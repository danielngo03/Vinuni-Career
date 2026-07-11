import { api } from "./client";

/**
 * Talent Pool — AI semantic candidate search over the CONSENTED CV pool.
 *
 * Owner decision (2026-07-10): the old passive "open-to-work list" + the
 * anonymous/blind-screening handshake are removed. A recruiter now expresses a
 * hiring NEED — a pasted/uploaded JD (posted OR not-yet-posted), skill/experience
 * filters, and/or free-text — and the backend returns the best-matching consented
 * candidates ranked by an AI semantic pipeline with a categorical match TIER and
 * human-readable match REASONS.
 *
 * Contract note: the backend NEVER returns (and this client never exposes) a raw
 * score/percentage/cosine, nor any provider/model/token/embedding internals. Tier
 * + reasons only. `source` tells us whether the AI path ran (`ai_semantic`) or a
 * deterministic keyword+filter fallback served the page (`keyword_fallback`); the
 * UI must surface the fallback honestly and never dress it up as AI.
 */

/** Categorical match strength, best → weakest. Never a numeric score. */
export type MatchTier = "excellent" | "strong" | "moderate" | "exploratory";

/** Which ranking path served the page. */
export type TalentSearchSource = "ai_semantic" | "keyword_fallback";

/** One ranked candidate card. RBAC-gated (candidate access) + audited server-side. */
export interface TalentMatch {
  /** Student profile id for the detail route. `null` when identity is unresolved. */
  profile_id: string | null;
  display_name: string;
  avatar_url: string | null;
  location_city: string | null;
  location_country: string | null;
  /** Categorical strength — drives the match-tier chip. */
  match_tier: MatchTier;
  /** Human-readable "why this candidate" bullets (no score, no PII). */
  match_reasons: string[];
  /** Candidate skills that matched the hiring need. */
  matched_skills: string[];
}

export interface TalentSearchPage {
  /** Total matched candidates for the criteria (post-dedup). */
  total: number | null;
  limit: number;
  offset: number;
}

export interface TalentSearchResult {
  items: TalentMatch[];
  source: TalentSearchSource;
  page: TalentSearchPage;
}

/**
 * A hiring need. At least ONE of `query_text` / `jd_text` / `skills` is required
 * (the backend returns 422 `VALIDATION_FAILED` otherwise). `jd_text` may carry an
 * EXTERNAL, not-yet-posted JD pasted by the recruiter.
 */
export interface TalentSearchBody {
  /** Free-text hiring need (max 1000 chars). */
  query_text?: string;
  /** Pasted/uploaded JD text, posted or not (max 8000 chars). */
  jd_text?: string;
  /** Required skills (max 25). */
  skills?: string[];
  /** Minimum relevant years of experience (0–50). */
  min_experience?: number;
  /** Page size, 1–20 (default 12 server-side). */
  limit?: number;
  /** Page offset (default 0). */
  offset?: number;
}

export const talentPoolApi = {
  /** POST /talent-pool/search — ranked consented candidates for a hiring need. */
  search(body: TalentSearchBody): Promise<TalentSearchResult> {
    return api.post<TalentSearchResult>("/talent-pool/search", body);
  },
};
