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
