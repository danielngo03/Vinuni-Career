/**
 * Platform Trust — support console, privacy/compliance, abuse triage
 * (ADR-0014, E36). Endpoints per docs/API_CONTRACTS.md
 * "Platform Trust — Support, Privacy, Abuse (ADR-0014, E36)" and the ground
 * truth routers under backend/app/modules/{platform_support,compliance,
 * moderation}/api/router.py.
 *
 * RBAC nouns consumed here (`support:*`, `privacy:*`, `abuse:*`) are
 * service-layer only — the frontend never gates on a role name, it renders
 * whatever the API returns and falls back to a permission empty-state on 403.
 */
import { api } from "./client";

/* ------------------------------- Support -------------------------------- */

export interface SupportUserRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  email_verified: boolean;
  persona: string;
  org_id: string | null;
  created_at: string | null;
}

export interface SupportOrgRow {
  id: string;
  slug: string;
  display_name: string;
  org_type: string;
  status: string;
  is_verified: boolean;
  trust_level: string | null;
  subscription_tier: string | null;
  created_at: string | null;
}

export interface SupportLookupResult<Row> {
  items: Row[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OutboxHealth {
  pending: number;
  sent: number;
  failed: number;
  dead: number;
  skipped: number;
  retry_scheduled: number;
  oldest_pending_age_seconds: number | null;
}

export interface SupportCase {
  id: string;
  resource_type: string;
  resource_id: string | null;
  severity: "low" | "medium" | "high" | string;
  status: string;
  findings: Record<string, unknown> | null;
  created_at: string;
}

export interface RevealedContact {
  email: string;
  full_name: string;
}

export const supportApi = {
  lookupUsers(q: string | undefined, page = 1, pageSize = 30) {
    return api.get<SupportLookupResult<SupportUserRow>>("/platform-support/lookup", {
      query: { q, type: "user", page, page_size: pageSize },
    });
  },
  lookupOrgs(q: string | undefined, page = 1, pageSize = 30) {
    return api.get<SupportLookupResult<SupportOrgRow>>("/platform-support/lookup", {
      query: { q, type: "organization", page, page_size: pageSize },
    });
  },
  outboxHealth() {
    return api.get<OutboxHealth>("/platform-support/outbox-health");
  },
  requeueOutbox(outboxId: string) {
    return api.post<{ id: string; status: string }>(
      `/platform-support/outbox/${outboxId}/requeue`,
    );
  },
  /** V1 scope: only `resource_type="user_contact"` is wired server-side. */
  revealUserContact(userId: string, reason: string) {
    return api.post<RevealedContact>(`/platform-support/reveal/user_contact/${userId}`, {
      reason,
    });
  },
  listCases(status?: string) {
    return api.get<SupportCase[]>("/platform-support/cases", {
      query: { status },
    });
  },
  resolveCase(itemId: string, note?: string) {
    return api.post<SupportCase>(`/platform-support/cases/${itemId}/resolve`, { note });
  },
};

/* --------------------------- Privacy / compliance ------------------------- */

export type ConsentType = "interview_recording" | "career_outcomes_data_sharing";

export interface ConsentState {
  granted: boolean;
  granted_at: string | null;
  revoked_at: string | null;
}

export type ConsentsResponse = Record<ConsentType, ConsentState>;

export interface RetentionPolicyItem {
  key: string;
  retention_days: number;
  label: string;
}

export type PrivacyRequestType = "export" | "deletion";
export type PrivacyRequestStatus = "pending" | "processing" | "fulfilled" | "rejected";

export interface PrivacyRequest {
  id: string;
  request_type: PrivacyRequestType;
  status: PrivacyRequestStatus;
  requested_by: string;
  processed_by: string | null;
  note: string | null;
  created_at: string;
  fulfilled_at: string | null;
}

export interface PrivacyRequestSubmitResult {
  status: "submitted" | "request_already_pending";
  request: PrivacyRequest;
}

export const privacyApi = {
  getConsents() {
    return api.get<ConsentsResponse>("/account/privacy/consents");
  },
  setConsent(type: ConsentType, granted: boolean) {
    return api.put<ConsentState>(`/account/privacy/consents/${type}`, { granted });
  },
  getRetention(locale: string) {
    return api.get<RetentionPolicyItem[]>("/account/privacy/retention", {
      query: { locale },
    });
  },
  submitRequest(requestType: PrivacyRequestType, note?: string) {
    return api.post<PrivacyRequestSubmitResult>("/account/privacy/requests", {
      request_type: requestType,
      note,
    });
  },
  listMyRequests() {
    return api.get<PrivacyRequest[]>("/account/privacy/requests");
  },
};

export const privacyAdminApi = {
  listRequests(status?: string, requestType?: string) {
    return api.get<PrivacyRequest[]>("/admin/privacy-requests", {
      query: { status, request_type: requestType },
    });
  },
  fulfill(requestId: string, status: "fulfilled" | "rejected", note?: string) {
    return api.post<PrivacyRequest>(`/admin/privacy-requests/${requestId}/fulfill`, {
      status,
      note,
    });
  },
};

/* --------------------------------- Abuse --------------------------------- */

export type ReportEntityType = "company" | "job" | "message";

export const REPORT_REASON_CODES = [
  "spam",
  "scam_fraud",
  "misleading_info",
  "inappropriate_content",
  "harassment",
  "other",
] as const;
export type ReportReasonCode = (typeof REPORT_REASON_CODES)[number];

export interface ContentReport {
  id: string;
  entity_type: string;
  entity_id: string;
  reason_code: string;
  status: "PENDING" | "TRIAGED" | "DISMISSED" | string;
  created_at: string;
}

export interface ContentReportSubmitResult {
  status: "submitted" | "already_reported";
  report: ContentReport;
}

export interface TriageContentReportItem {
  kind: "content_report";
  id: string;
  entity_type: string;
  entity_id: string;
  reason_code: string;
  status: string;
  review_item_id: string | null;
  created_at: string;
}

export interface TriageReviewItem {
  kind: "human_review_item";
  id: string;
  source: string;
  resource_type: string;
  resource_id: string | null;
  severity: "low" | "medium" | "high" | string;
  status: string;
  created_at: string;
}

export type TriageItem = TriageContentReportItem | TriageReviewItem;

export const TRIAGE_SOURCES = [
  "user_report",
  "fraud_detection",
  "content_moderation",
  "bias_detection",
  "support_case",
  "agent_loop",
] as const;

export const abuseApi = {
  submitReport(entityType: ReportEntityType, entityId: string, reasonCode: string, note?: string) {
    return api.post<ContentReportSubmitResult>("/content-reports", {
      entity_type: entityType,
      entity_id: entityId,
      reason_code: reasonCode,
      note,
    });
  },
  escalateReport(reportId: string) {
    return api.post<ContentReport>(`/content-reports/${reportId}/escalate`);
  },
  listTriage(source?: string) {
    return api.get<TriageItem[]>("/moderation/triage", { query: { source } });
  },
  /**
   * The backend audits a real before/after snapshot on this write path
   * (ADR-0014), but the HTTP response only echoes the updated review item —
   * the diff itself lives in `audit_logs`, not the response body. V1 only
   * has a wired resource-side reversal for `resource_type="user"`
   * (unsuspend); the UI renders that known transition when applicable and a
   * "no resource-side reversal wired" disclosure otherwise, rather than
   * fabricating a diff the API does not return.
   */
  overrideAction(reviewItemId: string, note: string) {
    return api.post<TriageReviewItem>(`/moderation/actions/${reviewItemId}/override`, {
      note,
    });
  },
};
