import { api } from "./client";

/* -------------------------------------------------------------------------- */
/* Types                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Response for `GET /admin/analytics/kpis`.
 * Platform-wide headcount and activity snapshot.
 */
export interface AdminAnalyticsKpis {
  students: number;
  partner_members: number;
  university_staff: number;
  jobs: number;
  applications: number;
  events: number;
}

/**
 * One stage row from `GET /admin/analytics/funnel`.
 * `conversion_from_previous` is null for the first stage (no previous stage).
 */
export interface AdminAnalyticsFunnelStage {
  stage:
    | "job_views"
    | "job_applies"
    | "applications_submitted"
    | "under_review"
    | "interview"
    | "offer"
    | "hired"
    | "rejected";
  count: number;
  conversion_from_previous: number | null;
}

export interface AdminAnalyticsFunnel {
  range_days: number;
  stages: AdminAnalyticsFunnelStage[];
}

/**
 * One day row from `GET /admin/analytics/growth`.
 * One entry per calendar day, ascending, gap-filled with zeros.
 */
export interface AdminAnalyticsGrowthRow {
  day: string; // "YYYY-MM-DD"
  signups: number;
  applications: number;
  active_users: number;
}

export interface AdminAnalyticsGrowth {
  range_days: number;
  series: AdminAnalyticsGrowthRow[];
}

/* -------------------------------------------------------------------------- */
/* API object                                                                 */
/* -------------------------------------------------------------------------- */

export const adminAnalyticsApi = {
  /**
   * Platform-wide KPI snapshot.
   * `GET /admin/analytics/kpis`
   */
  kpis(): Promise<AdminAnalyticsKpis> {
    return api.get<AdminAnalyticsKpis>("/admin/analytics/kpis");
  },

  /**
   * Recruitment funnel for the given range.
   * `GET /admin/analytics/funnel?range_days=<N>`
   */
  funnel(rangeDays: number): Promise<AdminAnalyticsFunnel> {
    return api.get<AdminAnalyticsFunnel>("/admin/analytics/funnel", {
      query: { range_days: rangeDays },
    });
  },

  /**
   * Platform growth time-series.
   * `GET /admin/analytics/growth?range_days=<N>`
   * Returns one row per day, ascending, gap-filled.
   */
  growth(rangeDays: number): Promise<AdminAnalyticsGrowth> {
    return api.get<AdminAnalyticsGrowth>("/admin/analytics/growth", {
      query: { range_days: rangeDays },
    });
  },
};
