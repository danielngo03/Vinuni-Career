import { api, apiFetch, apiUpload } from "./client";
import type { ApiListEnvelope } from "./types";

/* ------------------------------- Vocabularies ----------------------------- */

export type JobStatus =
  | "draft"
  | "pending_review"
  | "active"
  | "rejected"
  | "closed"
  | "expired";

export type ModerationStatus = "pending" | "approved" | "rejected" | "flagged";

/** Structured moderation reject/escalate reason vocabulary (`app.shared.moderation`). */
export type ModerationReasonCode =
  | "duplicate_listing"
  | "misleading_content"
  | "policy_violation"
  | "incomplete_info"
  | "spam"
  | "other";

export const MODERATION_REASON_CODES: ModerationReasonCode[] = [
  "duplicate_listing",
  "misleading_content",
  "policy_violation",
  "incomplete_info",
  "spam",
  "other",
];

/** Per-item result row from a bulk approve/reject call — partial success is normal. */
export interface BulkModerationResultItem {
  id: string;
  success: boolean;
  error_code?: string;
  message?: string;
}

export type EmploymentType =
  | "full_time"
  | "part_time"
  | "internship"
  | "contract";

export type LocationType = "onsite" | "remote" | "hybrid";

export type JobVisibility =
  | "public"
  | "authenticated"
  | "students_only"
  | "vinuni_only"
  | "invitation_only";

// Keep these for internal form schemas and type-guard usage only.
// The public filter chips must NOT render from these — use jobsApi.getConfig() instead.
export const EMPLOYMENT_TYPES: EmploymentType[] = [
  "full_time",
  "part_time",
  "internship",
  "contract",
];
export const LOCATION_TYPES: LocationType[] = ["onsite", "remote", "hybrid"];

export interface JobsConfig {
  employment_types: EmploymentType[];
  location_types: LocationType[];
}
export const JOB_VISIBILITIES: JobVisibility[] = [
  "public",
  "authenticated",
  "students_only",
  "vinuni_only",
  "invitation_only",
];

/* ------------------------------- Wire types ------------------------------- */

export interface JobSalary {
  min: number | null;
  max: number | null;
  currency: string;
}

/**
 * `hidden`/`fixed` are current server-authoritative kinds; `up_to` is a
 * legacy kind that may still appear on old data rows. Client code must not
 * assume this list is exhaustive — always fall back to rendering `label`.
 */
export type JobSalaryKind =
  | "negotiable"
  | "hidden"
  | "fixed"
  | "range"
  | "from"
  | "to"
  | "up_to";

export interface JobSalaryDisplay {
  kind: JobSalaryKind;
  label: string;
  min: number | null;
  max: number | null;
  currency: string;
  period?: "monthly" | "yearly";
  gross_net?: "unspecified" | "gross" | "net";
}

/**
 * `no_requirement`/`fresher`/`min`/`max`/`up_to` are current server kinds;
 * `not_required`/`from`/`fixed` may still appear on legacy data rows. Client
 * code must not assume this list is exhaustive — always fall back to `label`.
 */
export type JobExperienceKind =
  | "no_requirement"
  | "fresher"
  | "range"
  | "min"
  | "max"
  | "from"
  | "up_to"
  | "fixed"
  | "not_required";

export interface JobExperienceDisplay {
  kind: JobExperienceKind;
  label: string;
  min: number | null;
  max: number | null;
}

export interface JobCompanyRatingSummary {
  overall_avg: number | null;
  review_count: number;
}

/**
 * Lightweight company reference embedded on public job projections. `logo_url`
 * is nullable — render an initials placeholder when null. `null` company means
 * the owning partner is not currently listable; show the role without an
 * employer chip.
 */
export interface JobCompanyRef {
  slug: string;
  display_name: string;
  logo_url: string | null;
  is_verified: boolean;
  rating: JobCompanyRatingSummary | null;
}

/** A single worksite entry for multi-location job postings. */
export interface JobLocationItem {
  type: LocationType | string;
  province_code: string | null;
  ward_code?: string | null;
  ward_name?: string | null;
  city: string | null;
  country: string;
}

/* -------------------- Candidate requirements vocabulary ------------------- */

export type RequirementMode = "not_required" | "required" | "preferred";
export type AgeMode = "not_required" | "at_least" | "up_to" | "range";
export type SalaryMode = "negotiable" | "hidden" | "fixed" | "range" | "from" | "to";
export type SalaryPeriod = "monthly" | "yearly";
export type SalaryGrossNet = "unspecified" | "gross" | "net";
export type ExperienceMode = "no_requirement" | "fresher" | "range" | "min" | "max";

export interface RequirementGroup { mode: RequirementMode; values: string[]; note?: string | null; }
export interface AgeRequirement { mode: AgeMode; min?: number | null; max?: number | null; }
export interface LanguageRequirement { language: string; proficiency?: string | null; required: boolean; }
export interface CertificationRequirement { name: string; required: boolean; }
export interface CandidateRequirements {
  education?: RequirementGroup;
  nationalities?: RequirementGroup;
  gender?: RequirementGroup;
  age?: AgeRequirement;
  marital_status?: RequirementGroup;
  languages?: LanguageRequirement[];
  certifications?: CertificationRequirement[];
  note?: string | null;
}

export type JobStudentFitTier = "strong" | "good" | "possible" | "weak" | "no_cv";
export type JobStudentFitSignal = "ok" | "low_signal" | "no_cv";

export interface JobStudentFitCvScore {
  cv_id: string;
  title: string;
  score: number;
  tier: JobStudentFitTier;
  bands: StudentFitBands;
  matched_skills: string[];
  gap_count: number;
  stale: boolean;
  recommended: boolean;
}

export interface JobStudentFitSummary {
  score: number | null;
  tier: JobStudentFitTier;
  recommended_cv_id: string | null;
  recommended_cv_title: string | null;
  matched_skills: string[];
  gap_count: number;
  signal: JobStudentFitSignal;
  bands: StudentFitBands | null;
  cv_scores: JobStudentFitCvScore[];
}

/** Fields shared by every job projection (public + owner). */
export interface JobSummary {
  id: string;
  org_id: string;
  title: string;
  slug: string;
  employment_type: string;
  employment_type_label: string;
  location_type: string;
  location_type_label: string;
  location_city: string | null;
  location_country: string;
  /** Multi-location: always at least one item (synthesized from legacy fields when empty). */
  locations: JobLocationItem[];
  required_skills: string[];
  salary: JobSalary | null;
  salary_display: JobSalaryDisplay;
  experience_display: JobExperienceDisplay;
  is_featured: boolean;
  is_sponsored: boolean;
  application_deadline: string | null;
  published_at: string | null;
  /** Embedded employer chip on public projections. Null when not listable. */
  company?: JobCompanyRef | null;
  /** True when the authenticated student has saved this job. Always false for guests. */
  is_saved?: boolean;
  /** Authenticated student/alumni only: lightweight CV-JD fit summary for cards. */
  student_fit?: JobStudentFitSummary | null;
  /**
   * Coarse role family derived server-side from the job title
   * (`discovery/domain/taxonomy.role_family_of`), e.g. "software_engineering".
   * Drives the privacy-safe `role_families` discovery signal.
   *
   * OPTIONAL + BACKEND-PENDING (WS-12 Task E handoff): the public job
   * projection does not stamp this yet, so it is currently always undefined and
   * no `role_families` tag is emitted from job surfaces. Once the backend adds
   * it, {@link ../discovery/signal-tags} emits it automatically. Never a UUID —
   * always a coarse family key.
   */
  role_family?: string | null;
  /**
   * Coarse, tokenizable industry slug (e.g. "information-technology") for the
   * privacy-safe `industries` discovery signal.
   *
   * OPTIONAL + BACKEND-PENDING (WS-12 Task E handoff): the current projection
   * only carries the opaque `industry_id` UUID (on the DETAIL shape), which is
   * deliberately NOT emitted as a coarse tag (a UUID is not a coarse industry
   * token). Once the backend stamps a slug/label here, it is emitted
   * automatically.
   */
  industry_slug?: string | null;
}

/** Public discovery detail — never carries moderation/owner internals. */
export interface PublicJobDetail extends JobSummary {
  description: string;
  requirements: string | null;
  benefits: string | null;
  preferred_skills: string[];
  experience_min_years: number | null;
  experience_max_years: number | null;
  degree_required: string | null;
  headcount: number;
  view_count: number;
  /** BCP-47 language code of the original JD: "vi" | "en" | "mixed" | "unknown" */
  language_code?: string;
  /** Structured salary/experience/candidate fields — optional for backward compat. */
  salary_mode?: string | null;
  salary_period?: string | null;
  salary_gross_net?: string | null;
  experience_mode?: string | null;
  seniority_level?: string | null;
  candidate_requirements?: CandidateRequirements | null;
  /** Industry taxonomy id (level 0–2 node). Null when not set. */
  industry_id?: string | null;
  /**
   * CV document language required by the partner for this posting.
   * "any" (default) = no restriction. "en" / "vi" = soft preference only —
   * students can still apply with any CV but see a warning on mismatch.
   */
  cv_language_required?: "any" | "en" | "vi";
}

/** Translated JD fields returned by POST /jobs/{id}/translate */
export interface JobTranslation {
  title: string | null;
  description: string | null;
  requirements: string | null;
  benefits: string | null;
  language_code: string;
  target_lang: string;
  from_cache: boolean;
}

/** Owner/moderator list row — adds lifecycle + moderation status. */
export interface OwnerJobSummary extends JobSummary {
  status: JobStatus;
  status_label: string;
  moderation_status: ModerationStatus;
  moderation_status_label: string;
  moderation_reason_code?: ModerationReasonCode | string | null;
  moderation_reason_label?: string | null;
  visibility: JobVisibility;
  version: number;
  created_at: string;
  /** Moderation queue assignment (claim/SLA — university moderation only). */
  claimed_by?: string | null;
  claimed_at?: string | null;
  due_by?: string | null;
  age_hours?: number | null;
  is_overdue?: boolean;
}

/** Full owner/moderator detail (org members of the owning org + superadmin). */
export interface OwnerJobDetail extends PublicJobDetail {
  posted_by: string;
  visibility: JobVisibility;
  status: JobStatus;
  status_label: string;
  moderation_status: ModerationStatus;
  moderation_status_label: string;
  moderation_note: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  closed_at: string | null;
  application_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface JobCreateBody {
  title: string;
  description: string;
  requirements?: string | null;
  benefits?: string | null;
  employment_type: string;
  location_type: string;
  location_city?: string | null;
  location_country?: string;
  /** Multi-location worksites. First item = primary (populates legacy location_* fields). */
  locations?: JobLocationItem[];
  required_skills?: string[];
  preferred_skills?: string[];
  experience_min_years?: number | null;
  experience_max_years?: number | null;
  degree_required?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string;
  salary_is_disclosed?: boolean;
  headcount?: number;
  application_deadline?: string | null;
  visibility?: string;
  salary_mode?: string | null;
  salary_period?: string;
  salary_gross_net?: string;
  experience_mode?: string | null;
  seniority_level?: string | null;
  industry_id?: string | null;
  candidate_requirements?: CandidateRequirements | null;
  /**
   * CV document language requirement for this posting.
   * "any" = no restriction (server default). "en" / "vi" = soft preference.
   */
  cv_language_required?: "any" | "en" | "vi";
}

export type JobUpdateBody = Partial<JobCreateBody> & { version?: number };

/** Competition level vocabulary for job competition signal. */
export type CompetitionLevel = "low" | "medium" | "high" | "very_high";

/**
 * Competition signal returned by GET /jobs/{job_id}/competition-signal.
 * Public data — shown to all viewers (guests, students, partners).
 */
export interface CompetitionSignal {
  level: CompetitionLevel;
  /** Localised label from the backend (e.g. "Trung bình"). */
  label: string;
  explanation: string | null;
  ai_explanation_available: boolean;
  basis: "live" | "estimated";
  updated_at: string;
}

/* ---------------------- Student job intelligence (E35) --------------------- */

/** `cv_job_fit_reports.score_label` vocabulary — never raw model confidence. */
export type StudentFitLabel =
  | "strong_fit"
  | "good_fit"
  | "possible_fit"
  | "weak_fit";

export interface StudentFitBands {
  skills: number;
  experience: number;
  scope: number;
  credentials: number;
  soft_skills: number;
  trajectory: number;
}

/**
 * Fit sub-object of `GET /jobs/{job_id}/student-intelligence`. `status ===
 * "no_active_cv"` means the student has no eligible CV yet — every scored
 * field is null and `improvement_actions` carries a single "create a CV" hint.
 */
export interface StudentJobFit {
  status: "scored" | "no_active_cv";
  score: number | null;
  label: StudentFitLabel | null;
  bands: StudentFitBands | null;
  matched_evidence: string[];
  gaps: string[];
  improvement_actions: string[];
  signal?: "ok" | "low_signal";
  stale?: boolean;
  /** Optional, output-guarded — null when no explanation is available. */
  explanation?: string | null;
}

/** Bucketed, privacy-safe competition intelligence — never per-applicant data. */
export interface StudentCompetitionIntelligence {
  /** Null when `signal === "low_signal"` — never invent a precise score. */
  score: number | null;
  label: "low" | "moderate" | "high" | "very_high" | null;
  signal: "ok" | "low_signal";
  /**
   * Whether the headline reads on real applicant caliber (deep enough scored
   * pool) or on capped application volume (honest cold-start). Null in
   * `low_signal`. Never exposes a raw count — only the interpretation basis.
   */
  basis: "applicant_caliber" | "application_volume" | null;
  seats_bucket: "single_seat" | "small_batch" | "batch" | "mass_hiring";
  application_volume_bucket: "low" | "medium" | "high" | "very_high";
  /** Total applicants relative to seats — band only, never a count. */
  applicants_per_seat_band: "low_signal" | "low" | "moderate" | "high" | "very_high";
  /** Strong (high-fit) applicants per seat — the quality-adjusted headline driver. */
  strong_competitor_density: "low_signal" | "few" | "some" | "many";
  /** Aggregate applicant-pool quality bucket; "unknown" below the sample threshold. */
  applicant_quality_bucket: "unknown" | "strong" | "mixed" | "developing";
  /** The student's coarse standing within the scored pool; "unknown" below threshold. */
  student_standing_bucket: "unknown" | "ahead_of_most" | "middle_of_pack" | "behind_most";
  /** Where the student's own fit sits versus the strong competitor pool. */
  standing_vs_strong: "low_signal" | "ahead" | "among" | "behind";
  student_fit_bucket:
    | "unknown"
    | "needs_improvement"
    | "developing"
    | "competitive"
    | "highly_competitive";
  deadline_freshness:
    | "no_deadline"
    | "long_runway"
    | "closing_soon"
    | "final_days"
    | "closed";
  /** Null when too few discovery events exist to form a meaningful ratio. */
  source_mix: Record<string, number> | null;
  guidance: string[];
}

/**
 * A confirmation-gated CV-Studio "apply this improvement" hand-off. Built by the
 * backend (`cv_gap_handoff`) from a real fit gap; the frontend POSTs `request`
 * (adding its own `idempotency_key`) to `endpoint` to open the existing
 * natural-language CV-edit flow, which ALWAYS returns a pending diff the student
 * must explicitly accept — never an auto-applied edit. Leak-safe (no
 * provider/model/token/score internals).
 */
export interface CvImprovementHandoff {
  action: "cv_edit_command";
  method: "POST";
  /** Absolute API path, e.g. `/api/v1/cvs/{cv_id}/ai-edit-command`. */
  endpoint: string;
  cv_id: string;
  skill: string;
  /** Advisory rationale copy — never asserts the student HAS the skill. */
  rationale: string | null;
  /** Ready-to-send body; the client attaches its own `idempotency_key`. */
  request: { instruction: string };
  requires_confirmation: boolean;
}

export interface StudentLearningGap {
  skill: string;
  suggestion: string;
  resource_type: string;
  /**
   * Closed-loop hand-off to draft an improvement for this gap on the student's
   * CV (confirmation-gated, never auto-applied). Null when no target CV exists.
   */
  cv_edit: CvImprovementHandoff | null;
}

export interface StudentApplyReadiness {
  ready: boolean;
  blocked_reason: "already_applied" | "deadline_passed" | "no_active_cv" | null;
  already_applied: boolean;
  deadline_passed: boolean;
  has_active_cv: boolean;
}

export type StudentNextActionType =
  | "select_best_cv"
  | "improve_cv"
  | "apply"
  | "save_job"
  | "compare_adjacent_roles";

export interface StudentNextAction {
  action: StudentNextActionType;
  label: string;
  cv_id?: string;
  ready?: boolean;
  blocked_reason?: StudentApplyReadiness["blocked_reason"];
}

/**
 * `GET /jobs/{job_id}/student-intelligence` response — authenticated-student
 * only. Combines best-CV recommendation, CV-JD fit, bucketed competition
 * intelligence, learning gaps, apply readiness, and next actions. Never
 * exposes other applicants, exact ranks, raw CV text, raw model confidence,
 * or provider/model/prompt/token internals (docs/API_CONTRACTS.md §Student
 * Job Intelligence).
 */
export interface StudentJobIntelligence {
  job_id: string;
  selected_cv_id: string | null;
  best_cv_id: string | null;
  fit: StudentJobFit;
  competition: StudentCompetitionIntelligence;
  learning_gaps: StudentLearningGap[];
  apply_readiness: StudentApplyReadiness;
  next_actions: StudentNextAction[];
}

/** One matched requirement with its evidence strength (leak-safe — no confidence). */
export interface FitMatchedEvidence {
  requirement: string;
  cv_evidence: string | null;
  evidence_strength: "strong" | "moderate" | "weak";
  reasoning: string;
}

/** One confirmed gap with an advisory (never accusatory) suggestion. */
export interface FitAnalysisGap {
  requirement: string;
  cv_evidence: string | null;
  severity: "hard" | "soft";
  reasoning: string;
  suggestion: string;
}

/**
 * Structured matching detail (`semantic_scorer.analysis_payload`) — the
 * per-requirement matched evidence, confirmed gaps, and overall suggestion the
 * older contract discarded. Null when the AI narrative is unavailable. The
 * model-mirrored score is deliberately absent (it would read as raw confidence).
 */
export interface FitAnalysis {
  overall_suggestion: string;
  matched_evidence: FitMatchedEvidence[];
  gaps: FitAnalysisGap[];
}

/**
 * `GET /jobs/{job_id}/fit-explanation?cv_id=...` — the on-demand, LLM-backed
 * analysis for a specific CV, fired ONLY when the student opens the "Analyze CV"
 * drawer (energy-metered; cached per `(cv, job)`). `explanation`/`analysis` are
 * null when the AI assessment is unavailable (AI offline, low-signal, exhausted
 * energy); the caller degrades gracefully rather than surfacing an error.
 * `improvements` are confirmation-gated CV-Studio hand-offs (one per fit gap),
 * present even when the AI narrative is off. Never carries
 * provider/model/token/prompt/confidence internals.
 */
export interface StudentFitExplanation {
  cv_id: string | null;
  explanation: string | null;
  analysis: FitAnalysis | null;
  improvements: CvImprovementHandoff[];
  /**
   * Internal curated learning foci (one per fit gap) — a deterministic mapping,
   * NOT confirmation-gated CV edits. Distinct from `improvements`: these are
   * "what to study/practice", rendered as advisory reading, with no external
   * URLs and no provider/model internals. Empty when there is nothing to suggest.
   */
  learning_resources: StudentLearningResource[];
  ai_explanation_available: boolean;
}

/**
 * One curated learning focus for a fit gap. `resource_type` is a stable code
 * the client localizes into an icon + label (e.g. course/practice/reading);
 * `suggestion` is already-localized advisory copy. Never a real URL, never an
 * assertion that the student lacks the skill.
 */
export interface StudentLearningResource {
  skill: string;
  resource_type: string;
  suggestion: string;
}

/**
 * `GET /jobs/{job_id}/competition-explanation` — the on-demand AI narrative that
 * explains the competition bands, fired ONLY when the student opens the
 * "Competition" drawer (energy-metered; cached per `(job, level)`). The
 * deterministic bands come free from `student-intelligence.competition`; AI
 * never moves the numbers. `explanation` is null (with `ai_explanation_available:
 * false`) on AI-off / provider error / exhausted energy / low signal — never an
 * error, never a raw count/rank/identity or provider/model/token internals.
 */
export interface CompetitionExplanation {
  level: "low" | "moderate" | "high" | "very_high" | null;
  label: string | null;
  explanation: string | null;
  ai_explanation_available: boolean;
}

/** Result from the JD document upload + AI extraction endpoint. */
export interface JdUploadResult {
  is_ai_extraction: boolean;
  prompt_version: number;
  // Structured fields (populated when is_ai_extraction=true)
  title?: string | null;
  title_en?: string | null;
  description_vi?: string | null;
  description_en?: string | null;
  requirements_vi?: string | null;
  requirements_en?: string | null;
  benefits_vi?: string | null;
  benefits_en?: string | null;
  employment_type?: string | null;
  location_type?: string | null;
  locations?: Array<{ type?: string | null; city: string | null; province_code?: string | null; country: string }>;
  required_skills?: string[];
  preferred_skills?: string[];
  experience_min_years?: number | null;
  experience_max_years?: number | null;
  degree_required?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  salary_is_disclosed?: boolean;
  headcount?: number | null;
  detected_language?: "vi" | "en" | "mixed";
  // Fallback when AI unavailable
  raw_text_preview?: string | null;
  // Extended fields from rebuilt backend extraction
  status?: "ok" | "not_a_jd" | "blank" | "low_quality_scan" | "insufficient" | "ai_unavailable" | string;
  needs_review?: boolean;
  field_confidence?: Record<string, { needs_review: boolean }>;
  salary_mode?: string | null;
  salary_period?: string | null;
  salary_gross_net?: string | null;
  experience_mode?: string | null;
  seniority_level?: string | null;
  industry?: string | null;
  application_deadline?: string | null;
  candidate_requirements?: CandidateRequirements | null;
  /**
   * CV language preference extracted from the JD. Null / undefined when the
   * AI did not detect a specific preference ("any" is the safe default).
   */
  cv_language_required?: "any" | "en" | "vi" | null;
}

/* ------------------------ JD quality-check + preview ----------------------- */

export type JobQualityIssueSeverity = "blocking" | "advisory";

/**
 * One finding from the deterministic JD quality-check rubric
 * (`GET /jobs/{job_id}/quality-check`). `field` is a stable machine key
 * (e.g. "title", "description", "salary", "location_city", "experience")
 * used to route the finding to the matching form
 * field; `message` is already localized server-side.
 */
export interface JobQualityIssue {
  field: string;
  issue: string;
  severity: JobQualityIssueSeverity;
  message: string;
}

export interface JobQualityCheckResult {
  passed: boolean;
  issues: JobQualityIssue[];
}

export type JobPreviewPersona = "guest" | "student";

/** `GET /jobs/{job_id}/preview?as=guest|student` — owner-only pre/post-publish preview. */
export interface JobPreviewResult {
  as: JobPreviewPersona;
  would_be_visible: boolean;
  hidden_reason: "invitation_only" | "visibility_tier" | null;
  preview: PublicJobDetail;
}

/* --------------------------------- Calls ---------------------------------- */

export const jobsApi = {
  /** Job filter enum config from backend — must be called before rendering filter chips. */
  getConfig(): Promise<JobsConfig> {
    return api.get<JobsConfig>("/jobs/config", { skipAuth: true });
  },

  /* Public discovery (guest or any). Cursor pagination + server-side filters. */
  listPublic(opts?: {
    cursor?: string | null;
    page?: number | null;
    limit?: number;
    q?: string | null;
    employment_type?: string | null;
    location_type?: string | null;
    location_types?: string | null;
    province_code?: string | null;
    ward_code?: string | null;
    province_codes?: string | null;
    ward_codes?: string | null;
    /** @deprecated Use `industry_group_id` / `industry_id` / `specialization_id` instead. */
    industry_terms?: string | null;
    /** Level-0 (root) industry node id. Mutually exclusive with `industry_id`/`specialization_id`. */
    industry_group_id?: string | null;
    /** Level-1 (branch) industry node id. Mutually exclusive with `industry_group_id`/`specialization_id`. */
    industry_id?: string | null;
    /** Level-2 (leaf) industry node id. Mutually exclusive with `industry_group_id`/`industry_id`. */
    specialization_id?: string | null;
    salary_min?: number | null;
    salary_max?: number | null;
    experience_min_years?: number | null;
    experience_max_years?: number | null;
    posted_within_days?: number | null;
    sort?: string | null;
  }): Promise<ApiListEnvelope<JobSummary>> {
    return api.list<JobSummary>("/jobs", {
      skipAuth: true,
      query: {
        cursor: opts?.cursor ?? undefined,
        page: opts?.page ?? undefined,
        limit: opts?.limit,
        q: opts?.q ?? undefined,
        employment_type: opts?.employment_type ?? undefined,
        location_type: opts?.location_type ?? undefined,
        location_types: opts?.location_types ?? undefined,
        province_code: opts?.province_code ?? undefined,
        ward_code: opts?.ward_code ?? undefined,
        province_codes: opts?.province_codes ?? undefined,
        ward_codes: opts?.ward_codes ?? undefined,
        industry_terms: opts?.industry_terms ?? undefined,
        industry_group_id: opts?.industry_group_id ?? undefined,
        industry_id: opts?.industry_id ?? undefined,
        specialization_id: opts?.specialization_id ?? undefined,
        salary_min: opts?.salary_min ?? undefined,
        salary_max: opts?.salary_max ?? undefined,
        experience_min_years: opts?.experience_min_years ?? undefined,
        experience_max_years: opts?.experience_max_years ?? undefined,
        posted_within_days: opts?.posted_within_days ?? undefined,
        sort: opts?.sort ?? undefined,
      },
    });
  },

  /** Public/owner detail. Owner gets full detail; otherwise public iff visible. */
  getPublic(jobId: string): Promise<PublicJobDetail> {
    return api.get<PublicJobDetail>(`/jobs/${jobId}`);
  },

  /** Owner/superadmin detail (same shape, but full owner fields). */
  getOwned(jobId: string): Promise<OwnerJobDetail> {
    return api.get<OwnerJobDetail>(`/jobs/${jobId}`);
  },

  /* Partner-scoped management list (all statuses for the caller org). */
  listMine(opts?: {
    cursor?: string | null;
    limit?: number;
    status?: string | null;
  }): Promise<ApiListEnvelope<OwnerJobSummary>> {
    return api.list<OwnerJobSummary>("/jobs/mine", {
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        status: opts?.status ?? undefined,
      },
    });
  },

  create(body: JobCreateBody): Promise<OwnerJobDetail> {
    return api.post<OwnerJobDetail>("/jobs", body);
  },

  update(jobId: string, body: JobUpdateBody): Promise<OwnerJobDetail> {
    return api.patch<OwnerJobDetail>(`/jobs/${jobId}`, body);
  },

  submit(jobId: string): Promise<OwnerJobDetail> {
    return api.post<OwnerJobDetail>(`/jobs/${jobId}/submit`, {});
  },

  /** Preview the JD quality-check rubric before submitting (read-only, no side effect). */
  qualityCheck(jobId: string): Promise<JobQualityCheckResult> {
    return api.get<JobQualityCheckResult>(`/jobs/${jobId}/quality-check`);
  },

  /** Owner-only: preview exactly what a guest/student would see, pre- or post-publish. */
  preview(jobId: string, asPersona: JobPreviewPersona): Promise<JobPreviewResult> {
    return api.get<JobPreviewResult>(`/jobs/${jobId}/preview`, {
      query: { as: asPersona },
    });
  },

  close(jobId: string, version?: number): Promise<OwnerJobDetail> {
    return api.post<OwnerJobDetail>(`/jobs/${jobId}/close`, { version });
  },

  reopen(jobId: string, version?: number): Promise<OwnerJobDetail> {
    return api.post<OwnerJobDetail>(`/jobs/${jobId}/reopen`, { version });
  },

  duplicate(jobId: string): Promise<OwnerJobDetail> {
    return api.post<OwnerJobDetail>(`/jobs/${jobId}/duplicate`, {});
  },

  remove(jobId: string): Promise<unknown> {
    return apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
  },

  /**
   * On-demand JD translation (AI-powered, DB-cached).
   * Returns translated fields or throws ApiError with status 503 when AI unavailable.
   * target_lang: "vi" | "en"
   */
  translateJd(jobId: string, targetLang: string): Promise<JobTranslation> {
    return api.post<JobTranslation>(`/jobs/${jobId}/translate`, undefined, {
      query: { target_lang: targetLang },
    });
  },

  /* University moderation (university org / superadmin). Returns array + meta. */
  listModeration(status?: string | null): Promise<OwnerJobSummary[]> {
    return api.get<OwnerJobSummary[]>("/admin/jobs", {
      query: { status: status ?? undefined },
    });
  },

  /**
   * Approve + publish. Sent with NO body: the moderation request schema makes
   * `reason` mandatory whenever a body is present, so we cannot attach an
   * optimistic `version` here. Approve is idempotent server-side.
   */
  approve(jobId: string): Promise<OwnerJobSummary> {
    return api.post<OwnerJobSummary>(`/admin/jobs/${jobId}/approve`);
  },

  reject(
    jobId: string,
    reason: string,
    version?: number,
    reasonCode?: ModerationReasonCode | string,
  ): Promise<OwnerJobSummary> {
    return api.post<OwnerJobSummary>(`/admin/jobs/${jobId}/reject`, {
      reason,
      reason_code: reasonCode,
      version,
    });
  },

  /** Claim a pending job for review (concurrency-safe; 409 if already claimed). */
  claim(jobId: string): Promise<OwnerJobSummary> {
    return api.post<OwnerJobSummary>(`/admin/jobs/${jobId}/claim`);
  },

  /** Escalate a job to the shared human review queue. */
  escalate(
    jobId: string,
    opts?: { reason_code?: ModerationReasonCode | string; note?: string },
  ): Promise<OwnerJobSummary> {
    return api.post<OwnerJobSummary>(`/admin/jobs/${jobId}/escalate`, opts ?? {});
  },

  /** Approve multiple jobs; each item succeeds/fails independently. */
  bulkApprove(jobIds: string[]): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>("/admin/jobs/bulk-approve", {
      job_ids: jobIds,
    });
  },

  /** Reject multiple jobs; each item succeeds/fails independently. */
  bulkReject(
    items: { id: string; reason: string; reason_code?: ModerationReasonCode | string }[],
  ): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>("/admin/jobs/bulk-reject", { items });
  },

  /* AI: JD Writer — standalone (new job). No existing job required. */
  aiDraftDescriptionStandalone(inputs: JdDraftInputs): Promise<JdDraftResult> {
    return api.post<JdDraftResult>("/jobs/ai-draft-description", inputs);
  },

  /* AI: JD Writer — anchored to an existing job (carries title/context). */
  aiDraftDescription(
    jobId: string,
    inputs: JdDraftInputs,
  ): Promise<JdDraftResult> {
    return api.post<JdDraftResult>(`/jobs/${jobId}/ai-draft-description`, inputs);
  },

  /* JD Upload: partner uploads a PDF/DOCX to prefill job form via OCR+LLM. */
  uploadJd(file: File): Promise<JdUploadResult> {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<JdUploadResult>("/jobs/upload-jd", form);
  },

  /* Saved jobs (Heart affordance, student only). */
  saveJob(jobId: string): Promise<{ saved: boolean; job_id: string }> {
    return api.post(`/jobs/${jobId}/save`);
  },

  unsaveJob(jobId: string): Promise<{ saved: boolean; job_id: string }> {
    return api.delete<{ saved: boolean; job_id: string }>(`/jobs/${jobId}/save`);
  },

  listSaved(opts?: {
    cursor?: string | null;
    limit?: number;
  }): Promise<ApiListEnvelope<JobSummary>> {
    return api.list<JobSummary>("/jobs/saved", {
      query: { cursor: opts?.cursor ?? undefined, limit: opts?.limit },
    });
  },

  /**
   * Fetch the competition signal for a job posting.
   * Public — no auth required; auth is included when available for potential
   * future personalisation but the endpoint is accessible to guests.
   */
  competitionSignal(jobId: string): Promise<CompetitionSignal> {
    return api.get<CompetitionSignal>(`/jobs/${jobId}/competition-signal`);
  },

  /**
   * Combined logged-in student job intelligence: best CV, fit, bucketed
   * competition, learning gaps, apply readiness, next actions.
   * Authenticated-student only — guests/partners must not call this.
   */
  studentIntelligence(
    jobId: string,
    cvId?: string | null,
  ): Promise<StudentJobIntelligence> {
    return api.get<StudentJobIntelligence>(
      `/jobs/${jobId}/student-intelligence`,
      { query: { cv_id: cvId ?? undefined } },
    );
  },

  /**
   * Async AI narrative for the scored CV — fetched separately from (and after)
   * `studentIntelligence` so the deterministic fit ring/bands render instantly
   * while the LLM assessment streams in. `explanation` is null when
   * unavailable; the caller hides the section gracefully. Authenticated-student
   * only. Never exposes provider/model/token/confidence internals.
   */
  fitExplanation(
    jobId: string,
    cvId?: string | null,
  ): Promise<StudentFitExplanation> {
    return api.get<StudentFitExplanation>(`/jobs/${jobId}/fit-explanation`, {
      query: { cv_id: cvId ?? undefined },
    });
  },

  /**
   * On-demand AI narrative for the Competition drawer. Fired ONLY when the
   * student opens the drawer (the deterministic bands render free from
   * `studentIntelligence`). Model-metered + cached; authenticated-student only.
   * `explanation` is null when unavailable — the caller degrades gracefully.
   */
  competitionExplanation(jobId: string): Promise<CompetitionExplanation> {
    return api.get<CompetitionExplanation>(
      `/jobs/${jobId}/competition-explanation`,
    );
  },

  /**
   * Batch card-level fit scores for a page of jobs.
   * Authenticated-student only — 401 for guests/partners.
   * Silent failure is expected: caller ignores errors and shows no badge.
   * Max 50 job_ids per request.
   */
  batchFitScores(jobIds: string[]): Promise<BatchFitScoresResponse> {
    return api.post<BatchFitScoresResponse>("/jobs/fit-scores", { job_ids: jobIds });
  },
};

/* -------------------- Batch fit scores (card-level async) ------------------ */

export interface JobFitScoreEntry {
  score: number;
  recommended_cv_id: string | null;
  signal: "ok" | "low_signal";
  stale: boolean;
}

export interface BatchFitScoresResponse {
  scores: Record<string, JobFitScoreEntry>;
}

export interface JdDraftInputs {
  title?: string;
  employment_type?: string;
  experience_level?: string;
  location?: string;
  required_skills?: string;
  preferred_skills?: string;
  responsibilities?: string;
  benefits?: string;
  partner_instruction?: string;
}

export interface JdDraftResult {
  draft: string;
  prompt_version: number;
}
