import { api, apiUpload } from "./client";

/* ------------------------------- Vocabularies ----------------------------- */

/** Overall profile discoverability (student_profiles/domain/vocab.py). */
export type ProfileVisibility = "public" | "vinuni_only" | "private";

/** Per-field contact exposure gate. */
export type ContactVisibility = "public" | "invited" | "hidden";

export type OpenToWorkType = "full_time" | "internship" | "part_time" | "contract";
export type DegreeLevel = "undergraduate" | "graduate" | "phd";
/** Experience employment type (same vocabulary as opportunities, kept local). */
export type ProfileEmploymentType =
  | "full_time"
  | "part_time"
  | "internship"
  | "contract";
export type SkillCategory = "technical" | "language" | "soft";

/** Child-collection URL segments (plural) accepted by the API. */
export type ProfileChildKind = "education" | "experience" | "skills" | "links";

export const PROFILE_VISIBILITIES: readonly ProfileVisibility[] = [
  "public",
  "vinuni_only",
  "private",
] as const;

export const CONTACT_VISIBILITIES: readonly ContactVisibility[] = [
  "public",
  "invited",
  "hidden",
] as const;

export const OPEN_TO_WORK_TYPES: readonly OpenToWorkType[] = [
  "full_time",
  "internship",
  "part_time",
  "contract",
] as const;

export const DEGREE_LEVELS: readonly DegreeLevel[] = [
  "undergraduate",
  "graduate",
  "phd",
] as const;

export const PROFILE_EMPLOYMENT_TYPES: readonly ProfileEmploymentType[] = [
  "full_time",
  "part_time",
  "internship",
  "contract",
] as const;

export const SKILL_CATEGORIES: readonly SkillCategory[] = [
  "technical",
  "language",
  "soft",
] as const;

/* ------------------------------- Wire types ------------------------------- */

export interface EducationItem {
  id: string;
  institution: string | null;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean | null;
  gpa: number | null;
  description: string | null;
  sort_order: number | null;
  version: number;
}

export interface ExperienceItem {
  id: string;
  company_name: string | null;
  title: string | null;
  employment_type: string | null;
  employment_type_label: string | null;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean | null;
  description: string | null;
  skills_used: string[];
  sort_order: number | null;
  version: number;
}

export interface SkillItem {
  id: string;
  name: string | null;
  category: string | null;
  category_label: string | null;
  proficiency: number | null;
  sort_order: number | null;
  version: number;
}

export interface LinkItem {
  id: string;
  label: string | null;
  url: string | null;
  sort_order: number | null;
  version: number;
}

/** Full owner profile (GET /students/me/profile). Includes completion + children. */
export interface StudentProfile {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  headline: string | null;
  summary: string | null;
  phone: string | null;
  location_city: string | null;
  location_country: string | null;
  major: string | null;
  degree_level: string | null;
  degree_level_label: string | null;
  graduation_year: number | null;
  profile_visibility: ProfileVisibility | string;
  profile_visibility_label: string;
  show_email: ContactVisibility | string;
  show_email_label: string;
  show_phone: ContactVisibility | string;
  show_phone_label: string;
  is_open_to_work: boolean;
  open_to_work_types: string[];
  open_to_work_type_labels: string[];
  /** 0-100 completion metric (owner-only; never on public projection). */
  profile_completion: number;
  education: EducationItem[];
  experience: ExperienceItem[];
  skills: SkillItem[];
  links: LinkItem[];
  created_at: string;
  updated_at: string;
  version: number;
}

/* ------------------------------- Update bodies ---------------------------- */

export interface UpdateProfileBody {
  headline?: string | null;
  summary?: string | null;
  phone?: string | null;
  location_city?: string | null;
  location_country?: string | null;
  major?: string | null;
  degree_level?: string | null;
  graduation_year?: number | null;
  profile_visibility?: ProfileVisibility;
  show_email?: ContactVisibility;
  show_phone?: ContactVisibility;
  is_open_to_work?: boolean;
  open_to_work_types?: string[];
  /** Optimistic concurrency token; a stale value yields a 409 CONFLICT. */
  expected_version?: number;
}

export interface EducationBody {
  institution?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  gpa?: number | null;
  description?: string | null;
  sort_order?: number;
  expected_version?: number;
}

export interface ExperienceBody {
  company_name?: string | null;
  title?: string | null;
  employment_type?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  description?: string | null;
  skills_used?: string[];
  sort_order?: number;
  expected_version?: number;
}

export interface SkillBody {
  name?: string | null;
  category?: string | null;
  proficiency?: number | null;
  sort_order?: number;
  expected_version?: number;
}

export interface LinkBody {
  label?: string | null;
  url?: string | null;
  sort_order?: number;
  expected_version?: number;
}

export interface DeleteResult {
  id: string;
  deleted: boolean;
}

/**
 * Privacy-gated read of another student's profile
 * (GET /students/{profile_id}/profile). Does NOT include profile_completion,
 * visibility settings, or contact gates. Email/phone only when the student's
 * contact visibility allows it.
 */
export interface PublicStudentProfile {
  id: string;
  user_id: string;
  display_name: string;
  avatar_url: string | null;
  headline: string | null;
  summary: string | null;
  location_city: string | null;
  location_country: string | null;
  major: string | null;
  degree_level: string | null;
  degree_level_label: string | null;
  graduation_year: number | null;
  is_open_to_work: boolean;
  open_to_work_types: string[];
  open_to_work_type_labels: string[];
  education: EducationItem[];
  experience: ExperienceItem[];
  skills: SkillItem[];
  links: LinkItem[];
  profile_visibility: string;
  email?: string;
  phone?: string;
}

export interface SkillSuggestionsResult {
  suggestions: string[];
  is_fallback: boolean;
  prompt_version: number;
}

export interface SummaryDraftResult {
  draft: string;
  is_fallback: boolean;
  prompt_version: number;
}

export interface CareerSnapshotResult {
  snapshot: string;
  is_fallback: boolean;
  prompt_version: number;
}

/* --------------------------------- Calls ---------------------------------- */

export const profileApi = {
  /** Own full profile (lazy-creates an empty profile on first read). */
  getMine(): Promise<StudentProfile> {
    return api.get<StudentProfile>("/students/me/profile");
  },

  /** Update core fields + privacy/visibility (sparse; send expected_version). */
  updateMine(body: UpdateProfileBody): Promise<StudentProfile> {
    return api.patch<StudentProfile>("/students/me/profile", body);
  },

  createEducation(body: EducationBody): Promise<EducationItem> {
    return api.post<EducationItem>("/students/me/profile/education", body);
  },
  updateEducation(id: string, body: EducationBody): Promise<EducationItem> {
    return api.patch<EducationItem>(`/students/me/profile/education/${id}`, body);
  },

  createExperience(body: ExperienceBody): Promise<ExperienceItem> {
    return api.post<ExperienceItem>("/students/me/profile/experience", body);
  },
  updateExperience(id: string, body: ExperienceBody): Promise<ExperienceItem> {
    return api.patch<ExperienceItem>(
      `/students/me/profile/experience/${id}`,
      body,
    );
  },

  createSkill(body: SkillBody): Promise<SkillItem> {
    return api.post<SkillItem>("/students/me/profile/skills", body);
  },
  updateSkill(id: string, body: SkillBody): Promise<SkillItem> {
    return api.patch<SkillItem>(`/students/me/profile/skills/${id}`, body);
  },

  createLink(body: LinkBody): Promise<LinkItem> {
    return api.post<LinkItem>("/students/me/profile/links", body);
  },
  updateLink(id: string, body: LinkBody): Promise<LinkItem> {
    return api.patch<LinkItem>(`/students/me/profile/links/${id}`, body);
  },

  /** Soft-delete a child item. */
  deleteChild(kind: ProfileChildKind, id: string): Promise<DeleteResult> {
    return api.delete<DeleteResult>(`/students/me/profile/${kind}/${id}`);
  },

  /** Upload or replace my avatar (multipart). Returns { avatar_url }. */
  uploadAvatar(file: File): Promise<{ avatar_url: string }> {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<{ avatar_url: string }>("/students/me/avatar", form);
  },

  /** Remove my avatar. Returns { avatar_url: null }. */
  removeAvatar(): Promise<{ avatar_url: null }> {
    return api.delete<{ avatar_url: null }>("/students/me/avatar");
  },

  /** AI-suggested skills the student likely has but hasn't added yet. */
  getAiSkillSuggestions(): Promise<SkillSuggestionsResult> {
    return api.get<SkillSuggestionsResult>("/students/me/ai-skill-suggestions");
  },

  /** AI-drafted "About you" summary paragraph. */
  getAiSummaryDraft(): Promise<SummaryDraftResult> {
    return api.get<SummaryDraftResult>("/students/me/ai-summary-draft");
  },

  /** AI-generated personalized job search snapshot (2-3 sentences). */
  getAiCareerSnapshot(): Promise<CareerSnapshotResult> {
    return api.get<CareerSnapshotResult>("/students/me/ai-career-snapshot");
  },

  /** Privacy-gated public view of another student's profile. */
  getPublic(profileId: string): Promise<PublicStudentProfile> {
    return api.get<PublicStudentProfile>(`/students/${profileId}/profile`);
  },
};
