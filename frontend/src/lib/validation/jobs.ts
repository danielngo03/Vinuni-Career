import { z } from "zod";
import type { CandidateRequirements } from "@/lib/api/jobs";

type V = (key: string) => string;

/**
 * Partner job create/edit form schema. Skills are entered as
 * free text and split into arrays on submit. Numeric fields are kept as strings
 * in the form and coerced by the screen before calling the API.
 *
 * NOTE: `candidate_requirements` is NOT in this schema — it is managed as
 * external component state (see EMPTY_CANDIDATE_REQUIREMENTS / detailToCandidateRequirements).
 */
export function jobFormSchema(v: V) {
  return z
    .object({
      title: z.string().trim().min(3, v("titleMin")).max(255),
      description: z.string().trim().min(10, v("descriptionMin")),
      requirements: z.string().trim().max(10000).optional().or(z.literal("")),
      benefits: z.string().trim().max(10000).optional().or(z.literal("")),
      employment_type: z.enum([
        "full_time",
        "part_time",
        "internship",
        "contract",
      ]),
      location_type: z.enum(["onsite", "remote", "hybrid"]),
      location_city: z.string().trim().max(100).optional().or(z.literal("")),
      location_country: z.string().trim().max(100).min(1, v("required")),
      required_skills: z.string().max(2000).optional().or(z.literal("")),
      preferred_skills: z.string().max(2000).optional().or(z.literal("")),
      experience_min_years: z
        .string()
        .trim()
        .regex(/^\d{1,2}$/, v("number"))
        .optional()
        .or(z.literal("")),
      experience_max_years: z
        .string()
        .trim()
        .regex(/^\d{1,2}$/, v("number"))
        .optional()
        .or(z.literal("")),
      degree_required: z.string().trim().max(30).optional().or(z.literal("")),
      salary_is_disclosed: z.boolean(),
      salary_min: z
        .string()
        .trim()
        .regex(/^\d+$/, v("number"))
        .optional()
        .or(z.literal("")),
      salary_max: z
        .string()
        .trim()
        .regex(/^\d+$/, v("number"))
        .optional()
        .or(z.literal("")),
      salary_currency: z.string().trim().max(5).min(1, v("required")),
      headcount: z
        .string()
        .trim()
        .regex(/^\d+$/, v("number"))
        .refine((s) => Number(s) >= 1, v("min1")),
      application_deadline: z.string().optional().or(z.literal("")),
      visibility: z.enum([
        "public",
        "authenticated",
        "students_only",
        "vinuni_only",
        "invitation_only",
      ]),
      /** Structured salary display mode. */
      salary_mode: z.enum(["negotiable", "hidden", "fixed", "range", "from", "to"]),
      /** Whether salary is per month or per year. */
      salary_period: z.enum(["monthly", "yearly"]),
      /** Whether salary figures are gross or net. */
      salary_gross_net: z.enum(["unspecified", "gross", "net"]),
      /** Structured experience requirement mode. */
      experience_mode: z.enum(["no_requirement", "fresher", "range", "min", "max"]),
      /** Seniority level vocabulary; empty string = not specified. */
      seniority_level: z.string().optional().or(z.literal("")),
      /** Industry taxonomy id; empty string = not specified. */
      industry_id: z.string().optional().or(z.literal("")),
      /**
       * CV document language requirement for this posting. "any" = no
       * restriction (default). "en" / "vi" = soft preference shown to students.
       */
      cv_language_required: z.enum(["any", "en", "vi"]),
      /**
       * Original language the JD text is written in — a HINT sent to the
       * backend (re-resolved server-side) used to seed the student "translate
       * this JD" flow. `undefined` = let the server auto-detect. This is
       * SEPARATE from `cv_language_required` (the candidate's CV language).
       */
      language_code: z.enum(["vi", "en", "ja", "ko", "zh"]).optional(),
    })
    .refine(
      (d) =>
        !d.experience_min_years ||
        !d.experience_max_years ||
        Number(d.experience_max_years) >= Number(d.experience_min_years),
      { path: ["experience_max_years"], message: v("expRange") },
    )
    .refine(
      (d) =>
        !d.salary_min ||
        !d.salary_max ||
        Number(d.salary_max) >= Number(d.salary_min),
      { path: ["salary_max"], message: v("salaryRange") },
    )
    // salary_mode cross-field refinements
    .refine(
      (d) =>
        d.salary_mode !== "range" ||
        (Boolean(d.salary_min) && Boolean(d.salary_max)),
      { path: ["salary_min"], message: v("salaryModeNeedsRange") },
    )
    .refine(
      (d) =>
        d.salary_mode !== "from" || Boolean(d.salary_min),
      { path: ["salary_min"], message: v("salaryModeNeedsMin") },
    )
    .refine(
      (d) =>
        d.salary_mode !== "to" || Boolean(d.salary_max),
      { path: ["salary_max"], message: v("salaryModeNeedsMax") },
    )
    .refine(
      (d) =>
        d.salary_mode !== "fixed" || Boolean(d.salary_min),
      { path: ["salary_min"], message: v("salaryModeNeedsAmount") },
    );
}

export type JobFormValues = z.infer<ReturnType<typeof jobFormSchema>>;

export const JOB_FORM_DEFAULTS: JobFormValues = {
  title: "",
  description: "",
  requirements: "",
  benefits: "",
  employment_type: "internship",
  location_type: "onsite",
  location_city: "",
  location_country: "Vietnam",
  required_skills: "",
  preferred_skills: "",
  experience_min_years: "",
  experience_max_years: "",
  degree_required: "",
  salary_is_disclosed: false,
  salary_min: "",
  salary_max: "",
  salary_currency: "VND",
  salary_mode: "negotiable",
  salary_period: "monthly",
  salary_gross_net: "unspecified",
  experience_mode: "no_requirement",
  seniority_level: "",
  industry_id: "",
  cv_language_required: "any",
  language_code: undefined,
  headcount: "1",
  application_deadline: "",
  visibility: "public",
};

/**
 * Empty candidate requirements object — all groups default to not_required,
 * arrays empty. Used as the initial external state in F6 (CandidateRequirementsPanel).
 */
export const EMPTY_CANDIDATE_REQUIREMENTS: CandidateRequirements = {
  education: { mode: "not_required", values: [] },
  nationalities: { mode: "not_required", values: [] },
  gender: { mode: "not_required", values: [] },
  age: { mode: "not_required" },
  marital_status: { mode: "not_required", values: [] },
  languages: [],
  certifications: [],
  note: null,
};
