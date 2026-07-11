import { api, apiUpload } from "./client";
import type { ApiEnvelope } from "./types";

/**
 * Company profile + university-approval workflow (owner decision 2026-07-10).
 *
 * A partner admin opens their OWN company page and edits it, but the write path
 * is split by sensitivity — the backend, not the client, decides which path a
 * given field takes:
 *
 * - COSMETIC fields (display_name, description, website_url, industry,
 *   company_size, founded_year, headquarters_city/country) apply IMMEDIATELY.
 * - SENSITIVE legal-identity fields (legal_name, tax_code, registration_number)
 *   and ANY attached file do NOT touch the live profile — they accumulate on a
 *   single OPEN change request and wait for a university reviewer.
 *
 * `updateProfile` returns BOTH `applied` (the cosmetic fields written now) and
 * `requires_approval` + `pending_change_request` (the sensitive path), so the UI
 * can honestly tell the partner what happened.
 *
 * File safety: documents are projected as short-lived signed delivery URLs
 * (`url`); the raw storage key is NEVER returned and must never be reconstructed
 * client-side. Open/download the `url` directly.
 */

/** Change-request lifecycle. */
export type CompanyChangeStatus = "pending" | "approved" | "rejected" | "withdrawn";

/** Legal/verification document category. */
export type CompanyDocKind =
  | "business_license"
  | "tax_certificate"
  | "legal_document"
  | "other";

/** Selectable document kinds for the upload picker (backend allowlist). */
export const COMPANY_DOC_KINDS: readonly CompanyDocKind[] = [
  "business_license",
  "tax_certificate",
  "legal_document",
  "other",
] as const;

/** A stored company document, projected safe (signed `url`, never a key). */
export interface CompanyDocument {
  id: string;
  kind: CompanyDocKind | string;
  /** Localized category label (backend-rendered — never a raw code). */
  kind_label: string;
  filename: string;
  content_type: string;
  size: number;
  uploaded_at: string | null;
  /** Short-lived signed delivery URL. Open/download only; never a storage key. */
  url: string;
}

/** One proposed sensitive-field change, with a localized field label. */
export interface CompanyChangeField {
  field: string;
  /** Localized label (backend-rendered — never a raw column code). */
  label: string;
  from: string | number | null;
  to: string | number | null;
}

/** A company-profile change request (the "awaiting university review" unit). */
export interface CompanyChangeRequest {
  id: string;
  org_id: string;
  /** Company display name — populated on the university queue projection. */
  company_name: string | null;
  submitted_by: string | null;
  status: CompanyChangeStatus;
  /** Localized status label (backend-rendered). */
  status_label: string;
  /** Proposed sensitive-field diffs (may be empty for a documents-only request). */
  changes: CompanyChangeField[];
  /** Attached files awaiting approval. */
  documents: CompanyDocument[];
  reviewer_id: string | null;
  review_note: string | null;
  decided_at: string | null;
  /** Optimistic-locking version for approve/reject/withdraw. */
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

/** Full authenticated company profile for the partner-admin surface. */
export interface CompanyProfile {
  id: string;
  slug: string;
  org_type: "partner" | "university";
  logo_url: string | null;
  // Public identity + cosmetic (immediate) fields.
  display_name: string;
  description: string | null;
  website_url: string | null;
  industry: string | null;
  company_size: string | null;
  founded_year: number | null;
  headquarters_city: string | null;
  headquarters_country: string | null;
  // Sensitive legal identity (approval-gated).
  legal_name: string | null;
  tax_code: string | null;
  registration_number: string | null;
  is_verified: boolean;
  /** Approved verification documents on the live org. */
  verification_documents: CompanyDocument[];
  /** Optimistic-locking version. Send back on `updateProfile` to guard writes. */
  version: number;
  /** The single OPEN change request awaiting review, or null. */
  pending_change_request: CompanyChangeRequest | null;
}

/**
 * Partner profile edit. All fields optional; send only what changed. The
 * backend routes cosmetic vs sensitive by field name. `version` guards against
 * a concurrent edit (stale → 409 CONFLICT `version_conflict`).
 */
export interface CompanyProfileUpdateBody {
  // Cosmetic (applied immediately).
  display_name?: string;
  description?: string | null;
  website_url?: string | null;
  industry?: string | null;
  company_size?: string | null;
  founded_year?: number | null;
  headquarters_city?: string | null;
  headquarters_country?: string | null;
  // Sensitive (creates/merges a pending university approval request).
  legal_name?: string | null;
  tax_code?: string | null;
  registration_number?: string | null;
  version?: number;
}

/** Result of `updateProfile` — tells the UI which path(s) ran. */
export interface CompanyProfileUpdateResult {
  /** Cosmetic fields written to the live profile just now (may be empty). */
  applied: string[];
  /** True when a sensitive change created/merged a pending request. */
  requires_approval: boolean;
  /** The open pending request after this edit, or null when none. */
  pending_change_request: CompanyChangeRequest | null;
  /** The refreshed profile (with cosmetic changes applied). */
  profile: CompanyProfile;
}

/** University approve result — the decided request + the refreshed profile. */
export interface CompanyApprovalDecisionResult {
  status: string;
  request: CompanyChangeRequest;
  profile: CompanyProfile;
}

export const companyProfileApi = {
  /* ----------------------------- Partner ----------------------------- */

  /** GET the full company profile (legal fields + pending request + docs). */
  getProfile(orgId: string): Promise<CompanyProfile> {
    return api.get<CompanyProfile>(`/organizations/${orgId}/profile`);
  },

  /**
   * PUT a profile edit. Cosmetic fields apply immediately; sensitive fields
   * create/merge a pending university request. Inspect `applied` /
   * `requires_approval` on the result to drive the UX.
   */
  updateProfile(
    orgId: string,
    body: CompanyProfileUpdateBody,
  ): Promise<CompanyProfileUpdateResult> {
    return api.put<CompanyProfileUpdateResult>(
      `/organizations/${orgId}/profile`,
      body,
    );
  },

  /**
   * Attach a verification/legal document (multipart). ALWAYS awaits approval —
   * returns the pending change request the file was attached to.
   */
  uploadDocument(
    orgId: string,
    file: File,
    kind?: CompanyDocKind,
  ): Promise<CompanyChangeRequest> {
    const form = new FormData();
    form.append("file", file);
    if (kind) form.append("kind", kind);
    return apiUpload<ApiEnvelope<CompanyChangeRequest>>(
      `/organizations/${orgId}/documents`,
      form,
      { method: "POST" },
    ).then((res) => res.data);
  },

  /** List this org's change requests (optionally filtered by status). */
  listChangeRequests(
    orgId: string,
    status?: CompanyChangeStatus,
  ): Promise<CompanyChangeRequest[]> {
    return api.get<CompanyChangeRequest[]>(
      `/organizations/${orgId}/change-requests`,
      { query: status ? { status } : undefined },
    );
  },

  /** Withdraw a still-pending change request. */
  withdrawChangeRequest(
    orgId: string,
    reqId: string,
  ): Promise<CompanyChangeRequest> {
    return api.post<CompanyChangeRequest>(
      `/organizations/${orgId}/change-requests/${reqId}/withdraw`,
      {},
    );
  },

  /* --------------------------- University ---------------------------- */

  /** Company-approval queue (university reviewer). Defaults to pending. */
  listApprovals(
    status: CompanyChangeStatus = "pending",
  ): Promise<CompanyChangeRequest[]> {
    return api.get<CompanyChangeRequest[]>("/admin/company-approvals", {
      query: { status },
    });
  },

  /** A single change request detail (university reviewer). */
  getApproval(reqId: string): Promise<CompanyChangeRequest> {
    return api.get<CompanyChangeRequest>(`/admin/company-approvals/${reqId}`);
  },

  /** Approve a change request — applies sensitive fields + attaches docs. */
  approve(
    reqId: string,
    body: { note?: string | null; version?: number },
  ): Promise<CompanyApprovalDecisionResult> {
    return api.post<CompanyApprovalDecisionResult>(
      `/admin/company-approvals/${reqId}/approve`,
      body,
    );
  },

  /** Reject a change request. `reason` is required (surfaced to the partner). */
  reject(
    reqId: string,
    body: { reason: string; version?: number },
  ): Promise<CompanyChangeRequest> {
    return api.post<CompanyChangeRequest>(
      `/admin/company-approvals/${reqId}/reject`,
      body,
    );
  },
};
