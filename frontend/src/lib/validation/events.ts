import { z } from "zod";

type V = (key: string) => string;

/**
 * Partner event create/edit form schema. Datetime fields are kept as
 * `datetime-local` strings in the form and converted to ISO on submit. Capacity
 * is a string (blank = unlimited). Venue is required for onsite/hybrid and
 * ignored for online (the access link is managed separately in V1, ADR-0008).
 */
export function eventFormSchema(v: V) {
  return z
    .object({
      title: z.string().trim().min(3, v("titleMin")).max(500),
      description: z.string().trim().min(10, v("descriptionMin")),
      event_type: z.enum([
        "career_fair",
        "workshop",
        "info_session",
        "networking",
        "webinar",
      ]),
      format: z.enum(["onsite", "online", "hybrid"]),
      venue_name: z.string().trim().max(300).optional().or(z.literal("")),
      venue_address: z.string().trim().max(2000).optional().or(z.literal("")),
      cover_image_path: z
        .string()
        .trim()
        .max(1000)
        .url(v("url"))
        .optional()
        .or(z.literal("")),
      starts_at: z.string().min(1, v("required")),
      ends_at: z.string().min(1, v("required")),
      registration_opens_at: z.string().optional().or(z.literal("")),
      registration_closes_at: z.string().optional().or(z.literal("")),
      capacity: z
        .string()
        .trim()
        .regex(/^\d+$/, v("number"))
        .refine((s) => Number(s) >= 1, v("min1"))
        .optional()
        .or(z.literal("")),
      visibility: z.enum([
        "public",
        "authenticated",
        "students_only",
        "vinuni_only",
        "invitation_only",
      ]),
      tags: z.string().max(2000).optional().or(z.literal("")),
    })
    // Onsite/hybrid events must name a venue.
    .refine(
      (d) => d.format === "online" || (d.venue_name?.trim().length ?? 0) > 0,
      { path: ["venue_name"], message: v("venueRequired") },
    )
    // End must not precede start.
    .refine(
      (d) =>
        !d.starts_at ||
        !d.ends_at ||
        new Date(d.ends_at).getTime() >= new Date(d.starts_at).getTime(),
      { path: ["ends_at"], message: v("endsAfterStart") },
    )
    // Registration must close no later than the event start.
    .refine(
      (d) =>
        !d.registration_closes_at ||
        !d.starts_at ||
        new Date(d.registration_closes_at).getTime() <=
          new Date(d.starts_at).getTime(),
      { path: ["registration_closes_at"], message: v("closeBeforeStart") },
    );
}

export type EventFormValues = z.infer<ReturnType<typeof eventFormSchema>>;

export const EVENT_FORM_DEFAULTS: EventFormValues = {
  title: "",
  description: "",
  event_type: "workshop",
  format: "onsite",
  venue_name: "",
  venue_address: "",
  cover_image_path: "",
  starts_at: "",
  ends_at: "",
  registration_opens_at: "",
  registration_closes_at: "",
  capacity: "",
  visibility: "public",
  tags: "",
};
