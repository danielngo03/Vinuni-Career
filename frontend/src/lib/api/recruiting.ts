import { api } from "./client";

/* ------------------------ Recruiting boards (org-wide) -------------------- */
/*
 * Org-wide recruiting BOARD read models — an interviews board and an offers
 * board that span every job the caller can see (not scoped to one posting).
 * Each row is a leak-safe GLANCE: identities are the candidate's real handle
 * (applications are always identified), and NO provider/model/token internals
 * appear. Salary is present on the offers board because it is the recruiter's
 * OWN organisation's comp. Clicking a row opens the full, actionable
 * per-application panel (schedule/complete for interviews; submit/approve/send
 * for offers) which loads by `application_id`.
 */

/* -------------------------------- Interviews ------------------------------ */

/** Time-window scope for the interviews board. */
export type InterviewBoardScope = "upcoming" | "past" | "all";

/** Interview delivery channel (mirrors the per-application `InterviewMode`). */
export type InterviewBoardMode = "onsite" | "online" | "phone";

/** Interview lifecycle on the board glance. */
export type InterviewBoardStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "no_show";

/** One assigned interviewer (a partner-org member — never the candidate). */
export interface InterviewBoardAssignee {
  user_id: string;
  display_name: string;
}

/**
 * One interview row on the org-wide board. `meeting_link` is ATTENDEE-ONLY:
 * non-null only when the caller is an attendee (`is_attendee`), so a "Join"
 * affordance renders only when it is truthy.
 */
export interface InterviewBoardRow {
  id: string;
  application_id: string;
  job_id: string;
  job_title: string;
  candidate_handle: string;
  stage_name: string | null;
  mode: InterviewBoardMode;
  mode_label: string;
  scheduled_at: string;
  duration_minutes: number;
  status: InterviewBoardStatus;
  status_label: string;
  location: string | null;
  meeting_link: string | null;
  assignees: InterviewBoardAssignee[];
  assignee_count: number;
  is_attendee: boolean;
}

/** `GET /recruiting/interviews` params. */
export interface InterviewBoardParams {
  scope?: InterviewBoardScope;
  status?: InterviewBoardStatus;
  job_id?: string;
  /** Only interviews where the caller is an attendee/assignee. */
  mine?: boolean;
  limit?: number;
  offset?: number;
}

/** `GET /recruiting/interviews` payload (auto-unwrapped from `{ data }`). */
export interface InterviewBoardResult {
  interviews: InterviewBoardRow[];
  total: number;
}

/* --------------------------------- Offers --------------------------------- */

/** Lifecycle scope for the offers board. */
export type OfferBoardScope = "live" | "terminal" | "needs_action" | "all";

/** The 8-state offer machine (mirrors the per-application `OfferStatus`). */
export type OfferBoardStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "accepted"
  | "declined"
  | "expired"
  | "rescinded";

/**
 * One offer row on the org-wide board. Salary is the recruiter's own org comp
 * (visible per RBAC); it is `null` when no figure was set on the draft.
 */
export interface OfferBoardRow {
  id: string;
  application_id: string;
  job_id: string;
  job_title: string;
  candidate_handle: string;
  position_title: string;
  status: OfferBoardStatus;
  status_label: string;
  is_live: boolean;
  expiry_date: string | null;
  sent_at: string | null;
  approved_at: string | null;
  created_at: string;
  salary_amount: number | null;
  salary_currency: string;
  salary_period: string;
  period_label: string;
  start_date: string | null;
}

/** `GET /recruiting/offers` params. */
export interface OfferBoardParams {
  scope?: OfferBoardScope;
  status?: OfferBoardStatus;
  job_id?: string;
  limit?: number;
  offset?: number;
}

/** `GET /recruiting/offers` payload (auto-unwrapped from `{ data }`). */
export interface OfferBoardResult {
  offers: OfferBoardRow[];
  total: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const recruitingApi = {
  /**
   * Org-wide interviews board. `scope` defaults to `upcoming` server-side; the
   * board UI passes `all` and filters client-side so KPI counts and the
   * segmented time-window control stay honest against one loaded snapshot.
   */
  listInterviewsBoard(
    params: InterviewBoardParams = {},
  ): Promise<InterviewBoardResult> {
    return api.get<InterviewBoardResult>("/recruiting/interviews", {
      query: {
        scope: params.scope,
        status: params.status,
        job_id: params.job_id,
        mine: params.mine,
        limit: params.limit,
        offset: params.offset,
      },
    });
  },

  /** Org-wide offers board. `scope` defaults to `all` server-side. */
  listOffersBoard(params: OfferBoardParams = {}): Promise<OfferBoardResult> {
    return api.get<OfferBoardResult>("/recruiting/offers", {
      query: {
        scope: params.scope,
        status: params.status,
        job_id: params.job_id,
        limit: params.limit,
        offset: params.offset,
      },
    });
  },
};
