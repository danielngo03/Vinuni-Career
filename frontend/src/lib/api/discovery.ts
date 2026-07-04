import { api, apiFetch } from "./client";
import type { EventSummary } from "./events";
import type { JobSummary } from "./jobs";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Inventory class of a ranked item / list. Mirrors the backend ranking source
 * vocabulary (`discovery/domain/ranking.py`). `recommended` is used ONLY when a
 * genuine personalization signal exists; otherwise the backend honestly falls
 * back to `recent` / `popular`. `sponsored` is paid inventory (disclosure
 * required); `curated` is university-curated.
 */
export type RecoSource =
  | "recommended"
  | "recent"
  | "popular"
  | "sponsored"
  | "curated";

/**
 * User-safe coded reason for why an item appears. Localized on the client by
 * {@link ReasonChips}. `cv_fit.score` is a 0-100 PRODUCT fit score — never a
 * model/AI confidence. Unknown future codes are tolerated (rendered as nothing).
 */
export type ReasonCode =
  | { code: "cv_fit"; score: number; cv_id: string; cv_title: string }
  | { code: "preferred_job_type"; value: string }
  | { code: "preferred_location"; value: string }
  | { code: "preferred_field"; value: string }
  | { code: "matches_search"; term: string }
  | { code: "similar_role" }
  | { code: "similar_industry"; value: string }
  | { code: "skill_match"; skills: string[] }
  | { code: "saved_affinity" }
  | { code: "verified_employer" }
  | { code: "deadline_soon"; days: number }
  | { code: "popular" }
  | { code: "recent" }
  | { code: string; [k: string]: unknown };

/** Non-removable sponsored disclosure carried on paid inventory. */
export interface SponsoredDisclosure {
  /** Internal code, e.g. "sponsored". Not shown raw to users. */
  code: string;
  /** Localized, NON-REMOVABLE label, e.g. "Được tài trợ" / "Sponsored". */
  label: string;
  is_sponsored: boolean;
}

/**
 * Public inventory class a campaign placement may carry (spec §4). Only
 * `paid_sponsored` is PAID — its disclosure is non-removable. The others are
 * truthful editorial/partnership classes and MUST NEVER be styled as paid.
 */
export type DisclosureClass =
  | "paid_sponsored"
  | "university_curated"
  | "strategic_partner"
  | "featured";

/**
 * Polished, class-keyed public disclosure (spec §4/§7). `label` is the
 * server-localized polished text (e.g. "Đối tác tài trợ" / "VinUni tuyển chọn").
 * `is_paid` is true only for `paid_sponsored`; `is_removable` is false for paid
 * inventory so its disclosure always shows. `is_sponsored`/`code` are retained
 * for backward compatibility with older sponsored consumers.
 */
export interface InventoryDisclosure {
  class: DisclosureClass | string;
  label: string;
  is_paid: boolean;
  is_removable: boolean;
  is_sponsored: boolean;
  code?: string;
}

/**
 * An approved, validated campaign creative for a banner slot (spec §5). The
 * `image_url` is the public serve route (never a storage key). `focal_point`
 * drives the responsive object-position crop; `alt` is the localized alt text.
 */
export interface CampaignCreative {
  image_url: string;
  alt: string | null;
  focal_point: { x: number; y: number };
  click_target: string | null;
}

/**
 * A resolved marketplace banner slot (hero / right-rail). A `partner` source is
 * a live placement carrying a `job` target and — when uploaded + approved — a
 * `creative`; a `vinuni_curated` source is the university fallback (curated,
 * NEVER paid) with a `creative` but no `job`. The slot is hidden when neither a
 * creative nor a job is present. `sponsored_disclosure` is the backward-compat
 * alias the API still emits.
 */
export interface MarketplaceBanner {
  placement_id: string | null;
  slot: string;
  source: "partner" | "vinuni_curated" | string;
  target_type?: "job";
  job: JobSummary | null;
  creative: CampaignCreative | null;
  disclosure: InventoryDisclosure;
  sponsored_disclosure?: SponsoredDisclosure | InventoryDisclosure;
}

/* ------------------------------- Wire types ------------------------------- */

/**
 * A ranked public job — a {@link JobSummary} enriched with the recommendation
 * envelope. `score` is a 0-100 product fit score. `sponsored_disclosure` /
 * `placement_id` are present only when `source === "sponsored"`.
 */
export interface RecommendedJob extends JobSummary {
  score: number;
  source: RecoSource;
  reason_codes: ReasonCode[];
  recommended_cv_id: string | null;
  sponsored_disclosure: SponsoredDisclosure | null;
  placement_id: string | null;
}

/**
 * Recommendation feed (`GET /jobs/recommendations`, marketplace + dashboard
 * rails). `personalized` is true only when a real signal drove the ranking; the
 * UI labels the rail by `source` (never "recommended" for a recent/popular
 * fallback). `items` is empty when nothing is eligible — hide the rail.
 */
export interface JobRecommendations {
  source: RecoSource;
  personalized: boolean;
  items: RecommendedJob[];
}

/** Similar public jobs for a seed (`GET /jobs/{id}/similar`). Hide if empty. */
export interface SimilarJobs {
  job_id: string;
  items: RecommendedJob[];
}

/** An upcoming event enriched with an honest source + reason codes. */
export interface RecommendedEvent extends EventSummary {
  source: string;
  reason_codes: ReasonCode[];
}

/**
 * A sponsored placement banner (homepage hero / right-rail). The job target is
 * eligibility-filtered server-side; the disclosure is non-removable.
 */
export interface SponsoredBanner {
  placement_id: string;
  target_type: "job";
  job: JobSummary;
  sponsored_disclosure: SponsoredDisclosure;
}

/** A real role-family aggregate for the "popular roles" search chips. */
export interface PopularRole {
  /** Coded family, e.g. "software_engineering". Localized on the client. */
  role_family: string;
  job_count: number;
  application_count: number;
}

/** A static, honest trust module (NO fabricated numbers). Localized by `key`. */
export interface TrustModule {
  key: string;
}

/* ----------------------------- Analytics events --------------------------- */

export type DiscoveryEventType =
  | "impression"
  | "click"
  | "view"
  | "apply_start"
  | "save_intent"
  | "event_register_intent";

export type DiscoveryTargetType = "job" | "event" | "company" | "banner";

/**
 * Inventory-classed surface. MUST stay in sync with the backend allowlist
 * (`discovery/domain/allowlist.py SOURCE_SURFACES`). Organic, recommended,
 * sponsored, and curated inventory are tracked under separate surfaces so
 * analytics never conflate them.
 */
export type DiscoverySourceSurface =
  // organic
  | "homepage_recent"
  | "homepage_popular"
  | "search"
  | "job_detail"
  | "job_detail_similar"
  | "event_detail"
  | "company_profile"
  | "mega_companies"
  | "mega_events"
  // recommended
  | "homepage_recommended"
  | "search_recommended"
  | "job_detail_recommended_cv"
  | "mega_jobs_recommended"
  // sponsored (disclosure required; placement_id retained)
  | "homepage_sponsored"
  | "search_sponsored"
  | "right_rail_banner"
  | "email_sponsored"
  | "mega_sponsored"
  // university-curated
  | "employer_spotlight"
  | "career_explore"
  | "university_curated";

/**
 * Coarse, privacy-safe signals merged onto the guest session to improve guest
 * recommendations. ONLY allowlisted keys survive server-side; NEVER send PII,
 * exact location, raw CV text, or third-party tracking IDs.
 */
export interface CoarseSignalTags {
  search_terms?: string[];
  categories?: string[];
  industries?: string[];
  role_families?: string[];
  company_ids?: string[];
  event_ids?: string[];
  work_mode?: string;
  city?: string;
  device_type?: string;
}

export interface DiscoveryEventInput {
  event_type: DiscoveryEventType;
  source_surface: DiscoverySourceSurface;
  target_type: DiscoveryTargetType;
  target_id: string;
  /** Sponsored placement ref — supply ONLY on sponsored surfaces/banners. */
  placement_id?: string | null;
  /** Stable dedupe key (>= 8 chars), e.g. `${renderId}:${targetId}:impression`. */
  idempotency_key: string;
  locale?: string;
  signal_tags?: CoarseSignalTags;
}

export interface SessionResetResult {
  reset: boolean;
  opt_out: boolean;
}

/* --------------------------------- Calls ---------------------------------- */

export const discoveryApi = {
  /**
   * Personalized (or honestly-fallback) job recommendations. Optional-auth: a
   * signed-in student gets CV-fit + preference reasons; a guest gets
   * session/popular reasons or a `recent`/`popular` fallback.
   */
  recommendations(opts?: {
    q?: string | null;
    limit?: number;
  }): Promise<JobRecommendations> {
    return api.get<JobRecommendations>("/jobs/recommendations", {
      skipAuth: false,
      query: {
        q: opts?.q ?? undefined,
        limit: opts?.limit,
      },
    });
  },

  /** Similar public jobs for a seed. Returns `items: []` when none are similar. */
  similar(jobId: string, limit?: number): Promise<SimilarJobs> {
    return api.get<SimilarJobs>(`/jobs/${jobId}/similar`, {
      skipAuth: false,
      query: { limit },
    });
  },

  /**
   * Record a privacy-safe discovery analytics event. Fire-and-forget: this MUST
   * NOT block render and swallows all errors. The first-party `vinuni_discovery`
   * cookie is set/refreshed by the server response. Returns `true` when the
   * event was sent (or deduped), `false` on transport failure.
   */
  async recordEvent(input: DiscoveryEventInput): Promise<boolean> {
    try {
      await apiFetch("/discovery/events", {
        method: "POST",
        json: input,
        // Optional-auth: let a signed-in student's token link the session, but
        // never fail if absent.
      });
      return true;
    } catch {
      return false;
    }
  },

  /**
   * Clear stored coarse interests for the discovery session (privacy reset).
   * `opt_out` additionally disables personalization and drops the cookie.
   */
  sessionReset(optOut = false): Promise<SessionResetResult> {
    return api.post<SessionResetResult>("/discovery/session/reset", {
      opt_out: optOut,
    });
  },
};
