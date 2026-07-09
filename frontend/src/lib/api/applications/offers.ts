import { api } from "../client";
import { newIdempotencyKey } from "../cv";

/* ---------------------------- Offers (ADR-0007) --------------------------- */
/*
 * The offer is the terminal POSITIVE outcome of the pipeline — the only path to
 * `applications.status='hired'`. Salary is "recruiter + owning-student only"
 * (Fernet-encrypted at rest): the partner offer DETAIL + the student's OWN offer
 * carry decrypted comp; the partner BOARD glance NEVER does. The student only ever
 * sees their OWN `sent`+terminal offer — never a draft/pending/approved offer and
 * never partner internals (`created_by`/`approved_by`/`decline_reason`).
 */

/** The 8-state offer machine (ADR-0007 §1). */
export type OfferStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "accepted"
  | "declined"
  | "expired"
  | "rescinded";

/** LIVE (non-terminal) offer states — at most one per application. */
export const OFFER_LIVE_STATUSES: readonly OfferStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "sent",
];

/** Approval-gate decision (partner approver). */
export type OfferApproveDecision = "approve" | "reject";

/** Candidate response (V1 — counter-offer deferred). */
export type OfferRespondDecision = "accepted" | "declined";

/** Salary period picker order (matches the backend `period_label` vocab). */
export type SalaryPeriod = "monthly" | "yearly" | "hourly";
export const SALARY_PERIODS: readonly SalaryPeriod[] = [
  "monthly",
  "yearly",
  "hourly",
];

/** Currency options (V1 — VND default). */
export const SALARY_CURRENCIES: readonly string[] = ["VND", "USD"];

/** Decrypted comp block shared by the partner + owning-student offer views. */
export interface OfferCompFields {
  /** Null when no salary was set. */
  salary_amount: number | null;
  salary_currency: string;
  salary_period: string;
  /** Short human comp string (e.g. "20,000,000 VND/tháng"), or null. */
  comp_summary: string | null;
}

/**
 * The partner offer DETAIL view (partner-internal): FULL comp + the approval
 * trail. `decline_reason`/`approved_by`/`created_by` are partner-internal and
 * never reach a student surface.
 */
export interface PartnerOffer extends OfferCompFields {
  id: string;
  application_id: string;
  stage_id: string;
  status: OfferStatus | string;
  status_label: string;
  position_title: string;
  department: string | null;
  start_date: string | null;
  benefits_summary: string | null;
  terms_notes: string | null;
  /** Response deadline. */
  expiry_date: string | null;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  sent_at: string | null;
  student_response_at: string | null;
  /** Partner-internal note captured on a candidate decline. */
  decline_reason: string | null;
  /** Optimistic-concurrency token; a stale value yields a 409. */
  version: number;
  created_at: string;
  updated_at: string;
}

/** `GET /applications/{id}/offers` envelope (partner). */
export interface OfferListResult {
  application_id: string;
  offers: PartnerOffer[];
}

/**
 * The partner-only board/detail offer GLANCE — status + deadline, deliberately
 * NO salary (open the offer detail to see comp). Surfaced on the partner
 * application detail's `pipeline.offer` and (when wired) the board card.
 */
export interface OfferBoardGlance {
  id: string;
  status: OfferStatus | string;
  status_label: string;
  expiry_date: string | null;
  sent_at: string | null;
}

/**
 * The owning student's OWN offer (full comp; partner internals stripped). Only
 * `sent`+terminal offers are ever exposed to the student. Returned by
 * `POST /offers/{id}/respond` and `GET /offers/{id}`.
 */
export interface StudentOffer extends OfferCompFields {
  id: string;
  application_id: string;
  status: OfferStatus | string;
  status_label: string;
  position_title: string;
  department: string | null;
  start_date: string | null;
  benefits_summary: string | null;
  terms_notes: string | null;
  expiry_date: string | null;
  sent_at: string | null;
  student_response_at: string | null;
  version: number;
}

/**
 * The candidate's OWN offer summary card for the application timeline. Carries
 * `comp_summary` (their own comp is theirs to see) but no discrete figure; NEVER
 * partner internals and never a draft/pending/approved offer.
 */
export interface StudentOfferCard {
  id: string;
  status: OfferStatus | string;
  status_label: string;
  position_title: string;
  department: string | null;
  start_date: string | null;
  expiry_date: string | null;
  comp_summary: string | null;
}

/** Create-draft body (`expiry_date` = response deadline; required). */
export interface CreateOfferBody {
  position_title: string;
  expiry_date: string;
  department?: string | null;
  start_date?: string | null;
  salary_amount?: number | null;
  salary_currency?: string;
  salary_period?: string;
  benefits_summary?: string | null;
  terms_notes?: string | null;
}

/** Edit-draft body (editable ONLY while `draft`). Omitted fields stay unchanged. */
export interface UpdateOfferBody {
  position_title?: string | null;
  department?: string | null;
  start_date?: string | null;
  salary_amount?: number | null;
  salary_currency?: string | null;
  salary_period?: string | null;
  benefits_summary?: string | null;
  terms_notes?: string | null;
  expiry_date?: string | null;
  version?: number;
}

/** Candidate accept/decline body (the client supplies the idempotency key). */
export interface RespondOfferBody {
  decision: OfferRespondDecision;
  note?: string | null;
}

/* --------------------------------- Calls ---------------------------------- */

export const offersApi = {
  /**
   * Partner: create the DRAFT offer at the candidate's current ACTIVE stage. A
   * second LIVE offer → `409 offer_exists`; the app not `under_review` → `409
   * illegal_transition`. `salary_amount` is encrypted server-side. 404 cross-org.
   */
  createOffer(applicationId: string, body: CreateOfferBody): Promise<PartnerOffer> {
    return api.post<PartnerOffer>(`/applications/${applicationId}/offers`, body);
  },

  /**
   * Partner: list an application's offers (full comp — salary decrypted for the
   * partner). Partner-internal; never a student surface.
   */
  listOffers(applicationId: string): Promise<OfferListResult> {
    return api.get<OfferListResult>(`/applications/${applicationId}/offers`);
  },

  /**
   * Partner: edit a DRAFT offer (comp/terms/deadline). `409 offer_not_editable`
   * once past `draft`; optimistic `version` → `409` on a stale value.
   */
  updateOfferDraft(
    applicationId: string,
    offerId: string,
    body: UpdateOfferBody,
  ): Promise<PartnerOffer> {
    return api.patch<PartnerOffer>(
      `/applications/${applicationId}/offers/${offerId}`,
      body,
    );
  },

  /** Partner: submit a draft for approval (`draft → pending_approval`). */
  submitOffer(offerId: string, version?: number): Promise<PartnerOffer> {
    return api.post<PartnerOffer>(
      `/offers/${offerId}/submit`,
      version === undefined ? {} : { version },
    );
  },

  /**
   * Partner: approve (`pending_approval → approved`) or reject-back
   * (`pending_approval → draft`). Optimistic `version`.
   */
  approveOffer(
    offerId: string,
    decision: OfferApproveDecision,
    version?: number,
  ): Promise<PartnerOffer> {
    return api.post<PartnerOffer>(
      `/offers/${offerId}/approve`,
      version === undefined ? { decision } : { decision, version },
    );
  },

  /**
   * Partner: send an approved offer to the candidate (`approved → sent`). `409
   * offer_not_approved` if not yet `approved`.
   */
  sendOffer(offerId: string, version?: number): Promise<PartnerOffer> {
    return api.post<PartnerOffer>(
      `/offers/${offerId}/send`,
      version === undefined ? {} : { version },
    );
  },

  /** Partner: rescind a LIVE offer (`{draft,pending,approved,sent} → rescinded`). */
  rescindOffer(offerId: string, version?: number): Promise<PartnerOffer> {
    return api.post<PartnerOffer>(
      `/offers/${offerId}/rescind`,
      version === undefined ? {} : { version },
    );
  },

  /**
   * Student: accept / decline their OWN `sent` (non-expired) offer. Owner-only;
   * `409 offer_not_actionable` on an expired/terminal offer. Idempotent: a fresh
   * `idempotency_key` makes a network retry safe.
   */
  respondOffer(offerId: string, body: RespondOfferBody): Promise<StudentOffer> {
    return api.post<StudentOffer>(`/offers/${offerId}/respond`, {
      decision: body.decision,
      notes: body.note?.trim() ? body.note.trim() : undefined,
      idempotency_key: newIdempotencyKey(),
    });
  },
};
