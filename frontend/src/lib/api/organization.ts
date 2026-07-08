import { api, apiFetch, apiUpload } from "./client";
import type { ApiEnvelope, ApiListEnvelope } from "./types";

/* ------------------------------- Wire types ------------------------------- */

export interface Organization {
  id: string;
  slug: string;
  display_name: string;
  org_type: "partner" | "university";
  /**
   * Public, cache-busted (`?v=`) logo URL, or null when no logo is set. The raw
   * storage path is never exposed to the client.
   */
  logo_url?: string | null;
  website_url?: string | null;
  description?: string | null;
  industry?: string | null;
  company_size?: string | null;
  founded_year?: number | null;
  headquarters_city?: string | null;
  is_verified: boolean;
  status: string;
  status_label: string;
  subscription_tier?: string | null;
  /** Max active+pending members. -1 = unlimited (enterprise). Default 4 (free). */
  max_team_members?: number | null;
  trust_level?: string | null;
  settings?: Record<string, unknown>;
  version: number;
  created_at: string;
}

export interface OrgRole {
  id: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  /** Rendered permission strings, e.g. "members:read" or "*:*". */
  permissions: string[];
  created_at: string;
}

export interface OrgDepartment {
  id: string;
  name: string;
  parent_id?: string | null;
  created_at: string;
}

/**
 * A single role grant, optionally scoped to one department (dept-scoped RBAC,
 * P2/WS2.1). `department_id` null/omitted = the role applies ORG-WIDE (identical
 * to a plain `role_ids` entry); a non-null id scopes the role's grants to that
 * department only.
 */
export interface RoleAssignment {
  role_id: string;
  department_id?: string | null;
}

export interface OrgMember {
  id: string;
  /**
   * The member's underlying user id. Required to assign a member as an interview
   * reviewer (assignee_ids are user ids). Optional because some directory
   * projections omit it; the interview assignee picker only lists members that
   * carry a `user_id`.
   */
  user_id?: string | null;
  user_email: string;
  full_name?: string | null;
  /** `active` | `suspended` (deactivated, reversible) | `left` (removed). */
  status: string;
  status_label: string;
  role_ids: string[];
  /**
   * Per-role department scope. Always present in current responses (defaults to
   * one org-wide entry per `role_ids` when a member has no scoped roles). Kept
   * optional for backwards/forwards compatibility with directory projections.
   */
  role_assignments?: RoleAssignment[];
  department_ids: string[];
  version: number;
  joined_at: string;
}

/* --------------------------- Permission preview --------------------------- */

export interface PermissionPreview {
  grants: string[];
  is_admin: boolean;
  by_resource: Record<string, string[]>;
  membership_id?: string;
  membership_status?: string;
  role_ids?: string[];
  department_ids?: string[];
}

/* ------------------------------- Ownership -------------------------------- */

export interface OwnershipInfo {
  owner_membership_id: string | null;
}

/* ------------------------------- Audit log --------------------------------- */

export interface AuditLogEntry {
  id: number;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  occurred_at: string | null;
}

/* --------------------------------- CRM ------------------------------------- */

export interface ProfileQualityCheck {
  check: string;
  met: boolean;
  points: number;
}

export interface ProfileQuality {
  score: number;
  breakdown: ProfileQualityCheck[];
  missing: string[];
}

export interface RecruiterSeats {
  used: number;
  limit: number | null;
  unlimited: boolean;
  at_capacity: boolean;
}

export interface CampusOwner {
  campus_relationship_owner_id: string | null;
}

export type RiskFlagSeverity = "low" | "medium" | "high";

export interface OrgRiskFlag {
  id: string;
  flag_type: string;
  severity: RiskFlagSeverity;
  note?: string | null;
  raised_by: string;
  raised_at: string;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
  is_resolved: boolean;
}

export interface OrgNote {
  id: string;
  body: string;
  created_by: string;
  created_at: string;
}

export interface CrmActivityRollup {
  events: { total: number; by_status: Record<string, number> };
  campaigns: { total: number; by_status: Record<string, number> };
}

export interface HiringOutcomes {
  total_applications: number;
  hired: number;
  offers_accepted: number;
  recent_applications: number;
  window_months: number;
}

export interface OrgInvitation {
  id: string;
  email: string;
  role_id?: string | null;
  department_id?: string | null;
  status: string;
  status_label: string;
  expires_at: string;
  created_at: string;
}

export interface PermissionInput {
  resource: string;
  action: string;
}

export interface OrganizationPatch {
  display_name?: string;
  website_url?: string | null;
  description?: string | null;
  industry?: string | null;
  company_size?: string | null;
  founded_year?: number | null;
  headquarters_city?: string | null;
  version?: number;
}

/* --------------------------------- Calls ---------------------------------- */

/**
 * Superadmin cross-org scope helper. When a managed org id is supplied (the
 * university/superadmin team-screen path), it is appended as `?org_id=` — a
 * param the backend honours ONLY for superadmins and ignores for everyone else.
 * When omitted (the partner/self path), this returns `undefined` so the request
 * is byte-for-byte identical to before: the caller's own `principal.org_id`.
 */
function orgScope(orgId?: string | null): { org_id: string } | undefined {
  return orgId ? { org_id: orgId } : undefined;
}

export const organizationApi = {
  /* Profile */
  get(): Promise<Organization> {
    return api.get<Organization>("/organizations");
  },
  /**
   * "The org I manage" — for a superadmin this resolves to the single university
   * org when no `orgId` is given (or the explicit `orgId` for cross-org
   * management); for an org member it is their own org. Used by the university
   * team screen to discover the org id it then threads as `?org_id=` everywhere.
   */
  getCurrent(orgId?: string | null): Promise<Organization> {
    return api.get<Organization>("/organizations/current", { query: orgScope(orgId) });
  },
  update(body: OrganizationPatch): Promise<Organization> {
    return api.patch<Organization>("/organizations", body);
  },

  /**
   * Upload (replace) the org logo. Sent as multipart/form-data — never
   * JSON-encoded — so the browser sets the boundary. Optimistic `version`
   * guards against concurrent edits (stale → 409 CONFLICT). Returns the updated
   * org detail with a fresh, cache-busted `logo_url`.
   */
  uploadLogo(orgId: string, file: File, version?: number): Promise<Organization> {
    const form = new FormData();
    form.append("file", file);
    if (version !== undefined) form.append("version", String(version));
    return apiUpload<ApiEnvelope<Organization>>(
      `/organizations/${orgId}/logo`,
      form,
    ).then((res) => res.data);
  },
  /** Remove the org logo. Returns the updated org detail with `logo_url: null`. */
  removeLogo(orgId: string, version?: number): Promise<Organization> {
    return api.delete<Organization>(`/organizations/${orgId}/logo`, {
      query: version !== undefined ? { version } : undefined,
    });
  },

  /* Roles */
  listRoles(orgId?: string | null): Promise<OrgRole[]> {
    return api.get<OrgRole[]>("/organizations/roles", { query: orgScope(orgId) });
  },
  createRole(
    body: {
      name: string;
      description?: string | null;
      permissions: PermissionInput[];
    },
    orgId?: string | null,
  ): Promise<OrgRole> {
    return api.post<OrgRole>("/organizations/roles", body, { query: orgScope(orgId) });
  },
  updateRole(
    id: string,
    body: {
      name?: string | null;
      description?: string | null;
      permissions?: PermissionInput[] | null;
    },
    orgId?: string | null,
  ): Promise<OrgRole> {
    return api.patch<OrgRole>(`/organizations/roles/${id}`, body, {
      query: orgScope(orgId),
    });
  },
  deleteRole(id: string, orgId?: string | null): Promise<unknown> {
    return apiFetch(`/organizations/roles/${id}`, {
      method: "DELETE",
      query: orgScope(orgId),
    });
  },

  /* Departments */
  listDepartments(orgId?: string | null): Promise<OrgDepartment[]> {
    return api.get<OrgDepartment[]>("/organizations/departments", {
      query: orgScope(orgId),
    });
  },
  createDepartment(
    body: {
      name: string;
      parent_id?: string | null;
    },
    orgId?: string | null,
  ): Promise<OrgDepartment> {
    return api.post<OrgDepartment>("/organizations/departments", body, {
      query: orgScope(orgId),
    });
  },
  updateDepartment(
    id: string,
    body: { name?: string | null; parent_id?: string | null; clear_parent?: boolean },
    orgId?: string | null,
  ): Promise<OrgDepartment> {
    return api.patch<OrgDepartment>(`/organizations/departments/${id}`, body, {
      query: orgScope(orgId),
    });
  },
  deleteDepartment(id: string, orgId?: string | null): Promise<unknown> {
    return apiFetch(`/organizations/departments/${id}`, {
      method: "DELETE",
      query: orgScope(orgId),
    });
  },

  /* Members */
  listMembers(
    cursor?: string | null,
    orgId?: string | null,
  ): Promise<ApiListEnvelope<OrgMember>> {
    const query: Record<string, string> = {};
    if (cursor) query.cursor = cursor;
    if (orgId) query.org_id = orgId;
    return api.list<OrgMember>("/organizations/members", {
      query: Object.keys(query).length ? query : undefined,
    });
  },
  updateMember(
    id: string,
    body: {
      /** Legacy org-wide role set. Mutually exclusive with `role_assignments`. */
      role_ids?: string[];
      /**
       * Department-scoped role set (authoritative — REPLACES `role_ids`). Send
       * this instead of `role_ids` when any role carries a `department_id`.
       */
      role_assignments?: RoleAssignment[];
      department_ids?: string[];
      version?: number;
    },
    orgId?: string | null,
  ): Promise<OrgMember> {
    return api.patch<OrgMember>(`/organizations/members/${id}`, body, {
      query: orgScope(orgId),
    });
  },
  removeMember(id: string, orgId?: string | null): Promise<unknown> {
    return apiFetch(`/organizations/members/${id}`, {
      method: "DELETE",
      query: orgScope(orgId),
    });
  },
  /** Suspend a member's access. Reversible — distinct from permanent removal. */
  deactivateMember(id: string, orgId?: string | null): Promise<OrgMember> {
    return api.post<OrgMember>(`/organizations/members/${id}/deactivate`, {}, {
      query: orgScope(orgId),
    });
  },
  /** Restore a previously-suspended member's access. */
  reactivateMember(id: string, orgId?: string | null): Promise<OrgMember> {
    return api.post<OrgMember>(`/organizations/members/${id}/reactivate`, {}, {
      query: orgScope(orgId),
    });
  },

  /* Permission preview */
  previewMemberPermissions(
    membershipId: string,
    orgId?: string | null,
  ): Promise<PermissionPreview> {
    return api.get<PermissionPreview>(
      `/organizations/members/${membershipId}/permission-preview`,
      { query: orgScope(orgId) },
    );
  },
  previewHypotheticalPermissions(
    body: {
      role_ids: string[];
      department_ids?: string[];
    },
    orgId?: string | null,
  ): Promise<PermissionPreview> {
    return api.post<PermissionPreview>("/organizations/permission-preview", body, {
      query: orgScope(orgId),
    });
  },

  /* Ownership */
  getOwnership(): Promise<OwnershipInfo> {
    return api.get<OwnershipInfo>("/organizations/ownership");
  },
  transferOwnership(body: {
    target_membership_id: string;
    confirm: boolean;
  }): Promise<OwnershipInfo> {
    return api.post<OwnershipInfo>("/organizations/ownership/transfer", body);
  },

  /* Audit log */
  listAuditLog(
    params?: {
      cursor?: string | null;
      actor_id?: string;
      action?: string;
      since?: string;
      until?: string;
    },
    orgId?: string | null,
  ): Promise<ApiListEnvelope<AuditLogEntry>> {
    const query: Record<string, string> = {};
    if (params?.cursor) query.cursor = params.cursor;
    if (params?.actor_id) query.actor_id = params.actor_id;
    if (params?.action) query.action = params.action;
    if (params?.since) query.since = params.since;
    if (params?.until) query.until = params.until;
    if (orgId) query.org_id = orgId;
    return api.list<AuditLogEntry>("/organizations/audit-log", { query });
  },

  /* Employer CRM (B-553) */
  getProfileQuality(orgId: string): Promise<ProfileQuality> {
    return api.get<ProfileQuality>(`/organizations/${orgId}/profile-quality`);
  },
  getRecruiterSeats(orgId: string): Promise<RecruiterSeats> {
    return api.get<RecruiterSeats>(`/organizations/${orgId}/recruiter-seats`);
  },
  getCrmActivity(orgId: string): Promise<CrmActivityRollup> {
    return api.get<CrmActivityRollup>(`/organizations/${orgId}/crm/activity`);
  },
  getHiringOutcomes(orgId: string): Promise<HiringOutcomes> {
    return api.get<HiringOutcomes>(`/organizations/${orgId}/crm/hiring-outcomes`);
  },
  getCampusOwner(orgId: string): Promise<CampusOwner> {
    return api.get<CampusOwner>(`/organizations/${orgId}/campus-owner`);
  },
  setCampusOwner(orgId: string, ownerUserId: string | null): Promise<CampusOwner> {
    return api.put<CampusOwner>(`/organizations/${orgId}/campus-owner`, {
      owner_user_id: ownerUserId,
    });
  },
  listRiskFlags(orgId: string): Promise<OrgRiskFlag[]> {
    return api.get<OrgRiskFlag[]>(`/organizations/${orgId}/risk-flags`);
  },
  raiseRiskFlag(
    orgId: string,
    body: { flag_type: string; severity: RiskFlagSeverity; note?: string | null },
  ): Promise<OrgRiskFlag> {
    return api.post<OrgRiskFlag>(`/organizations/${orgId}/risk-flags`, body);
  },
  resolveRiskFlag(
    orgId: string,
    flagId: string,
    resolutionNote?: string | null,
  ): Promise<OrgRiskFlag> {
    return api.post<OrgRiskFlag>(
      `/organizations/${orgId}/risk-flags/${flagId}/resolve`,
      { resolution_note: resolutionNote ?? null },
    );
  },
  listNotes(orgId: string): Promise<OrgNote[]> {
    return api.get<OrgNote[]>(`/organizations/${orgId}/notes`);
  },
  createNote(orgId: string, body: string): Promise<OrgNote> {
    return api.post<OrgNote>(`/organizations/${orgId}/notes`, { body });
  },

  /* Invitations */
  listInvitations(orgId?: string | null): Promise<OrgInvitation[]> {
    return api.get<OrgInvitation[]>("/organizations/invitations", {
      query: orgScope(orgId),
    });
  },
  createInvitation(
    body: {
      email: string;
      role_id?: string | null;
      department_id?: string | null;
    },
    orgId?: string | null,
  ): Promise<OrgInvitation> {
    return api.post<OrgInvitation>("/organizations/invitations", body, {
      query: orgScope(orgId),
    });
  },
  revokeInvitation(id: string, orgId?: string | null): Promise<unknown> {
    return apiFetch(`/organizations/invitations/${id}`, {
      method: "DELETE",
      query: orgScope(orgId),
    });
  },
  acceptInvitation(token: string): Promise<OrgMember> {
    return api.post<OrgMember>(
      `/organizations/invitations/${encodeURIComponent(token)}/accept`,
      {},
    );
  },
};
