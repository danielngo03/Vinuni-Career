import { z } from "zod";

type V = (key: string) => string;

export function roleSchema(v: V) {
  return z.object({
    name: z.string().trim().min(2, v("roleNameMin")).max(80),
    description: z.string().trim().max(280).optional().or(z.literal("")),
  });
}
export type RoleValues = z.infer<ReturnType<typeof roleSchema>>;

export function departmentSchema(v: V) {
  return z.object({
    name: z.string().trim().min(2, v("deptNameMin")).max(120),
    parent_id: z.string().optional().or(z.literal("")),
  });
}
export type DepartmentValues = z.infer<ReturnType<typeof departmentSchema>>;

export function invitationSchema(v: V) {
  return z.object({
    email: z.string().min(1, v("required")).email(v("email")),
    role_id: z.string().optional().or(z.literal("")),
    department_id: z.string().optional().or(z.literal("")),
  });
}
export type InvitationValues = z.infer<ReturnType<typeof invitationSchema>>;

export function orgProfileSchema(v: V) {
  return z.object({
    display_name: z.string().trim().min(2, v("companyNameMin")).max(200),
    website_url: z
      .string()
      .trim()
      .url(v("url"))
      .or(z.literal(""))
      .optional(),
    industry: z.string().trim().max(120).optional().or(z.literal("")),
    company_size: z.string().optional().or(z.literal("")),
    headquarters_city: z.string().trim().max(120).optional().or(z.literal("")),
    founded_year: z
      .string()
      .trim()
      .regex(/^\d{4}$/, v("year"))
      .optional()
      .or(z.literal("")),
    description: z.string().trim().max(2000).optional().or(z.literal("")),
  });
}
export type OrgProfileValues = z.infer<ReturnType<typeof orgProfileSchema>>;

/** Shared company-size options for forms (label keys live in i18n). */
export const COMPANY_SIZES = ["1-10", "11-50", "50-200", "200-1000", "1000+"];

/**
 * Phase 1b permission catalog (ADR-0002 §4.1). The UI offers only these
 * resource/action pairs; the escalation ceiling further restricts what an
 * actor may grant to a subset of their own effective permissions.
 */
export interface CatalogResource {
  resource: string;
  actions: string[];
  /** Only relevant to university-org roles. */
  universityOnly?: boolean;
}

export const PERMISSION_CATALOG: CatalogResource[] = [
  { resource: "organizations", actions: ["read", "update"] },
  { resource: "roles", actions: ["read", "create", "update", "delete"] },
  { resource: "departments", actions: ["read", "create", "update", "delete"] },
  { resource: "members", actions: ["read", "invite", "update", "remove"] },
  {
    resource: "jobs",
    actions: ["read", "create", "update", "delete", "submit", "publish", "moderate", "assign_owner"],
  },
  { resource: "events", actions: ["read", "create", "update", "submit", "moderate", "register", "manage"] },
  { resource: "applications", actions: ["read", "update", "review", "reject", "bulk_review", "export"] },
  { resource: "advertising", actions: ["view", "create", "edit", "submit", "manage", "moderate"] },
  { resource: "billing", actions: ["view", "subscribe", "manage", "moderate"] },
  { resource: "ai_settings", actions: ["read", "manage", "view_provider_identity"], universityOnly: true },
  { resource: "cv_templates", actions: ["read", "create", "update"], universityOnly: true },
  { resource: "reviews", actions: ["moderate"], universityOnly: true },
  {
    resource: "partners",
    actions: ["read", "approve", "reject", "manage"],
    universityOnly: true,
  },
  // Visual workflow builder (partner or university owner).
  { resource: "workflow", actions: ["create", "read", "update", "activate"] },
  // Recruiting analytics (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`).
  { resource: "analytics", actions: ["view_job_metrics", "view_clicks", "export"] },
  // Org audit-log read (B-518/523).
  { resource: "audit", actions: ["read"] },
  // Advisory/confirmation-required AI recruiting actions.
  {
    resource: "ai_recruiting",
    actions: ["draft_jd", "screen_candidate", "suggest_scorecard", "move_candidate_with_confirmation"],
  },
  // Sensitive candidate-identity access (B-523) — every use is audited.
  {
    resource: "candidate_identity",
    actions: ["request_reveal", "view_revealed_identity", "view_cv", "download_cv"],
  },
  // Pipeline stage actions, distinct from `applications:*`.
  { resource: "pipeline", actions: ["read", "move_candidate", "rollback", "configure_template"] },
  { resource: "scorecards", actions: ["read", "submit", "read_aggregate", "configure"] },
  { resource: "interviews", actions: ["schedule", "assign", "complete", "cancel", "read"] },
  { resource: "offers", actions: ["create", "approve", "send", "rescind"] },
  // NOTE: career_services_*, notification_templates, support, privacy, and
  // abuse resources exist in the backend catalog (other in-flight backlog
  // items: B-554, notification governance, platform trust) but have no
  // frontend labels yet — omitted here until that work adds them, to avoid
  // an unlabeled resource row in the role editor.
];

/** True when an effective permission set grants `resource:action`. */
export function grants(
  effective: ReadonlySet<string>,
  resource: string,
  action: string,
): boolean {
  return (
    effective.has("*:*") ||
    effective.has(`${resource}:*`) ||
    effective.has(`*:${action}`) ||
    effective.has(`${resource}:${action}`)
  );
}

export const HOLDS_WILDCARD = (effective: ReadonlySet<string>): boolean =>
  effective.has("*:*");
