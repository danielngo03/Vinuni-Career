/**
 * University career-services counselor workspace API
 * (`/api/v1/career-services/...`).
 *
 * Mirrors `backend/app/modules/career_services/api/{schemas,router}.py` and the
 * application-service presenters exactly — every status/reason/category/type
 * code ships with a server-localized `_label` sibling (never a raw enum code
 * alone in the UI). RBAC is per-resource
 * (`career_services_cohorts|_at_risk|_cv_review|_appointments|_notes|_interventions|_reporting`);
 * callers must expect `PERMISSION_DENIED` independently for each resource.
 */
import { api } from "./client";

/* --------------------------------- Cohorts -------------------------------- */

export type CohortStatus = "active" | "archived";

export interface CareerServicesCohort {
  id: string;
  name: string;
  description: string | null;
  owner_counselor_id: string;
  status: CohortStatus;
  status_label: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface CohortMembership {
  id: string;
  cohort_id: string;
  student_id: string;
  added_by: string;
  created_at: string | null;
}

export interface CohortCreateBody {
  name: string;
  description?: string | null;
}

export interface CohortUpdateBody {
  name?: string;
  description?: string | null;
  status?: CohortStatus;
}

/* ------------------------------- At-risk flags ----------------------------- */

export type RiskReason =
  | "academic_performance"
  | "low_engagement"
  | "no_applications_submitted"
  | "missed_appointments"
  | "graduating_unplaced"
  | "other";

export type RiskSeverity = "low" | "medium" | "high";
export type RiskStatus = "open" | "in_progress" | "resolved" | "dismissed";

export const RISK_REASONS: RiskReason[] = [
  "academic_performance",
  "low_engagement",
  "no_applications_submitted",
  "missed_appointments",
  "graduating_unplaced",
  "other",
];

export const RISK_SEVERITIES: RiskSeverity[] = ["low", "medium", "high"];

export interface AtRiskFlag {
  id: string;
  student_id: string;
  cohort_id: string | null;
  reason: RiskReason;
  reason_label: string;
  severity: RiskSeverity;
  severity_label: string;
  status: RiskStatus;
  status_label: string;
  notes: string | null;
  flagged_by: string;
  resolved_by: string | null;
  resolution_notes: string | null;
  resolved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AtRiskFlagCreateBody {
  student_id: string;
  reason: RiskReason;
  severity?: RiskSeverity;
  notes?: string | null;
  cohort_id?: string | null;
}

/* ------------------------------ CV review queue ---------------------------- */

export type CvReviewStatus =
  | "queued"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "closed";
export type CvReviewPriority = "low" | "normal" | "high" | "urgent";

export const CV_REVIEW_PRIORITIES: CvReviewPriority[] = [
  "low",
  "normal",
  "high",
  "urgent",
];

export const CV_REVIEW_STATUSES: CvReviewStatus[] = [
  "queued",
  "in_review",
  "changes_requested",
  "approved",
  "closed",
];

export interface CvReviewItem {
  id: string;
  student_id: string;
  cv_id: string | null;
  requested_by: string;
  assigned_counselor_id: string | null;
  status: CvReviewStatus;
  status_label: string;
  priority: CvReviewPriority;
  priority_label: string;
  feedback: string | null;
  created_at: string | null;
  updated_at: string | null;
  resolved_at: string | null;
}

export interface CvReviewCreateBody {
  student_id: string;
  cv_id?: string | null;
  priority?: CvReviewPriority;
}

/* -------------------------------- Appointments ------------------------------ */

export type AppointmentStatus =
  | "requested"
  | "confirmed"
  | "completed"
  | "cancelled"
  | "no_show";
export type AppointmentMode = "in_person" | "video" | "phone";

export const APPOINTMENT_MODES: AppointmentMode[] = ["in_person", "video", "phone"];
export const APPOINTMENT_STATUSES: AppointmentStatus[] = [
  "requested",
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
];

export interface CareerServicesAppointment {
  id: string;
  student_id: string;
  counselor_id: string;
  scheduled_at: string | null;
  duration_minutes: number;
  mode: AppointmentMode;
  mode_label: string;
  location: string | null;
  status: AppointmentStatus;
  status_label: string;
  notes: string | null;
  cancel_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AppointmentCreateBody {
  student_id: string;
  counselor_id: string;
  /** ISO datetime, sent as-is to the backend (UTC-normalized client-side). */
  scheduled_at: string;
  duration_minutes?: number;
  mode?: AppointmentMode;
  location?: string | null;
  notes?: string | null;
}

/* ------------------------- Employer relationship notes ---------------------- */

export type NoteCategory =
  | "general"
  | "partnership"
  | "hiring_event"
  | "feedback"
  | "escalation";
export type NoteVisibility = "counselor_only" | "department" | "all_staff";

export const NOTE_CATEGORIES: NoteCategory[] = [
  "general",
  "partnership",
  "hiring_event",
  "feedback",
  "escalation",
];
export const NOTE_VISIBILITIES: NoteVisibility[] = [
  "counselor_only",
  "department",
  "all_staff",
];

export interface EmployerRelationshipNote {
  id: string;
  employer_org_id: string;
  author_id: string;
  category: NoteCategory;
  category_label: string;
  visibility: NoteVisibility;
  visibility_label: string;
  note_text: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface EmployerNoteCreateBody {
  employer_org_id: string;
  category?: NoteCategory;
  visibility?: NoteVisibility;
  note_text: string;
}

export interface EmployerNoteUpdateBody {
  note_text?: string;
  category?: NoteCategory;
  visibility?: NoteVisibility;
}

/* ---------------------------- Intervention history -------------------------- */

export type InterventionType =
  | "advising_session"
  | "referral"
  | "workshop_recommendation"
  | "at_risk_outreach"
  | "cv_review_followup"
  | "employer_referral"
  | "other";

export type InterventionOutcome =
  | "no_outcome_yet"
  | "improved"
  | "no_change"
  | "escalated"
  | "resolved";

export const INTERVENTION_TYPES: InterventionType[] = [
  "advising_session",
  "referral",
  "workshop_recommendation",
  "at_risk_outreach",
  "cv_review_followup",
  "employer_referral",
  "other",
];

export const INTERVENTION_OUTCOMES: InterventionOutcome[] = [
  "no_outcome_yet",
  "improved",
  "no_change",
  "escalated",
  "resolved",
];

export interface InterventionRecord {
  id: string;
  student_id: string;
  counselor_id: string;
  intervention_type: InterventionType;
  intervention_type_label: string;
  description: string;
  outcome: InterventionOutcome;
  outcome_label: string;
  linked_appointment_id: string | null;
  linked_at_risk_flag_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InterventionCreateBody {
  student_id: string;
  intervention_type: InterventionType;
  description: string;
  linked_appointment_id?: string | null;
  linked_at_risk_flag_id?: string | null;
}

/* ------------------------------ Outcomes reporting -------------------------- */

export interface ReportingBucket {
  code: string;
  label: string;
  count: number;
}

export interface CareerServicesReportingSummary {
  active_cohorts: number;
  open_at_risk_flags: number;
  open_cv_reviews: number;
  at_risk_by_status: ReportingBucket[];
  at_risk_by_severity: ReportingBucket[];
  cv_review_by_status: ReportingBucket[];
  appointments_by_status: ReportingBucket[];
  interventions_by_outcome: ReportingBucket[];
}

/* ---------------------------------- Calls ----------------------------------- */

export const careerServicesApi = {
  // Cohorts
  listCohorts(locale: string): Promise<CareerServicesCohort[]> {
    return api.get("/career-services/cohorts", { query: { locale } });
  },
  createCohort(body: CohortCreateBody, locale: string): Promise<CareerServicesCohort> {
    return api.post("/career-services/cohorts", body, { query: { locale } });
  },
  updateCohort(
    id: string,
    body: CohortUpdateBody,
    locale: string,
  ): Promise<CareerServicesCohort> {
    return api.patch(`/career-services/cohorts/${id}`, body, { query: { locale } });
  },
  deleteCohort(id: string): Promise<void> {
    return api.delete(`/career-services/cohorts/${id}`);
  },
  listMembers(cohortId: string): Promise<CohortMembership[]> {
    return api.get(`/career-services/cohorts/${cohortId}/members`);
  },
  addMember(cohortId: string, studentId: string): Promise<CohortMembership> {
    return api.post(`/career-services/cohorts/${cohortId}/members`, {
      student_id: studentId,
    });
  },
  removeMember(cohortId: string, studentId: string): Promise<void> {
    return api.delete(
      `/career-services/cohorts/${cohortId}/members/${studentId}`,
    );
  },

  // At-risk flags
  listAtRiskFlags(
    locale: string,
    params?: { student_id?: string; status?: RiskStatus | "" },
  ): Promise<AtRiskFlag[]> {
    return api.get("/career-services/at-risk-flags", {
      query: {
        locale,
        student_id: params?.student_id || undefined,
        status: params?.status || undefined,
      },
    });
  },
  createAtRiskFlag(body: AtRiskFlagCreateBody, locale: string): Promise<AtRiskFlag> {
    return api.post("/career-services/at-risk-flags", body, { query: { locale } });
  },
  updateAtRiskFlagStatus(
    id: string,
    body: { status: RiskStatus; resolution_notes?: string | null },
    locale: string,
  ): Promise<AtRiskFlag> {
    return api.patch(`/career-services/at-risk-flags/${id}/status`, body, {
      query: { locale },
    });
  },

  // CV review queue
  listCvReviewItems(
    locale: string,
    params?: { status?: CvReviewStatus | ""; assigned_counselor_id?: string },
  ): Promise<CvReviewItem[]> {
    return api.get("/career-services/cv-review-items", {
      query: {
        locale,
        status: params?.status || undefined,
        assigned_counselor_id: params?.assigned_counselor_id || undefined,
      },
    });
  },
  createCvReviewItem(body: CvReviewCreateBody, locale: string): Promise<CvReviewItem> {
    return api.post("/career-services/cv-review-items", body, { query: { locale } });
  },
  assignCvReview(
    id: string,
    counselorId: string,
    locale: string,
  ): Promise<CvReviewItem> {
    return api.post(
      `/career-services/cv-review-items/${id}/assign`,
      { counselor_id: counselorId },
      { query: { locale } },
    );
  },
  updateCvReviewStatus(
    id: string,
    body: { status: CvReviewStatus; feedback?: string | null },
    locale: string,
  ): Promise<CvReviewItem> {
    return api.patch(`/career-services/cv-review-items/${id}/status`, body, {
      query: { locale },
    });
  },

  // Appointments
  listAppointments(
    locale: string,
    params?: {
      counselor_id?: string;
      student_id?: string;
      status?: AppointmentStatus | "";
    },
  ): Promise<CareerServicesAppointment[]> {
    return api.get("/career-services/appointments", {
      query: {
        locale,
        counselor_id: params?.counselor_id || undefined,
        student_id: params?.student_id || undefined,
        status: params?.status || undefined,
      },
    });
  },
  bookAppointment(
    body: AppointmentCreateBody,
    locale: string,
  ): Promise<CareerServicesAppointment> {
    return api.post("/career-services/appointments", body, { query: { locale } });
  },
  updateAppointmentStatus(
    id: string,
    body: { status: AppointmentStatus; cancel_reason?: string | null },
    locale: string,
  ): Promise<CareerServicesAppointment> {
    return api.patch(`/career-services/appointments/${id}/status`, body, {
      query: { locale },
    });
  },

  // Employer relationship notes
  listEmployerNotes(
    locale: string,
    employerOrgId?: string,
  ): Promise<EmployerRelationshipNote[]> {
    return api.get("/career-services/employer-notes", {
      query: { locale, employer_org_id: employerOrgId || undefined },
    });
  },
  createEmployerNote(
    body: EmployerNoteCreateBody,
    locale: string,
  ): Promise<EmployerRelationshipNote> {
    return api.post("/career-services/employer-notes", body, { query: { locale } });
  },
  updateEmployerNote(
    id: string,
    body: EmployerNoteUpdateBody,
    locale: string,
  ): Promise<EmployerRelationshipNote> {
    return api.patch(`/career-services/employer-notes/${id}`, body, {
      query: { locale },
    });
  },

  // Intervention history
  listInterventions(
    locale: string,
    studentId?: string,
  ): Promise<InterventionRecord[]> {
    return api.get("/career-services/interventions", {
      query: { locale, student_id: studentId || undefined },
    });
  },
  createIntervention(
    body: InterventionCreateBody,
    locale: string,
  ): Promise<InterventionRecord> {
    return api.post("/career-services/interventions", body, { query: { locale } });
  },
  updateInterventionOutcome(
    id: string,
    outcome: InterventionOutcome,
    locale: string,
  ): Promise<InterventionRecord> {
    return api.patch(
      `/career-services/interventions/${id}/outcome`,
      { outcome },
      { query: { locale } },
    );
  },

  // Outcomes reporting
  getReportingSummary(locale: string): Promise<CareerServicesReportingSummary> {
    return api.get("/career-services/reporting/summary", { query: { locale } });
  },
};
