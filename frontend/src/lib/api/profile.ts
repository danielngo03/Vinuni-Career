import { api, apiUpload } from "./client";

/* ------------------------------- Vocabularies ----------------------------- */

/** Overall profile discoverability (student_profiles/domain/vocab.py). */
export type ProfileVisibility = "public" | "vinuni_only" | "private";

/** Per-field contact exposure gate. */
export type ContactVisibility = "public" | "invited" | "hidden";

/**
 * Open-to-work employment types. Retained for the partner talent-search
 * filters (the `/students/talent` list endpoint), even though the slim
 * identity profile now exposes `is_open_to_work` as a single boolean.
 */
export type OpenToWorkType = "full_time" | "internship" | "part_time" | "contract";

/** Degree levels — retained for the partner talent-search filter. */
export type DegreeLevel = "undergraduate" | "graduate" | "phd";

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

/* ------------------------------- Wire types ------------------------------- */

/**
 * Slim owner identity profile (GET /students/me/profile). Career content now
 * lives entirely in the student's CVs (max 5); this profile is identity +
 * contact + open-to-work + privacy only. `display_name` and `email` are
 * account-owned and read-only here.
 */
export interface StudentProfile {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  phone: string | null;
  location_city: string | null;
  location_country: string | null;
  is_open_to_work: boolean;
  profile_visibility: ProfileVisibility | string;
  profile_visibility_label: string;
  show_email: ContactVisibility | string;
  show_email_label: string;
  show_phone: ContactVisibility | string;
  show_phone_label: string;
  created_at: string;
  updated_at: string;
  version: number;
}

/* ------------------------------- Update bodies ---------------------------- */

export interface UpdateProfileBody {
  phone?: string | null;
  location_city?: string | null;
  location_country?: string | null;
  is_open_to_work?: boolean;
  profile_visibility?: ProfileVisibility;
  show_email?: ContactVisibility;
  show_phone?: ContactVisibility;
  /** Optimistic concurrency token; a stale value yields a 409 CONFLICT. */
  expected_version?: number;
}

/**
 * Privacy-gated read of another student's identity profile
 * (GET /students/{profile_id}/profile). Recruiters view career content in the
 * student's CVs, not here — this is name/location/open-to-work + gated contact
 * only. Email/phone appear only when the student's contact visibility allows.
 */
export interface PublicStudentProfile {
  id: string;
  user_id: string;
  display_name: string;
  avatar_url: string | null;
  location_city: string | null;
  location_country: string | null;
  is_open_to_work: boolean;
  profile_visibility: string;
  email?: string;
  phone?: string;
}

/* --------------------------------- Calls ---------------------------------- */

export const profileApi = {
  /** Own identity profile (lazy-creates an empty profile on first read). */
  getMine(): Promise<StudentProfile> {
    return api.get<StudentProfile>("/students/me/profile");
  },

  /** Update contact + open-to-work + privacy (sparse; send expected_version). */
  updateMine(body: UpdateProfileBody): Promise<StudentProfile> {
    return api.patch<StudentProfile>("/students/me/profile", body);
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

  /** Privacy-gated public view of another student's identity profile. */
  getPublic(profileId: string): Promise<PublicStudentProfile> {
    return api.get<PublicStudentProfile>(`/students/${profileId}/profile`);
  },
};
