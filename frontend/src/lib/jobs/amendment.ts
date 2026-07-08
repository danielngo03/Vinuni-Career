/**
 * Post-publication amendment policy (B-552) — mirrors backend
 * `app.modules.opportunities.domain.lifecycle.FREE_AMEND_FIELDS` /
 * `REMODERATION_FIELDS`. Once a job is `active`, edits split into:
 *
 * - Free-amend fields: apply immediately, job stays live.
 * - Re-moderation fields: unpublish the job back to `pending_review` for a
 *   fresh university approval pass.
 * - Screening questions: locked entirely once `active` (existing
 *   applications reference the question set by id/order).
 *
 * Keep this list in sync with the backend source of truth; it drives
 * client-side UX only (badges, confirmation copy) — the server enforces the
 * real rule regardless of what the client sends.
 */

export const FREE_AMEND_FORM_FIELDS = new Set<string>([
  "application_deadline",
  "headcount",
  "visibility",
  "benefits",
]);

export const REMODERATION_FORM_FIELDS = new Set<string>([
  "title",
  "description",
  "requirements",
  "employment_type",
  "location_type",
  "location_city",
  "location_country",
  "locations",
  "required_skills",
  "preferred_skills",
  "experience_min_years",
  "experience_max_years",
  "degree_required",
  "salary_is_disclosed",
  "salary_min",
  "salary_max",
  "salary_currency",
  // Structured salary/experience/eligibility fields added in F2
  "salary_mode",
  "salary_period",
  "salary_gross_net",
  "experience_mode",
  "seniority_level",
  "candidate_requirements",
  "industry_id",
]);

export function isFreeAmendField(field: string): boolean {
  return FREE_AMEND_FORM_FIELDS.has(field);
}

export function isRemoderationField(field: string): boolean {
  return REMODERATION_FORM_FIELDS.has(field);
}
