import { api } from "./client";

/**
 * AI governance API — university AI-energy DISTRIBUTION (not billing).
 *
 * Two audiences share this module:
 *   - University staff submit/read their own capacity requests when their
 *     distributed weekly AI energy runs out (no self-serve upgrade path).
 *   - Platform superadmins run the capacity-request queue and distribute weekly
 *     energy ceilings down the org → department → user tree.
 *
 * Energy is ALWAYS opaque product credits + a masked remaining `energy_pct`
 * (0..100). This surface never exposes tokens, USD, provider, or model — the
 * same masking rule applies to ordinary university staff, not just end users.
 */

/* ------------------------------- Wire types ------------------------------- */

/** Lifecycle of a capacity request. `pending` awaits a superadmin decision. */
export type CapacityRequestStatus = "pending" | "approved" | "denied";

/**
 * One AI capacity request. Staff always request against their own USER scope;
 * the backend may also model DEPARTMENT-scope requests, so `scope_type` is a
 * plain string. `requested_units` / decision fields are opaque energy credits.
 */
export interface AiCapacityRequest {
  id: string;
  org_id: string;
  requested_by: string;
  scope_type: string;
  scope_id: string;
  reason: string;
  requested_units: number | null;
  status: CapacityRequestStatus;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/**
 * A capacity request in the superadmin queue. Enriched with the requester's
 * identity so the queue is actionable without a second round-trip. On approve
 * the decided payload also echoes `granted_units`.
 */
export interface AiCapacityRequestQueueItem extends AiCapacityRequest {
  requested_by_email: string | null;
  requested_by_name: string | null;
}

/** Decided-request payload (approve echoes the granted amount). */
export interface AiCapacityRequestDecided extends AiCapacityRequest {
  granted_units?: number | null;
}

export interface SubmitCapacityRequestBody {
  reason: string;
  /** Optional desired weekly energy credits; the admin may grant a different amount. */
  requested_units?: number | null;
}

export interface DecideCapacityRequestBody {
  decision: "approve" | "deny";
  /** Required on approve unless the request already carries `requested_units`. */
  granted_units?: number | null;
  note?: string | null;
}

/* ----------------------------- Distribution ------------------------------- */

/** A distribution scope: the org pool, a department, or an individual member. */
export type AllocationScopeType = "org" | "department" | "user";

/** The org energy pool. `weekly_allowance_units` is the explicit ceiling
 * (`null` = the persona default applies); `effective_allowance_units` is the
 * resolved cap actually enforced. `energy_pct` = remaining, 0..100. */
export interface AiAllocationOrgNode {
  scope_type: "org";
  scope_id: string;
  weekly_allowance_units: number | null;
  effective_allowance_units: number;
  wallet_units: number;
  units_used: number;
  energy_pct: number | null;
}

/** A department node. `weekly_allowance_units === null` → inherits the org pool
 * (then `energy_pct` is `null`, as the node has no own cap). */
export interface AiAllocationDepartmentNode {
  scope_type: "department";
  scope_id: string;
  name: string;
  weekly_allowance_units: number | null;
  wallet_units: number;
  units_used: number;
  energy_pct: number | null;
}

/** A member node. `weekly_allowance_units === null` → inherits department/org. */
export interface AiAllocationMemberNode {
  scope_type: "user";
  scope_id: string;
  email: string | null;
  name: string | null;
  department_ids: string[];
  weekly_allowance_units: number | null;
  wallet_units: number;
  units_used: number;
  energy_pct: number | null;
}

/** Live distribution read-model for one org (`GET /admin/ai/allocations`). */
export interface AiAllocations {
  org_id: string;
  org_type: string;
  /** ISO date of the current week's start (Mon 00:00 UTC). */
  week_start: string;
  org: AiAllocationOrgNode;
  departments: AiAllocationDepartmentNode[];
  members: AiAllocationMemberNode[];
}

/** Upsert one scope's ceiling. `weekly_allowance_units: null` clears it → the
 * scope inherits its parent pool again. */
export interface UpsertAllocationBody {
  scope_type: AllocationScopeType;
  scope_id: string;
  org_id: string;
  weekly_allowance_units: number | null;
}

export interface UpsertAllocationResult {
  id: string;
  scope_type: string;
  scope_id: string;
  org_id: string | null;
  weekly_allowance_units: number | null;
  wallet_units: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const aiGovernanceApi = {
  /* ---- University staff ---- */

  /** Submit a capacity request against my own user allocation. 409 if I already
   * have a pending one. */
  submitCapacityRequest(
    body: SubmitCapacityRequestBody,
  ): Promise<AiCapacityRequest> {
    return api.post<AiCapacityRequest>(
      "/university/ai/capacity-requests",
      body,
    );
  },

  /** My capacity requests, newest first. */
  myCapacityRequests(): Promise<AiCapacityRequest[]> {
    return api.get<AiCapacityRequest[]>(
      "/university/ai/capacity-requests/me",
    );
  },

  /* ---- Superadmin: capacity-request queue ---- */

  /** The capacity-request queue, filtered by status (default `pending`). */
  listCapacityRequests(
    status: CapacityRequestStatus = "pending",
  ): Promise<AiCapacityRequestQueueItem[]> {
    return api.get<AiCapacityRequestQueueItem[]>(
      "/admin/ai/capacity-requests",
      { query: { status } },
    );
  },

  /** Approve (raise the target ceiling) or deny a pending request. Audited. */
  decideCapacityRequest(
    id: string,
    body: DecideCapacityRequestBody,
  ): Promise<AiCapacityRequestDecided> {
    return api.post<AiCapacityRequestDecided>(
      `/admin/ai/capacity-requests/${id}/decide`,
      body,
    );
  },

  /* ---- Superadmin: distribution ---- */

  /** Live distribution read-model for an org (pool + departments + members). */
  listAllocations(orgId: string): Promise<AiAllocations> {
    return api.get<AiAllocations>("/admin/ai/allocations", {
      query: { org_id: orgId },
    });
  },

  /** Set or clear one scope's weekly energy ceiling. Audited. */
  upsertAllocation(
    body: UpsertAllocationBody,
  ): Promise<UpsertAllocationResult> {
    return api.put<UpsertAllocationResult>("/admin/ai/allocations", body);
  },
};
