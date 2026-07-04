/** Advertising-specific formatting helpers (frozen price, date window, live hints). */

/**
 * Format a decimal-string VND amount (e.g. "1500000.00") as a locale-aware
 * currency string. Returns a dash when the amount is not yet frozen.
 */
export function formatVnd(
  amount: string | null | undefined,
  currency: string | null | undefined,
  locale: string,
): string {
  if (amount == null) return "—";
  const value = Number(amount);
  if (Number.isNaN(value)) return amount;
  const cur = currency || "VND";
  try {
    return new Intl.NumberFormat(locale === "vi" ? "vi-VN" : "en-US", {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toLocaleString(locale === "vi" ? "vi-VN" : "en-US")} ${cur}`;
  }
}

/** Locale-aware date-only formatting for a window endpoint. */
export function formatDate(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
      dateStyle: "medium",
    }).format(date);
  } catch {
    return iso;
  }
}

/** "start – end" window string; either side may be unset. */
export function formatWindow(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: string,
): string {
  if (!start && !end) return "—";
  return `${formatDate(start, locale)} – ${formatDate(end, locale)}`;
}

/** Whole days remaining until `end` (>= 0), or null when `end` is unknown/past info N/A. */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const end = new Date(iso).getTime();
  if (Number.isNaN(end)) return null;
  const ms = end - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

/**
 * Compute the derived window for a draft/create preview: `end = start + days`.
 * Returns ISO strings; `null` start yields a null window.
 */
export function deriveWindow(
  startIso: string | null,
  durationDays: number | null,
): { start: string | null; end: string | null } {
  if (!startIso || durationDays == null) return { start: startIso, end: null };
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return { start: startIso, end: null };
  const end = new Date(start.getTime());
  end.setDate(end.getDate() + durationDays);
  return { start: start.toISOString(), end: end.toISOString() };
}
