import { z } from "zod";

type V = (key: string) => string;

/**
 * Slim identity-profile form schema. The profile now holds only contact +
 * location (career content lives in the student's CVs). Text fields are kept
 * as strings and coerced to the API shape by the screen before submit;
 * business rules are re-checked server-side.
 */
export function contactProfileSchema(v: V) {
  return z.object({
    phone: z.string().trim().max(30, v("phoneMax")).optional().or(z.literal("")),
    location_city: z.string().trim().max(100).optional().or(z.literal("")),
    location_country: z.string().trim().max(100).optional().or(z.literal("")),
  });
}
export type ContactProfileValues = z.infer<ReturnType<typeof contactProfileSchema>>;
