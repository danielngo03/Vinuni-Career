import type { EventSummary } from "@/lib/api";

/** The bundled hero/fallback cover used when an event has no `cover_image_url`. */
export const EVENT_COVER_FALLBACK = "/images/career-day-2026.jpg";

function intlLocale(locale: string): string {
  return locale === "vi" ? "vi-VN" : "en-US";
}

function safeDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Locale-aware date only, e.g. "15 thg 7, 2026" / "Jul 15, 2026". */
export function formatEventDate(iso: string | null | undefined, locale: string): string {
  const d = safeDate(iso);
  if (!d) return "—";
  return new Intl.DateTimeFormat(intlLocale(locale), {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(d);
}

function timeOnly(d: Date, locale: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/**
 * Human "when" line. Same-day events read "<date> · 09:00 – 12:00"; multi-day
 * events read "<start date> 09:00 → <end date> 17:00".
 */
export function formatEventWhen(
  startsAt: string | null | undefined,
  endsAt: string | null | undefined,
  locale: string,
): string {
  const start = safeDate(startsAt);
  const end = safeDate(endsAt);
  if (!start) return "—";
  const date = formatEventDate(startsAt, locale);
  if (!end) return `${date} · ${timeOnly(start, locale)}`;
  const sameDay =
    start.getFullYear() === end.getFullYear() &&
    start.getMonth() === end.getMonth() &&
    start.getDate() === end.getDate();
  if (sameDay) {
    return `${date} · ${timeOnly(start, locale)} – ${timeOnly(end, locale)}`;
  }
  return `${date} ${timeOnly(start, locale)} → ${formatEventDate(endsAt, locale)} ${timeOnly(end, locale)}`;
}

/** Compact date for cards: "15 thg 7 · 09:00". */
export function formatEventDateShort(
  startsAt: string | null | undefined,
  locale: string,
): string {
  const start = safeDate(startsAt);
  if (!start) return "—";
  const date = new Intl.DateTimeFormat(intlLocale(locale), {
    day: "numeric",
    month: "short",
  }).format(start);
  return `${date} · ${timeOnly(start, locale)}`;
}

/**
 * The effective registration deadline: explicit `registration_closes_at`, or the
 * event start when no explicit close is set (matches the backend rule).
 */
export function registrationDeadlineIso(event: EventSummary): string | null {
  return event.registration_closes_at ?? event.starts_at ?? null;
}

/** True once the registration window has passed (server is authoritative). */
export function isRegistrationClosed(
  event: EventSummary,
  now: number = Date.now(),
): boolean {
  const deadline = safeDate(registrationDeadlineIso(event));
  if (!deadline) return false;
  return now >= deadline.getTime();
}

/** True when registration has an explicit future open time not yet reached. */
export function isRegistrationNotOpen(
  event: EventSummary,
  now: number = Date.now(),
): boolean {
  const opens = safeDate(event.registration_opens_at);
  if (!opens) return false;
  return now < opens.getTime();
}

/** True for a capacitied event with no confirmed seats left (waitlist territory). */
export function isEventFull(event: EventSummary): boolean {
  return event.capacity !== null && (event.seats_remaining ?? 0) <= 0;
}
