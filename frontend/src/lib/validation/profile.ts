import { z } from "zod";

type V = (key: string) => string;

/**
 * Student-profile form schemas. Text/number fields are kept as strings in the
 * form and coerced to the API shape by the screen before submit (mirrors
 * validation/jobs.ts). Vocabulary + business rules are re-checked server-side.
 */

export function coreProfileSchema(v: V) {
  return z.object({
    headline: z.string().trim().max(255, v("headlineMax")).optional().or(z.literal("")),
    summary: z.string().trim().max(5000, v("summaryMax")).optional().or(z.literal("")),
    phone: z.string().trim().max(30, v("phoneMax")).optional().or(z.literal("")),
    location_city: z.string().trim().max(100).optional().or(z.literal("")),
    location_country: z.string().trim().max(100).optional().or(z.literal("")),
    major: z.string().trim().max(200, v("majorMax")).optional().or(z.literal("")),
    degree_level: z.string().optional().or(z.literal("")),
    graduation_year: z.string().optional().or(z.literal("")),
  });
}
export type CoreProfileValues = z.infer<ReturnType<typeof coreProfileSchema>>;

export function educationSchema(v: V) {
  return z
    .object({
      institution: z.string().trim().min(1, v("required")).max(255),
      degree: z.string().trim().max(100).optional().or(z.literal("")),
      field_of_study: z.string().trim().max(200).optional().or(z.literal("")),
      start_date: z.string().optional().or(z.literal("")),
      end_date: z.string().optional().or(z.literal("")),
      is_current: z.boolean(),
      gpa: z
        .string()
        .trim()
        .regex(/^(?:[0-3](?:\.\d{1,2})?|4(?:\.0{1,2})?)$/, v("gpaRange"))
        .optional()
        .or(z.literal("")),
      description: z.string().trim().max(5000).optional().or(z.literal("")),
    })
    .refine(
      (d) => !(d.start_date && d.end_date) || d.end_date >= d.start_date,
      { path: ["end_date"], message: v("endBeforeStart") },
    );
}
export type EducationValues = z.infer<ReturnType<typeof educationSchema>>;

export function experienceSchema(v: V) {
  return z
    .object({
      company_name: z.string().trim().min(1, v("required")).max(255),
      title: z.string().trim().min(1, v("required")).max(255),
      employment_type: z.string().optional().or(z.literal("")),
      location: z.string().trim().max(200).optional().or(z.literal("")),
      start_date: z.string().optional().or(z.literal("")),
      end_date: z.string().optional().or(z.literal("")),
      is_current: z.boolean(),
      skills_used: z.string().max(1000).optional().or(z.literal("")),
      description: z.string().trim().max(5000).optional().or(z.literal("")),
    })
    .refine(
      (d) => !(d.start_date && d.end_date) || d.end_date >= d.start_date,
      { path: ["end_date"], message: v("endBeforeStart") },
    );
}
export type ExperienceValues = z.infer<ReturnType<typeof experienceSchema>>;

export function linkSchema(v: V) {
  return z.object({
    label: z.string().trim().max(100).optional().or(z.literal("")),
    url: z
      .string()
      .trim()
      .min(1, v("required"))
      .max(500)
      .regex(/^https?:\/\/.+/i, v("urlInvalid")),
  });
}
export type LinkValues = z.infer<ReturnType<typeof linkSchema>>;

export function skillSchema(v: V) {
  return z.object({
    name: z.string().trim().min(1, v("required")).max(100),
    category: z.string().optional().or(z.literal("")),
    proficiency: z.string().optional().or(z.literal("")),
  });
}
export type SkillValues = z.infer<ReturnType<typeof skillSchema>>;
