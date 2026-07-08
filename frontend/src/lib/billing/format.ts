/**
 * Billing-local formatting helpers. The money/date/window/days-left logic is
 * shared with the advertising surface (same frozen-decimal + ISO-window shapes),
 * so we re-export it here behind a billing-namespaced import path.
 */
export {
  formatVnd,
  formatDate,
  formatWindow,
  daysUntil,
} from "@/lib/advertising/format";
