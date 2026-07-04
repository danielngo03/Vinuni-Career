import { api, apiDownload } from "../client";
import type { ApiListEnvelope } from "../types";
import type { StudentInterviewCard } from "./interviews";
import type { OfferBoardGlance, StudentOfferCard } from "./offers";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Application lifecycle. `interview`/`offer` progress is tracked separately
 * (via `upcoming_interview`/`offer` + the interviews/offers modules) — the
 * backend NEVER emits `shortlisted` | `interview` | `offer` as an
 * `application.status` value, so those are not part of this vocabulary.
 */
export type ApplicationStatus =
  | "submitted"
  | "under_review"
  | "rejected"
  | "withdrawn"
  | "hired";

/**
 * Coded reasons a partner must pick when rejecting an application. The codes are
 * the wire contract; localized labels live in i18n (candidates.rejectReasons).
 */
export type RejectionReason =
  | "not_qualified"
  | "experience_mismatch"
  | "position_filled"
  | "incomplete"
  | "other";

/** Display order for the rejection-reason picker. */
export const REJECTION_REASONS: readonly RejectionReason[] = [
  "not_qualified",
  "experience_mismatch",
  "position_filled",
  "incomplete",
  "other",
];

/**
 * The action that gates advancing OUT of a pipeline stage (ADR-0005 §3). The V1
 * seeded ladder is all `manual`; `scorecard` blocks `/advance` until a scorecard
 * is submitted. Partner-only — never surfaced to the student.
 */
export type StageRequiredAction =
  | "manual"
  | "scorecard"
  | "score_threshold"
  | string;

/** CV selection discriminator on apply (docs/API_CONTRACTS.md). */
export type CvSelectionType = "builder_cv" | "uploaded_document";

/** Reveal request lifecycle as surfaced by the API. */
export type RevealStatus = "none" | "pending" | "accepted" | "declined" | "expired";

export type RevealDecision = "accepted" | "declined";

/* ------------------------------- Wire types ------------------------------- */

export interface CvSelectionInput {
  type: CvSelectionType;
  cv_profile_id?: string | null;
  cv_version_id?: string | null;
  uploaded_document_id?: string | null;
}

/** Free-form screening answers, keyed by screening question id. */
export type ScreeningAnswers = Record<string, string | string[]>;

export interface ApplyBody {
  job_id: string;
  cv_selection: CvSelectionInput;
  cover_letter?: string | null;
  screening_answers?: ScreeningAnswers;
  is_anonymous?: boolean;
  idempotency_key: string;
}

/**
 * Short, machine-readable "what happens next" key for the student, derived
 * server-side from status + upcoming interview + actionable offer
 * (`docs/DATA_MODEL.md` §32). Open union: unknown values render no banner
 * rather than crash.
 */
export type ApplicationNextAction =
  | "await_review"
  | "prepare_for_interview"
  | "respond_to_offer"
  | "no_action_withdrawn"
  | "no_action_rejected"
  | "no_action_hired"
  | "in_progress"
  | (string & {});

/**
 * One entry in the student-facing application timeline
 * (`docs/DATA_MODEL.md` §32). `label` is already locale-resolved server-side —
 * never re-translate it client-side. Never carries partner-internal metadata
 * (rejection reason, target stage).
 */
export interface ApplicationTimelineEvent {
  event_type: string;
  label: string;
  occurred_at: string;
}

/** Pointer to a real application-bound message thread, when one exists. */
export interface ApplicationMessagesPointer {
  thread_id: string;
  unread_count: number;
}

/** A reveal request as seen by either party. */
export interface RevealRequest {
  id: string;
  application_id: string;
  status: RevealStatus | string;
  status_label: string | null;
  reason: string;
  expires_at: string | null;
  responded_at: string | null;
  created_at: string;
}

/**
 * Student-facing application (list + detail share this shape). `reveal_request`
 * / `reveal_status` are optional: the current backend projection omits them, so
 * the UI renders the reveal accept/decline panel only when they are present
 * (no fabricated data). See handoff "backend gaps".
 */
export interface StudentApplication {
  id: string;
  job_id: string;
  job_title: string | null;
  company_name: string | null;
  status: ApplicationStatus | string;
  status_label: string;
  is_anonymous: boolean;
  cover_letter: string | null;
  screening_answers: ScreeningAnswers;
  snapshot_id: string;
  applied_at: string;
  last_status_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  reveal_request?: RevealRequest | null;
  reveal_status?: RevealStatus | string | null;
  /**
   * The student's OWN upcoming interview (ADR-0006 §6) — identity-safe by
   * construction: date/mode/duration/location-or-link/status only, NEVER
   * assignees, scorecards, or the advance gate. Optional: absent until a partner
   * schedules one. This is the ONLY interview surface the student sees.
   */
  upcoming_interview?: StudentInterviewCard | null;
  /**
   * The student's OWN offer summary card (ADR-0007 §8). Identity-safe to the
   * owner: position, their own comp summary, start date, response deadline.
   * Surfaced ONLY for a `sent`+terminal offer — never a draft/pending/approved
   * one and never partner internals (`approved_by`, `decline_reason`). Optional:
   * absent until a partner SENDS an offer.
   */
  offer?: StudentOfferCard | null;
  /**
   * Real, server-sourced, locale-aware event log — ordered ascending by
   * `occurred_at`. Replaces the earlier client-side guess derived from
   * `status` alone. Defensive-only fallback: may be absent on stale cached
   * data; the current backend always returns it.
   */
  timeline?: ApplicationTimelineEvent[];
  /** Server-computed "what happens next" — do not re-derive from `status`. */
  next_action?: ApplicationNextAction | null;
  /** Server-computed — replaces any client-side status-based guess. */
  can_withdraw?: boolean;
  /** Non-null only when a real application-bound message thread exists. */
  messages_pointer?: ApplicationMessagesPointer | null;
}

/** Body for `POST /applications/{id}/withdraw`. Both fields optional. */
export interface WithdrawBody {
  /** Optimistic-lock guard; a stale value yields 409 `version_conflict`. */
  version?: number;
  /** The student's own free-text note (<=500 chars), not a coded reason. */
  reason?: string;
}

/** Applicant block in the partner view — PII redacted until revealed. */
export interface PartnerApplicant {
  is_anonymous: boolean;
  revealed: boolean;
  /** UV-xxxx handle shown while anonymous + unrevealed. */
  anonymous_id?: string | null;
  display_name: string;
  /** Only present once revealed (or non-anonymous). */
  email?: string | null;
  user_id?: string | null;
}

/** Partner-facing application (list + detail share this shape). */
export interface PartnerApplication {
  id: string;
  job_id: string;
  status: ApplicationStatus | string;
  status_label: string;
  is_anonymous: boolean;
  applicant: PartnerApplicant;
  screening_answers: ScreeningAnswers;
  /** Null while anonymous + unrevealed. */
  cover_letter: string | null;
  snapshot_id: string;
  /** True once the partner may download the (watermarked) CV. */
  cv_download_available: boolean;
  reveal_status: RevealStatus | string;
  reveal_status_label: string | null;
  applied_at: string;
  /** Last status transition timestamp (decision workflow). */
  last_status_at: string | null;
  /**
   * Coded rejection reason — partner-only, present only once `status` is
   * `rejected`. Never surfaced on student-facing projections.
   */
  rejection_reason: RejectionReason | string | null;
  /** Optional partner-only internal note attached on rejection. */
  rejection_note: string | null;
  /** Optimistic-concurrency token; a stale value yields a 409 CONFLICT. */
  version: number;
  /**
   * Anonymity-safe pipeline projection attached to the partner application detail
   * (`GET /applications/{id}`, partner branch). Carries the partner-only offer
   * GLANCE (status + deadline, NO salary). Full comp lives behind
   * `GET /applications/{id}/offers`. Optional: only the detail endpoint sets it.
   */
  pipeline?: { offer?: OfferBoardGlance | null } | null;
}

/** Body for a partner rejection decision. `reason` is required. */
export interface RejectBody {
  reason: RejectionReason;
  note?: string | null;
  version?: number;
}

/** Watermarked signed-download descriptor for a partner CV download. */
export interface CvDownloadInfo {
  snapshot_id: string;
  has_watermark: boolean;
  download_url: string;
}

/* ------------------------------ Pipeline board ---------------------------- */

/**
 * An ordered pipeline stage (configured template stage). Used both to label
 * columns and to drive the rollback target picker (prior stages only).
 */
export interface PipelineStage {
  id: string;
  name: string;
  sort_order: number;
  /** Whether candidates in this stage are visible to the caller's role. */
  candidate_visible?: boolean;
  /**
   * Partner-only gate for advancing OUT of this stage. The board reads this from
   * `board.stages[]` to render the "scorecard required to advance" state on a
   * `scorecard` column (ADR-0005 §3/§6).
   */
  required_action?: StageRequiredAction;
}

/**
 * Partner-only scorecard glance attached to a board card / partner detail for the
 * card's CURRENT stage. Anchoring-safe by construction: the score-derived fields
 * (`avg_overall`, `recommendation_summary`) are an aggregate, never an individual
 * reviewer's scores. NEVER present on any student projection (ADR-0005 §4/§6).
 */
export interface PipelineEvaluation {
  submitted_count: number;
  required: number;
  /** False on a `scorecard` stage with `submitted_count < required` → advance is blocked. */
  gate_met: boolean;
  avg_overall: number | null;
  /**
   * The `score_threshold` stage's required average (ADR-0006). Present on the
   * single-card detail evaluation; the leaner board-card glance may omit it.
   */
  threshold?: number | null;
  recommendation_summary: Record<string, number>;
}

/**
 * A single board card. Anonymity-safe by construction: the backend only ever
 * includes `display_name` when reveal/RBAC rules allow it; otherwise the card
 * carries the `anonymous_id` (UV-xxxx) handle. Never assume PII is present.
 * Carries NO score and NO rejection reason — those are not board-safe.
 */
export interface PipelineCard {
  application_id: string;
  is_anonymous: boolean;
  applicant: {
    /** Present only when reveal/RBAC allow it. */
    display_name?: string | null;
    /** UV-xxxx handle shown while anonymous + unrevealed. */
    anonymous_id?: string | null;
  };
  status: ApplicationStatus | string;
  status_label: string;
  reveal_status: RevealStatus | string;
  cv_download_available: boolean;
  /** `null` while the card sits in the pre-pipeline `new` bucket. */
  stage_id: string | null;
  position: number;
  /** When the card entered its current column (freshness). */
  entered_at: string;
  /** Count of rollbacks applied to this application (>0 surfaces a badge). */
  rollback_count: number;
  applied_at: string;
  last_status_at: string | null;
  /**
   * Partner-only scorecard summary for the card's CURRENT stage (null on the
   * pre-pipeline `new` bucket). `evaluation.gate_met === false` on a `scorecard`
   * column means the card is advance-blocked. Never carries student identity.
   */
  evaluation?: PipelineEvaluation | null;
  /**
   * Partner-only offer glance for the card's CURRENT (Offer) stage (ADR-0007 §8):
   * status + deadline ONLY — NO salary (open the candidate detail to see comp).
   * Optional/nullable: the board surfaces it only on a card whose current stage
   * carries a LIVE/terminal offer; otherwise it is absent.
   */
  offer?: OfferBoardGlance | null;
}

/**
 * One board column. `columns[0]` is always the `new` pre-pipeline bucket with
 * `stage_id: null`; subsequent columns map to ordered stages by `sort_order`.
 */
export interface PipelineColumn {
  /** `null` for the `new` pre-pipeline bucket. */
  stage_id: string | null;
  name: string;
  sort_order: number;
  candidate_visible: boolean;
  count: number;
  candidates: PipelineCard[];
}

/** Aggregate, board-safe counts shown above the columns. */
export interface PipelineSummary {
  rejected: number;
  withdrawn: number;
  [key: string]: number;
}

/** Partner pipeline board for one job (anonymity-safe projection). */
export interface PipelineBoard {
  job: { id: string; title: string };
  template_id: string | null;
  stages: PipelineStage[];
  columns: PipelineColumn[];
  summary: PipelineSummary;
  /** True when the board was capped at `candidate_cap` most-recent candidates. */
  truncated: boolean;
  candidate_cap: number;
}

/** Body for a rollback to a PRIOR stage (reason >= 20 chars). */
export interface RollbackBody {
  target_stage_id: string;
  reason: string;
  version?: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const applicationsCoreApi = {
  /* Student: submit an application (immutable snapshot, idempotent). */
  apply(body: ApplyBody): Promise<StudentApplication> {
    return api.post<StudentApplication>("/applications", body);
  },

  /* Student: own applications, cursor paginated. */
  listMine(opts?: {
    cursor?: string | null;
    limit?: number;
  }): Promise<ApiListEnvelope<StudentApplication>> {
    return api.list<StudentApplication>("/applications", {
      query: { cursor: opts?.cursor ?? undefined, limit: opts?.limit },
    });
  },

  /* Student: own application detail. */
  getMine(id: string): Promise<StudentApplication> {
    return api.get<StudentApplication>(`/applications/${id}`);
  },

  /* Student: withdraw (idempotent). `version`/`reason` are both optional. */
  withdraw(id: string, body?: WithdrawBody): Promise<StudentApplication> {
    return api.post<StudentApplication>(
      `/applications/${id}/withdraw`,
      body ?? {},
    );
  },

  /* Student: respond to a partner reveal request. */
  respondReveal(id: string, decision: RevealDecision): Promise<RevealRequest> {
    return api.post<RevealRequest>(`/applications/${id}/reveal/respond`, {
      decision,
    });
  },

  /* Partner: applications for one of the caller org's jobs, cursor paginated. */
  listForJob(
    jobId: string,
    opts?: { cursor?: string | null; limit?: number },
  ): Promise<ApiListEnvelope<PartnerApplication>> {
    return api.list<PartnerApplication>(`/jobs/${jobId}/applications`, {
      query: { cursor: opts?.cursor ?? undefined, limit: opts?.limit },
    });
  },

  /* Partner: application detail (org-scoped; anonymous redacted until reveal). */
  getForPartner(id: string): Promise<PartnerApplication> {
    return api.get<PartnerApplication>(`/applications/${id}`);
  },

  /* Partner: request to reveal an anonymous applicant (reason >= 20 chars). */
  requestReveal(id: string, reason: string): Promise<RevealRequest> {
    return api.post<RevealRequest>(`/applications/${id}/reveal`, { reason });
  },

  /* Partner: obtain a watermarked, signed CV download URL. */
  getCvDownload(id: string): Promise<CvDownloadInfo> {
    return api.get<CvDownloadInfo>(`/applications/${id}/cv-download`);
  },

  /* Partner: move `submitted` → `under_review` (idempotent). */
  review(id: string, version?: number): Promise<PartnerApplication> {
    return api.post<PartnerApplication>(
      `/applications/${id}/review`,
      version === undefined ? {} : { version },
    );
  },

  /* Partner: reject `{submitted,under_review}` → `rejected` (reason required). */
  reject(id: string, body: RejectBody): Promise<PartnerApplication> {
    return api.post<PartnerApplication>(`/applications/${id}/reject`, body);
  },

  /* Partner: anonymity-safe pipeline board for one job (kanban projection). */
  pipelineBoard(jobId: string): Promise<PipelineBoard> {
    return api.get<PipelineBoard>(`/jobs/${jobId}/pipeline`);
  },

  /**
   * Partner: advance an application to the next pipeline stage. `version` is
   * optional (board cards may omit it; the server resolves the current stage).
   * Always send a fresh `Idempotency-Key` so a retried click is a no-op.
   * 409 on a stale version / illegal transition.
   */
  advance(
    id: string,
    opts: { idempotencyKey: string; version?: number },
  ): Promise<PartnerApplication> {
    return api.post<PartnerApplication>(
      `/applications/${id}/advance`,
      opts.version === undefined ? {} : { version: opts.version },
      { headers: { "Idempotency-Key": opts.idempotencyKey } },
    );
  },

  /**
   * Partner: roll an application back to a PRIOR stage. `reason` must be >= 20
   * chars (422 otherwise); 409 on a stale version / illegal transition.
   */
  rollback(id: string, body: RollbackBody): Promise<PartnerApplication> {
    return api.post<PartnerApplication>(`/applications/${id}/rollback`, body);
  },

  /**
   * Partner: bulk-move submitted applications to under_review in one call.
   * Each item is processed independently; returns {reviewed, skipped, errors}.
   */
  bulkReview(
    jobId: string,
    applicationIds: string[],
  ): Promise<{ reviewed: number; skipped: number; errors: number }> {
    return api.post(`/jobs/${jobId}/applications/bulk-review`, {
      application_ids: applicationIds,
    });
  },

  /**
   * Partner: reject up to 100 applications in one call. Each item processed
   * independently; returns {rejected, skipped, errors}.
   */
  bulkReject(
    jobId: string,
    body: { application_ids: string[]; reason: RejectionReason; note?: string | null },
  ): Promise<{ rejected: number; skipped: number; errors: number }> {
    return api.post(`/jobs/${jobId}/applications/bulk-reject`, body);
  },

  /** Partner: export all applications for a job as a CSV blob (B-322). */
  exportCsv(jobId: string): Promise<Blob> {
    return apiDownload(`/jobs/${jobId}/applications/export`);
  },
};
