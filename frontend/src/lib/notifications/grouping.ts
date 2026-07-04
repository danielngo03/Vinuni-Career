import type { Notification } from "@/lib/api";

/** Day bucket the bell center renders headers for (newest first). */
export type DayBucket = "today" | "yesterday" | "older";

export interface NotificationGroup {
  bucket: DayBucket;
  items: Notification[];
}

/** Local-calendar day index (days since epoch in the user's own timezone). */
function localDayIndex(d: Date): number {
  const local = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.floor(local.getTime() / 86_400_000);
}

function bucketFor(createdAt: string, now: Date): DayBucket {
  const created = new Date(createdAt);
  if (Number.isNaN(created.getTime())) return "older";
  const diff = localDayIndex(now) - localDayIndex(created);
  if (diff <= 0) return "today";
  if (diff === 1) return "yesterday";
  return "older";
}

/**
 * Split a flat, server-ordered (newest-first) list into Today / Yesterday /
 * Older sections using the viewer's local timezone. Empty buckets are dropped
 * and original order is preserved within each section.
 */
export function groupByDay(
  items: Notification[],
  now: Date = new Date(),
): NotificationGroup[] {
  const order: DayBucket[] = ["today", "yesterday", "older"];
  const map = new Map<DayBucket, Notification[]>();
  for (const item of items) {
    const bucket = bucketFor(item.created_at, now);
    const arr = map.get(bucket);
    if (arr) arr.push(item);
    else map.set(bucket, [item]);
  }
  return order
    .filter((b) => map.has(b))
    .map((bucket) => ({ bucket, items: map.get(bucket)! }));
}

const DIVISIONS: { amount: number; unit: Intl.RelativeTimeFormatUnit }[] = [
  { amount: 60, unit: "second" },
  { amount: 60, unit: "minute" },
  { amount: 24, unit: "hour" },
  { amount: 7, unit: "day" },
  { amount: 4.34524, unit: "week" },
  { amount: 12, unit: "month" },
  { amount: Number.POSITIVE_INFINITY, unit: "year" },
];

/**
 * Locale-aware "x minutes ago" relative timestamp. Falls back to an empty
 * string for unparseable input so a row never renders a broken date.
 */
export function relativeTime(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const rtf = new Intl.RelativeTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
    numeric: "auto",
  });
  let duration = (date.getTime() - Date.now()) / 1000;
  for (const division of DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return rtf.format(Math.round(duration), division.unit);
    }
    duration /= division.amount;
  }
  return "";
}
