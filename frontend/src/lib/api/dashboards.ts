import { api } from "./client";
import type { JobRecommendations } from "./discovery";

/* ------------------------------- Shared shapes ---------------------------- */

/**
 * A "what should I do now" rail item. `key` is a stable, persona-scoped action
 * code mapped to a localized label + icon on the client; `href` deep-links into
 * the real workflow; `count` is an optional badge (null when not applicable).
 * Actions are only present when relevant — the UI hides anything not returned.
 */
export interface DashboardNextAction {
  key: string;
  href: string;
  count: number | null;
}

/* -------------------------------- Student --------------------------------- */

export interface StudentDashboardMetrics {
  applications_total: number;
  applications_active: number;
  profile_completion_pct: number;
  cv_count: number;
  alert_count: number;
}

export interface StudentRecentApplication {
  id: string;
  job_title: string | null;
  company_name: string | null;
  status: string;
  status_label: string;
  submitted_at: string;
}

export interface StudentRevealRequestItem {
  application_id: string;
  job_title: string | null;
  company_name: string | null;
  requested_at: string;
}

export interface StudentUpcomingInterview {
  id: string;
  application_id: string;
  job_title: string | null;
  company_name: string | null;
  title: string | null;
  mode: string;
  scheduled_at: string;
  duration_minutes: number;
  location: string | null;
}

export interface CompletionSection {
  key: string;
  done: boolean;
  weight: number;
  href: string;
}

export interface StudentUpcomingEvent {
  event_id: string;
  title: string;
  event_type: string;
  event_type_label: string;
  format: string;
  format_label: string;
  starts_at: string | null;
  ends_at: string | null;
  venue_name: string | null;
  registration_status: string;
  registration_status_label: string;
}

export interface StudentDashboard {
  metrics: StudentDashboardMetrics;
  completion_sections: CompletionSection[];
  next_actions: DashboardNextAction[];
  applications_recent: StudentRecentApplication[];
  reveal_requests_pending: StudentRevealRequestItem[];
  upcoming_interviews: StudentUpcomingInterview[];
  upcoming_events: StudentUpcomingEvent[];
  /**
   * Honest recommendation rail. Label by `source`: a CV-less student gets
   * `recent`/`popular` (NEVER "recommended"); a student with CV/preferences gets
   * `recommended` with reason codes + product fit score.
   */
  recommended_jobs: JobRecommendations;
}

/* -------------------------------- Partner --------------------------------- */

export interface PartnerDashboardMetrics {
  jobs_active: number;
  jobs_draft: number;
  jobs_pending_review: number;
  applications_total: number;
  reveals_pending_response: number;
}

export interface PartnerJobAttentionItem {
  id: string;
  title: string;
  status: string;
  status_label: string;
  application_count: number;
}

export interface PartnerRecentApplication {
  id: string;
  job_title: string | null;
  /** Anonymous handle, e.g. "UV-60ADB170". Never a real candidate name. */
  candidate_handle: string;
  status: string;
  status_label: string;
  submitted_at: string;
}

export interface PartnerDashboard {
  org_name: string;
  metrics: PartnerDashboardMetrics;
  next_actions: DashboardNextAction[];
  jobs_attention: PartnerJobAttentionItem[];
  applications_recent: PartnerRecentApplication[];
}

/* ----------------------------- Partner ops (V2) ---------------------------- */

/**
 * Partner Dashboard V2 (`GET /dashboards/partner/ops`,
 * docs/PARTNER_RBAC_ANALYTICS_SPEC.md §"Partner Dashboard V2 Contract").
 * Additive to {@link PartnerDashboard} (v1) — every widget below degrades
 * independently and never fabricates data: absent projections report an honest
 * `basis`/`reason`, and grant-gated widgets report `locked: true` + `reason`
 * instead of a fake zero.
 */
export interface PartnerOpsTodo {
  key: string;
  href: string;
  count: number | null;
  priority: "high" | "medium" | "low";
}

/** Org-wide funnel totals over the trailing window — present only when the
 * viewer has `analytics:view_job_metrics` AND the projection has rows. */
export interface PartnerEngagementTotals {
  impressions: number;
  detail_views: number;
  cta_clicks: number;
  apply_starts: number;
  applications_submitted: number;
  save_clicks: number;
  share_clicks: number;
  conversion_rate_pct: number | null;
}

export type PartnerEngagementWidget =
  | ({ available: true; basis: "job_metrics_daily" } & PartnerEngagementTotals)
  | { available: false; basis: "application_counts_only"; reason: "no_metrics_yet" }
  | { available: false; basis: "locked"; reason: "missing_grant" };

export interface PartnerOpsMetrics {
  jobs_active: number;
  jobs_draft: number;
  jobs_pending_review: number;
  applications_total: number;
  reveals_pending_response: number;
  engagement: PartnerEngagementWidget;
}

export interface PartnerJobPerformanceSourceMix {
  organic: number;
  search: number;
  recommendation: number;
  sponsored: number;
  invitation: number;
  direct: number;
}

/** One job's funnel row when the `job_metrics_daily` projection has data. */
export interface PartnerJobPerformanceRow {
  job_id: string;
  title: string;
  impressions: number;
  detail_views: number;
  cta_clicks: number;
  apply_starts: number;
  applications_submitted: number;
  save_clicks: number;
  share_clicks: number;
  conversion_rate_pct: number | null;
  source_mix: PartnerJobPerformanceSourceMix;
}

/** Honest application-count-only fallback row (no click/view projection yet). */
export interface PartnerTopJobRow {
  job_id: string;
  title: string;
  application_count: number;
}

export type PartnerJobPerformanceWidget =
  | { locked: true; reason: "missing_grant"; items: [] }
  | { locked: false; basis: "job_metrics_daily"; items: PartnerJobPerformanceRow[] }
  | { locked: false; basis: "application_counts_only"; items: PartnerTopJobRow[] };

export interface PartnerActivityItem {
  action: string;
  action_label: string;
  resource_type: string;
  resource_id: string | null;
  actor_name: string | null;
  occurred_at: string;
}

export interface PartnerAccessAlertItem {
  code: "cv_download_spike" | "reveal_spike";
  label: string;
  actor_name: string | null;
  count: number;
  window_hours: number;
}

export type PartnerAccessAlertsWidget =
  | { locked: true; reason: "missing_grant"; items: [] }
  | { locked: false; items: PartnerAccessAlertItem[] };

/** Read-only capability summary driving every locked-widget reason shown above. */
export interface PartnerRbacSummary {
  is_org_admin: boolean;
  grants: Record<string, boolean>;
  hidden_widgets: string[];
}

/** Advisory-only heuristic recommendation. Never auto-executed; never claims to
 * be a live model call. `advisory_only` is always true — render as guidance. */
export interface PartnerAiRecommendation {
  code: string;
  message_vi: string;
  message_en: string;
  advisory_only: true;
}

export interface PartnerDashboardOps {
  org_name: string | null;
  todos: PartnerOpsTodo[];
  metrics: PartnerOpsMetrics;
  job_performance: PartnerJobPerformanceWidget;
  team_activity: PartnerActivityItem[];
  access_alerts: PartnerAccessAlertsWidget;
  rbac_summary: PartnerRbacSummary;
  ai_recommendations: PartnerAiRecommendation[];
}

/* ------------------------------- University -------------------------------- */

export interface UniversityDashboardMetrics {
  jobs_pending_moderation: number;
  partners_pending: number;
  partners_active: number;
  jobs_active_total: number;
}

export interface UniversityModerationItem {
  id: string;
  title: string;
  company_name: string | null;
  submitted_at: string;
}

export interface UniversityPartnerRequestItem {
  id: string;
  company_name: string | null;
  submitted_at: string;
}

export interface UniversityDashboard {
  metrics: UniversityDashboardMetrics;
  next_actions: DashboardNextAction[];
  moderation_queue_recent: UniversityModerationItem[];
  partner_requests_recent: UniversityPartnerRequestItem[];
}

/* ------------------------------- Analytics -------------------------------- */

export interface AnalyticsFunnelItem {
  status: string;
  count: number;
}

export interface AnalyticsTopJob {
  job_id: string;
  title: string;
  application_count: number;
}

export interface AnalyticsMonthlyPoint {
  month: string;
  count: number;
}

export interface PartnerAnalytics {
  funnel: AnalyticsFunnelItem[];
  top_jobs: AnalyticsTopJob[];
  monthly_trend: AnalyticsMonthlyPoint[];
}

/* ------------------- Recruiting funnel analytics (§6, NEW) ---------------- */

/**
 * Recruiting-funnel analytics read (`GET /dashboards/partner/analytics/
 * recruiting-funnel`, design-spec §6). Extends the thin {@link PartnerAnalytics}
 * funnel with step-over-step conversion, per-stage outcomes, and time-to-hire /
 * time-in-stage medians. Every metric degrades honestly: `low_signal` and
 * `median_days: null` mean "not enough data" — the UI renders an em dash / an
 * honest note, never a fabricated number.
 */
export interface RecruitingFunnelStage {
  stage: string;
  label: string;
  count: number;
  /** Conversion vs the previous stage (0–100); null for the first stage. */
  conversion_from_prev_pct: number | null;
}

export interface RecruitingStageOutcome {
  stage_type: string;
  label: string;
  entered: number;
  advanced: number;
  rejected: number;
  rolled_back: number;
  active: number;
  pass_rate_pct: number | null;
}

export interface TimeBucket {
  label: string;
  count: number;
}

export interface TimeToHire {
  sample_size: number;
  median_days: number | null;
  low_signal: boolean;
  buckets: TimeBucket[];
}

export interface TimeInStageItem {
  stage_type: string;
  label: string;
  median_days: number | null;
  sample_size: number;
  low_signal: boolean;
}

export interface PartnerRecruitingFunnel {
  funnel: RecruitingFunnelStage[];
  stage_outcomes: RecruitingStageOutcome[];
  time_to_hire: TimeToHire;
  time_in_stage: TimeInStageItem[];
}

/* --------------------- Advertising performance (§6, NEW) ------------------ */

/**
 * Ad delivery read (`GET /dashboards/partner/analytics/advertising`, design-spec
 * §6). Delivery counters (`impressions`/`clicks`/`apply_starts`) come from the
 * real ad-event projection; `ctr_pct` is null until there is enough delivery to
 * compute honestly (render "—", never 0-as-a-rate). `spend` is a frozen decimal
 * string. `disclosure_class` drives the non-removable public sponsored label.
 */
export interface AdvertisingCampaignRow {
  placement_id: string;
  target_title: string | null;
  placement_type_label: string;
  status_label: string;
  disclosure_class: string;
  impressions: number;
  clicks: number;
  apply_starts: number;
  ctr_pct: number | null;
  spend: string | number | null;
  currency: string;
}

export interface AdvertisingPerformanceTotals {
  impressions: number;
  clicks: number;
  apply_starts: number;
  ctr_pct: number | null;
  spend: string | number | null;
  currency: string;
  active_count?: number;
  campaigns?: number;
}

export interface PartnerAdvertisingPerformance {
  campaigns: AdvertisingCampaignRow[];
  totals: AdvertisingPerformanceTotals;
}

/* ---------------------- University reports/KPIs --------------------------- */

export interface UniversityPlatformKpis {
  students: number;
  partner_members: number;
  jobs: number;
  applications: number;
  events: number;
}

export interface UniversityMonthlyPoint {
  month: string;
  label: string;
  count: number;
}

export interface UniversityPlatformStats {
  kpis: UniversityPlatformKpis;
  monthly_applications: UniversityMonthlyPoint[];
}

/* --------------------------- Pipeline overview ----------------------------- */

export interface PipelineJobRow {
  job_id: string;
  title: string;
  status: string;
  deadline: string | null;
  total: number;
  active_total: number;
  rejected: number;
  withdrawn: number;
}

export interface PartnerPipelineOverview {
  jobs: PipelineJobRow[];
  total_active: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const dashboardsApi = {
  /** Student command center projection (authenticated student/alumni). */
  student(): Promise<StudentDashboard> {
    return api.get<StudentDashboard>("/dashboards/student");
  },

  /** Partner recruiting-ops projection (authenticated org member). */
  partner(): Promise<PartnerDashboard> {
    return api.get<PartnerDashboard>("/dashboards/partner");
  },

  /**
   * Partner Dashboard V2 — todos, richer metrics, job performance, team
   * activity, access alerts, RBAC summary, and advisory AI recommendations.
   * Additive to {@link PartnerDashboard}; never replaces it.
   */
  partnerOps(): Promise<PartnerDashboardOps> {
    return api.get<PartnerDashboardOps>("/dashboards/partner/ops");
  },

  /** University operations projection (authenticated university staff). */
  university(): Promise<UniversityDashboard> {
    return api.get<UniversityDashboard>("/dashboards/university");
  },

  /** Partner analytics — application funnel, top jobs, monthly trend. */
  partnerAnalytics(): Promise<PartnerAnalytics> {
    return api.get<PartnerAnalytics>("/dashboards/partner/analytics");
  },

  /**
   * Recruiting-funnel analytics (§6) — step conversion, per-stage outcomes,
   * time-to-hire / time-in-stage. Optional trailing-window range (ISO dates).
   */
  partnerRecruitingFunnel(params?: {
    from?: string;
    to?: string;
  }): Promise<PartnerRecruitingFunnel> {
    return api.get<PartnerRecruitingFunnel>(
      "/dashboards/partner/analytics/recruiting-funnel",
      { query: { from: params?.from, to: params?.to } },
    );
  },

  /** Advertising delivery read (§6) — per-campaign impressions/clicks/CTR/spend. */
  partnerAdvertisingPerformance(): Promise<PartnerAdvertisingPerformance> {
    return api.get<PartnerAdvertisingPerformance>(
      "/dashboards/partner/analytics/advertising",
    );
  },

  /** Partner pipeline overview — per-job candidate counts. */
  partnerPipelineOverview(): Promise<PartnerPipelineOverview> {
    return api.get<PartnerPipelineOverview>("/dashboards/partner/pipeline-overview");
  },

  /** University platform KPI reports. */
  universityReports(): Promise<UniversityPlatformStats> {
    return api.get<UniversityPlatformStats>("/dashboards/university/reports");
  },
};
