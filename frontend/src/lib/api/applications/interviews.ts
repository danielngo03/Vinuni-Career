import { api } from "../client";

/* -------------------------- Interviews (ADR-0006) ------------------------- */
/*
 * Interviews are PARTNER-INTERNAL scheduling. The candidate sees ONLY their own
 * upcoming-interview card (identity-safe; see `StudentInterviewCard`).
 * `meeting_link` is ATTENDEE-ONLY: the API returns it (non-null) only for the
 * candidate and the assigned interviewers, and never on the board glance — so
 * the type marks it optional/nullable and the UI renders it only when present.
 */

/** Interview delivery channel (ADR-0006 §1). The "round" is the pipeline stage. */
export type InterviewMode = "onsite" | "online" | "phone";

/** Mode picker order. */
export const INTERVIEW_MODES: readonly InterviewMode[] = [
  "onsite",
  "online",
  "phone",
];

/**
 * Interview lifecycle. V1 actively uses `scheduled | completed | cancelled |
 * no_show`; `rescheduled` is reserved (reschedule edits in place).
 */
export type InterviewStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "no_show"
  | "rescheduled"
  | string;

/** Outcome when completing an interview. */
export type InterviewOutcome = "completed" | "no_show";

/**
 * One assigned reviewer. `user_id` is a PARTNER-ORG member id (never the
 * student); `name` may be blank when the directory has no display name.
 */
export interface InterviewAssignee {
  user_id: string;
  name?: string | null;
}

/**
 * Partner-only gate summary attached to an interview's stage (ADR-0006 §2).
 * Extends the scorecard glance with the `score_threshold` average gate. NEVER on
 * any student projection.
 */
export interface InterviewEvaluation {
  submitted_count: number;
  required: number;
  gate_met: boolean;
  avg_overall: number | null;
  /** Present on a `score_threshold` stage; null otherwise. */
  threshold?: number | null;
  recommendation_summary: Record<string, number>;
}

/**
 * The partner interview view (partner-internal). `meeting_link` is present and
 * non-null ONLY for an attendee viewer (candidate + assigned interviewers);
 * otherwise it is absent/null — render it only when truthy.
 */
export interface Interview {
  id: string;
  application_id: string;
  stage_id: string;
  title: string | null;
  mode: InterviewMode | string;
  mode_label: string;
  scheduled_at: string;
  duration_minutes: number;
  /** Onsite address (onsite mode). Null otherwise. */
  location: string | null;
  /** ATTENDEE-ONLY: non-null only for the candidate + assigned interviewers. */
  meeting_link?: string | null;
  status: InterviewStatus;
  notes: string | null;
  assignees: InterviewAssignee[];
  evaluation: InterviewEvaluation | null;
  /** Optimistic-concurrency token; a stale value yields a 409 on reschedule. */
  version: number;
  created_at: string;
  updated_at: string;
}

/** `GET /applications/{id}/interviews` envelope. */
export interface InterviewListResult {
  application_id: string;
  interviews: Interview[];
}

/**
 * Schedule body. `online` requires `meeting_link`, `onsite` requires `location`
 * (else a field-scoped 422). `assignee_ids` are partner-org member user ids.
 */
export interface ScheduleInterviewBody {
  mode: InterviewMode;
  scheduled_at: string;
  assignee_ids?: string[];
  duration_minutes?: number;
  location?: string | null;
  meeting_link?: string | null;
  title?: string | null;
  notes?: string | null;
}

/** Reschedule / edit body. Omitted fields are left unchanged. */
export interface RescheduleInterviewBody {
  scheduled_at?: string;
  mode?: InterviewMode;
  location?: string | null;
  meeting_link?: string | null;
  title?: string | null;
  notes?: string | null;
  version?: number;
}

/**
 * The candidate's own upcoming-interview card. Carries the resolved
 * `location_or_link` (the meeting link for `online`, the address for `onsite`,
 * null for `phone`) — no assignee identities, no scores, no gate.
 */
export interface StudentInterviewCard {
  id: string;
  scheduled_at: string;
  mode: InterviewMode | string;
  mode_label: string;
  duration_minutes: number;
  location_or_link: string | null;
  status: InterviewStatus;
}

/* --------------------------------- Calls ---------------------------------- */

export const interviewsApi = {
  /**
   * Partner: schedule the candidate's interview for their current ACTIVE stage.
   * 409 `interview_exists` when an open interview already exists for the stage.
   * 422 (field-scoped) when `online` lacks a `meeting_link` / `onsite` lacks a
   * `location` / an assignee is not an org member. 404 cross-org. Returns the
   * partner interview view.
   */
  scheduleInterview(id: string, body: ScheduleInterviewBody): Promise<Interview> {
    return api.post<Interview>(`/applications/${id}/interviews`, body);
  },

  /** Partner: list the application's interviews (partner-internal). */
  listInterviews(id: string): Promise<InterviewListResult> {
    return api.get<InterviewListResult>(`/applications/${id}/interviews`);
  },

  /**
   * Partner: reschedule / edit an interview. Optimistic `version` (a stale value
   * yields a 409). Re-notifies the candidate + assignees on the server.
   */
  rescheduleInterview(
    id: string,
    interviewId: string,
    body: RescheduleInterviewBody,
  ): Promise<Interview> {
    return api.patch<Interview>(
      `/applications/${id}/interviews/${interviewId}`,
      body,
    );
  },

  /**
   * Partner: replace the interview's assignee set (partner-org member user ids).
   * A non-member id is a 422. Changes the advance gate's `required` denominator.
   */
  setInterviewAssignees(
    id: string,
    interviewId: string,
    userIds: string[],
  ): Promise<Interview> {
    return api.put<Interview>(
      `/applications/${id}/interviews/${interviewId}/assignees`,
      { assignee_ids: userIds },
    );
  },

  /** Partner: cancel an interview (frees the open slot). Optimistic `version`. */
  cancelInterview(
    id: string,
    interviewId: string,
    version?: number,
  ): Promise<Interview> {
    return api.post<Interview>(
      `/applications/${id}/interviews/${interviewId}/cancel`,
      version === undefined ? {} : { version },
    );
  },

  /** Partner: complete an interview (`completed` / `no_show`). Optimistic `version`. */
  completeInterview(
    id: string,
    interviewId: string,
    outcome: InterviewOutcome,
    version?: number,
  ): Promise<Interview> {
    return api.post<Interview>(
      `/applications/${id}/interviews/${interviewId}/complete`,
      version === undefined ? { outcome } : { outcome, version },
    );
  },
};
