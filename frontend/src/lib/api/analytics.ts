import { api } from "./client";

/**
 * Partner-analytics HTTP surface: the public job-engagement pixel (feeds the
 * `partner_job_metrics_daily` read model behind Partner Dashboard V2's
 * `job_performance` widget) and the permission-gated candidate-access
 * compliance log ("who viewed which CV").
 *
 * docs/PARTNER_RBAC_ANALYTICS_SPEC.md §"Recruiting Intelligence Read Models".
 */

export type JobEngagementEventType = "impression" | "cta_click" | "share_click";

export type JobEngagementSource =
  | "organic"
  | "search"
  | "recommendation"
  | "sponsored"
  | "invitation"
  | "direct";

export interface JobEngagementBody {
  event_type: JobEngagementEventType;
  source?: JobEngagementSource | null;
}

export interface JobEngagementResult {
  recorded: boolean;
}

/**
 * One row of the candidate-access audit log
 * (`partner_candidate_access_events`). Never carries candidate name/email —
 * only the application/job reference and the acting partner member, so this
 * view cannot itself become a second identity-leak surface.
 */
export type CandidateAccessEventType =
  | "application_opened"
  | "cv_previewed"
  | "cv_downloaded"
  | "identity_reveal_requested"
  | "identity_revealed_viewed";

export interface CandidateAccessLogItem {
  id: string;
  event_type: CandidateAccessEventType;
  application_id: string;
  job_title: string;
  actor_name: string | null;
  reason: string | null;
  occurred_at: string;
}

export interface CandidateAccessLog {
  items: CandidateAccessLogItem[];
}

export const analyticsApi = {
  /**
   * Public (optional-auth) engagement pixel. Fire-and-forget: this MUST NOT
   * block render. Only for signals with no other authoritative backend write
   * (a genuine detail view / save / apply are already recorded server-side) —
   * this pixel is for list-impression / CTA-click / share-click only.
   */
  recordJobEngagement(jobId: string, body: JobEngagementBody): Promise<JobEngagementResult> {
    return api.post<JobEngagementResult>(`/analytics/jobs/${jobId}/engagement`, body);
  },

  /**
   * "Who accessed which candidate" compliance/security view. 403s for a
   * partner member without `candidate_identity:download_cv` or
   * `analytics:view_clicks` — the UI must show a locked state, not retry.
   */
  candidateAccessLog(limit?: number): Promise<CandidateAccessLog> {
    return api.get<CandidateAccessLog>("/analytics/partner/candidate-access-log", {
      query: { limit },
    });
  },
};
