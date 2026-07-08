import type { StatusTone } from "@/components/ui";
import type { CapacityRequestStatus } from "@/lib/api";

/** Map a capacity-request status to a design-system badge tone.
 * Color is never the only signal — callers always pair it with a text label. */
export function capacityStatusTone(status: CapacityRequestStatus): StatusTone {
  if (status === "approved") return "accepted";
  if (status === "denied") return "rejected";
  return "pending";
}

/** Localized absolute date/time (e.g. "Jul 8, 2026, 14:30"). `null` when the
 * input is missing/invalid. Client-only. */
export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

/** Localized short date (e.g. "Jul 8, 2026"). */
export function formatDate(
  iso: string | null | undefined,
  locale: string,
): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(d);
}

/** Localized integer with grouping (opaque energy credits — never money). */
export function formatCredits(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}
