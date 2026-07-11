/** Locale-aware month + year for a date-only ISO value (e.g. profile dates). */
export function formatMonthYear(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
      month: "short",
      year: "numeric",
    }).format(date);
  } catch {
    return iso;
  }
}

/**
 * Relative time label for published/posted dates (e.g. "2 ngày trước").
 * Falls back to a short absolute date when older than 30 days or invalid.
 */
export function formatRelativeTime(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffDays < 0) return "";
  if (diffDays === 0) {
    const diffH = Math.floor(diffMs / 3_600_000);
    if (diffH < 1) return locale === "vi" ? "Vừa đăng" : "Just posted";
    try {
      return new Intl.RelativeTimeFormat(locale === "vi" ? "vi" : "en", {
        numeric: "auto",
      }).format(-diffH, "hour");
    } catch {
      return locale === "vi" ? "Hôm nay" : "Today";
    }
  }
  if (diffDays <= 30) {
    try {
      return new Intl.RelativeTimeFormat(locale === "vi" ? "vi" : "en", {
        numeric: "auto",
      }).format(-diffDays, "day");
    } catch {
      return `${diffDays}d`;
    }
  }
  try {
    return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return "";
  }
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/**
 * Compact day-first date, e.g. `08/03/2026`. Locale-agnostic numeric format
 * (used for dense table columns like deadlines). Pair with `formatDateTimeShort`
 * as a hover tooltip to expose the exact time.
 */
export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;
}

/**
 * Full time-then-date label, e.g. `18:15 08/03/2026`. Used as the hover
 * tooltip/title for a `formatDateShort` cell so the exact deadline time stays
 * one hover away without cluttering the dense column.
 */
export function formatDateTimeShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())} ${formatDateShort(iso)}`;
}

/** Locale-aware date/time formatting for account/security surfaces. */
export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  } catch {
    return iso;
  }
}
