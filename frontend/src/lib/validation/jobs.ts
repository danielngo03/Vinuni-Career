import { z } from "zod";

type V = (key: string) => string;

const screeningQuestionSchema = (v: V) =>
  z.object({
    question: z.string().trim().min(1, v("required")).max(2000),
    q_type: z.enum(["text", "yes_no", "single_choice", "multiple_choice"]),
    /** Comma-separated options, only used for choice types. */
    options: z.string().max(1000).optional().or(z.literal("")),
    is_required: z.boolean(),
  });

/**
 * Partner job create/edit form schema. Skills + screening options are entered as
 * free text and split into arrays on submit. Numeric fields are kept as strings
 * in the form and coerced by the screen before calling the API.
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
      screening_questions: z.array(screeningQuestionSchema(v)),
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
  headcount: "1",
  application_deadline: "",
  visibility: "public",
  screening_questions: [],
};
