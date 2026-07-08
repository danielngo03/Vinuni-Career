import { api } from "./client";
import type { CompanySummary } from "./companies";
import type { EventSummary } from "./events";
import type { JobSummary } from "./jobs";
import type {
  JobRecommendations,
  MarketplaceBanner,
  PopularRole,
  RecommendedEvent,
  TrustModule,
} from "./discovery";

/* ------------------------------- Wire types ------------------------------- */

/** Live aggregate counters for the public gateway. Null when unavailable. */
export interface MarketplaceMetrics {
  active_jobs: number;
  companies: number;
  open_for_applications: number;
}

/** One trailing day in the 30-day new-jobs series (oldest-first). */
export interface JobsTrendPoint {
  /** ISO date (YYYY-MM-DD). */
  date: string;
  /** New jobs published on this day. */
  count: number;
}

/**
 * 30-day momentum for newly published jobs. Null when the trend cannot be
 * computed — callers must hide the trend tile entirely rather than fake it.
 * `delta_pct` is the percent change vs the previous 30-day window and is null
 * when there is no comparable baseline; render the sparkline with no arrow.
 */
export interface JobsTrend {
  new_jobs_30d: number;
  /** Exactly the trailing days, oldest-first. */
  series: JobsTrendPoint[];
  delta_pct: number | null;
}

/**
 * Public career gateway overview. Any inventory list may be empty — callers
 * must hide the corresponding section rather than render placeholder content.
 * `metrics` is null when aggregates are unavailable; do not render dashes.
 * `jobs_trend` is null when momentum is unavailable; hide the trend tile.
 */
export interface MarketplaceOverview {
  metrics: MarketplaceMetrics | null;
  jobs_trend: JobsTrend | null;
  sponsored_jobs: JobSummary[];
  featured_jobs: JobSummary[];
  recent_jobs: JobSummary[];
  spotlight_companies: CompanySummary[];
  /**
   * Real upcoming/sponsored/featured events for the gateway events strip. Each
   * array is empty when nothing qualifies — the strip hides rather than faking
   * inventory. Sponsored/featured come from the real flags on each summary.
   */
  upcoming_events: EventSummary[];
  sponsored_events: EventSummary[];
  featured_events: EventSummary[];

  /* --- Discovery / recommendation / sponsored rails (spec §6/§8) --------- */

  /**
   * Top campaign banner (hero slot): a live partner placement OR a VinUni-curated
   * fallback (spec §5). Null when nothing fills the slot — hide the banner (never
   * fabricate). Carries the polished, class-keyed `disclosure.label` and, when
   * available, an approved `creative` for the editorial image.
   */
  hero_campaign: MarketplaceBanner | null;
  /**
   * The recommended-jobs rail. Label the rail by `recommended_jobs.source`:
   * "recommended" -> personalized, else honest "recent"/"popular" fallback.
   */
  recommended_jobs: JobRecommendations;
  /** Upcoming events with honest source + reason codes. Hide if empty. */
  recommended_events: RecommendedEvent[];
  /** Companies ranked from coarse session signals; falls back to spotlight ordering. */
  recommended_companies: CompanySummary[];
  /** Right-rail banner (second slot): live placement or curated fallback. Null = hide. */
  sponsored_banner: MarketplaceBanner | null;
  /** University-curated employer spotlight. Empty = hide. */
  employer_spotlight: CompanySummary[];
  /** Real role-family aggregates for search chips. Empty = hide the rail. */
  popular_roles: PopularRole[];
  /** Static trust modules localized by `key`. NO fabricated numbers. */
  trust_modules: TrustModule[];
}

/* --------------------------------- Calls ---------------------------------- */

export const marketplaceApi = {
  /** Public, unauthenticated gateway overview. */
  overview(): Promise<MarketplaceOverview> {
    return api.get<MarketplaceOverview>("/marketplace/overview", {
      skipAuth: true,
    });
  },
};
