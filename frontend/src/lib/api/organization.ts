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

export const organizationApi = {
  /* Profile */
  get(): Promise<Organization> {
    return api.get<Organization>("/organizations");
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
  listRoles(): Promise<OrgRole[]> {
    return api.get<OrgRole[]>("/organizations/roles");
  },
  createRole(body: {
    name: string;
    description?: string | null;
    permissions: PermissionInput[];
  }): Promise<OrgRole> {
    return api.post<OrgRole>("/organizations/roles", body);
  },
  updateRole(
    id: string,
    body: {
      name?: string | null;
      description?: string | null;
      permissions?: PermissionInput[] | null;
    },
  ): Promise<OrgRole> {
    return api.patch<OrgRole>(`/organizations/roles/${id}`, body);
  },
  deleteRole(id: string): Promise<unknown> {
    return apiFetch(`/organizations/roles/${id}`, { method: "DELETE" });
  },

  /* Departments */
  listDepartments(): Promise<OrgDepartment[]> {
    return api.get<OrgDepartment[]>("/organizations/departments");
  },
  createDepartment(body: {
    name: string;
    parent_id?: string | null;
  }): Promise<OrgDepartment> {
    return api.post<OrgDepartment>("/organizations/departments", body);
  },
  updateDepartment(
    id: string,
    body: { name?: string | null; parent_id?: string | null; clear_parent?: boolean },
  ): Promise<OrgDepartment> {
    return api.patch<OrgDepartment>(`/organizations/departments/${id}`, body);
  },
  deleteDepartment(id: string): Promise<unknown> {
    return apiFetch(`/organizations/departments/${id}`, { method: "DELETE" });
  },

  /* Members */
  listMembers(cursor?: string | null): Promise<ApiListEnvelope<OrgMember>> {
    return api.list<OrgMember>("/organizations/members", {
      query: cursor ? { cursor } : undefined,
    });
  },
  updateMember(
    id: string,
    body: { role_ids?: string[]; department_ids?: string[]; version?: number },
  ): Promise<OrgMember> {
    return api.patch<OrgMember>(`/organizations/members/${id}`, body);
  },
  removeMember(id: string): Promise<unknown> {
    return apiFetch(`/organizations/members/${id}`, { method: "DELETE" });
  },
  /** Suspend a member's access. Reversible — distinct from permanent removal. */
  deactivateMember(id: string): Promise<OrgMember> {
    return api.post<OrgMember>(`/organizations/members/${id}/deactivate`, {});
  },
  /** Restore a previously-suspended member's access. */
  reactivateMember(id: string): Promise<OrgMember> {
    return api.post<OrgMember>(`/organizations/members/${id}/reactivate`, {});
  },

  /* Permission preview */
  previewMemberPermissions(membershipId: string): Promise<PermissionPreview> {
    return api.get<PermissionPreview>(
      `/organizations/members/${membershipId}/permission-preview`,
    );
  },
  previewHypotheticalPermissions(body: {
    role_ids: string[];
    department_ids?: string[];
  }): Promise<PermissionPreview> {
    return api.post<PermissionPreview>("/organizations/permission-preview", body);
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
  listAuditLog(params?: {
    cursor?: string | null;
    actor_id?: string;
    action?: string;
    since?: string;
    until?: string;
  }): Promise<ApiListEnvelope<AuditLogEntry>> {
    const query: Record<string, string> = {};
    if (params?.cursor) query.cursor = params.cursor;
    if (params?.actor_id) query.actor_id = params.actor_id;
    if (params?.action) query.action = params.action;
    if (params?.since) query.since = params.since;
    if (params?.until) query.until = params.until;
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
  listInvitations(): Promise<OrgInvitation[]> {
    return api.get<OrgInvitation[]>("/organizations/invitations");
  },
  createInvitation(body: {
    email: string;
    role_id?: string | null;
    department_id?: string | null;
  }): Promise<OrgInvitation> {
    return api.post<OrgInvitation>("/organizations/invitations", body);
  },
  revokeInvitation(id: string): Promise<unknown> {
    return apiFetch(`/organizations/invitations/${id}`, { method: "DELETE" });
  },
  acceptInvitation(token: string): Promise<OrgMember> {
    return api.post<OrgMember>(
      `/organizations/invitations/${encodeURIComponent(token)}/accept`,
      {},
    );
  },
};
