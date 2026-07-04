import { z } from "zod";

type V = (key: string) => string;

const optionalUrl = (v: V) =>
  z
    .string()
    .trim()
    .url(v("url"))
    .or(z.literal(""))
    .optional();

const optionalText = z.string().trim().max(2000).optional().or(z.literal(""));

/** Public partner self-registration form (API_CONTRACTS Partner Registration). */
export function partnerRegistrationSchema(v: V) {
  return z.object({
    company_name: z.string().trim().min(2, v("companyNameMin")).max(200),
    tax_code: z.string().trim().max(50).optional().or(z.literal("")),
    company_website: optionalUrl(v),
    company_size: z.string().optional().or(z.literal("")),
    industry: z.string().trim().max(120).optional().or(z.literal("")),
    contact_name: z.string().trim().min(2, v("contactNameMin")).max(120),
    contact_title: z.string().trim().max(120).optional().or(z.literal("")),
    email: z.string().min(1, v("required")).email(v("email")),
    phone: z
      .string()
      .trim()
      .max(30)
      .regex(/^[+()\d\s-]*$/, v("phone"))
      .optional()
      .or(z.literal("")),
    description: optionalText,
  });
}

export type PartnerRegistrationValues = z.infer<
  ReturnType<typeof partnerRegistrationSchema>
>;
