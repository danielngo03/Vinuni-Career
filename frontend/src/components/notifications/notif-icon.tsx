import {
  BadgeCheck,
  BadgeDollarSign,
  Bell,
  CalendarCheck,
  CalendarX,
  CheckCircle2,
  ClipboardList,
  Eye,
  Handshake,
  Megaphone,
  MessageSquare,
  UserPlus,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { NotifType } from "@/lib/api";

type NotifTone = "info" | "success" | "danger" | "warning" | "neutral";

interface NotifVisual {
  icon: LucideIcon;
  tone: NotifTone;
}

/** Soft data-viz tint per tone — content colour, never a loud fill (v10). */
const TONE_TINT: Record<NotifTone, { bg: string; fg: string }> = {
  info: { bg: "var(--viz-indigo-soft)", fg: "var(--viz-indigo)" },
  success: { bg: "var(--content-success-soft)", fg: "var(--content-success)" },
  danger: { bg: "var(--content-danger-soft)", fg: "var(--content-danger)" },
  warning: { bg: "var(--content-warning-soft)", fg: "var(--content-warning)" },
  neutral: { bg: "var(--bg-muted)", fg: "var(--text-secondary)" },
};

/**
 * notif_type -> lucide icon + semantic tone. Unknown types fall back to a
 * neutral bell so a new server-side type still renders cleanly. The tile carries
 * a soft data-viz tint (CONTENT colour); unread emphasis lives on the row.
 */
const VISUALS: Record<string, NotifVisual> = {
  "recruitment.reveal_requested": { icon: Eye, tone: "info" },
  "recruitment.reveal_responded": { icon: BadgeCheck, tone: "info" },
  "recruitment.application_received": { icon: UserPlus, tone: "info" },
  "recruitment.application_under_review": { icon: ClipboardList, tone: "info" },
  "recruitment.application_stage_advanced": { icon: CheckCircle2, tone: "success" },
  "recruitment.application_under_rereview": { icon: ClipboardList, tone: "info" },
  "recruitment.application_rejected": { icon: XCircle, tone: "danger" },
  "recruitment.interview_scheduled": { icon: CalendarCheck, tone: "success" },
  "recruitment.interview_rescheduled": { icon: CalendarCheck, tone: "info" },
  "recruitment.interview_cancelled": { icon: CalendarX, tone: "danger" },
  "recruitment.interview_reminder": { icon: CalendarCheck, tone: "info" },
  "recruitment.interview_assigned": { icon: CalendarCheck, tone: "info" },
  "recruitment.interview_reminder_assignee": { icon: CalendarCheck, tone: "info" },
  "recruitment.offer_received": { icon: BadgeDollarSign, tone: "success" },
  "recruitment.offer_expiring": { icon: BadgeDollarSign, tone: "warning" },
  "recruitment.offer_expired": { icon: BadgeDollarSign, tone: "danger" },
  "recruitment.offer_accepted": { icon: Handshake, tone: "success" },
  "recruitment.offer_declined": { icon: XCircle, tone: "danger" },
  "recruitment.offer_rescinded": { icon: XCircle, tone: "danger" },
  "opportunities.job_approved": { icon: CheckCircle2, tone: "success" },
  "opportunities.job_rejected": { icon: XCircle, tone: "danger" },
  "opportunities.job_auto_closed": { icon: XCircle, tone: "neutral" },
  "opportunities.event_registration_confirmed": { icon: CalendarCheck, tone: "success" },
  "opportunities.event_waitlisted": { icon: CalendarCheck, tone: "warning" },
  "opportunities.event_waitlist_promoted": { icon: CalendarCheck, tone: "success" },
  "opportunities.event_cancelled": { icon: CalendarX, tone: "danger" },
  "opportunities.event_reminder": { icon: CalendarCheck, tone: "info" },
  "organization.partner_approved": { icon: Handshake, tone: "success" },
  "messaging.message.received": { icon: MessageSquare, tone: "info" },
  "advertising.placement_approved": { icon: Megaphone, tone: "success" },
  "advertising.placement_rejected": { icon: Megaphone, tone: "danger" },
};

const FALLBACK: NotifVisual = { icon: Bell, tone: "neutral" };

/** Maps a notif_type to its i18n category key for the category pill. */
const CATEGORY_KEYS: Record<string, string> = {
  "recruitment.reveal_requested": "application",
  "recruitment.reveal_responded": "application",
  "recruitment.application_received": "application",
  "recruitment.application_under_review": "application",
  "recruitment.application_stage_advanced": "application",
  "recruitment.application_under_rereview": "application",
  "recruitment.application_rejected": "application",
  "recruitment.interview_scheduled": "interview",
  "recruitment.interview_rescheduled": "interview",
  "recruitment.interview_cancelled": "interview",
  "recruitment.interview_reminder": "interview",
  "recruitment.interview_assigned": "interview",
  "recruitment.interview_reminder_assignee": "interview",
  "recruitment.offer_received": "offer",
  "recruitment.offer_expiring": "offer",
  "recruitment.offer_expired": "offer",
  "recruitment.offer_accepted": "offer",
  "recruitment.offer_declined": "offer",
  "recruitment.offer_rescinded": "offer",
  "opportunities.job_approved": "job",
  "opportunities.job_rejected": "job",
  "opportunities.job_auto_closed": "job",
  "opportunities.event_registration_confirmed": "event",
  "opportunities.event_waitlisted": "event",
  "opportunities.event_waitlist_promoted": "event",
  "opportunities.event_cancelled": "event",
  "opportunities.event_reminder": "event",
  "organization.partner_approved": "organization",
  "messaging.message.received": "message",
  "advertising.placement_approved": "advertising",
  "advertising.placement_rejected": "advertising",
};

/**
 * Returns the i18n key for the category pill label, or null for unknown types.
 * Consumers use this with `t("notifications.categories.${key}")`.
 */
export function notifCategoryKey(type: NotifType): string | null {
  return CATEGORY_KEYS[type as string] ?? null;
}

/** Soft-tinted glyph tile for a notification row. Decorative (aria-hidden). */
export function NotifIcon({ type }: { type: NotifType; active?: boolean }) {
  const visual = VISUALS[type as string] ?? FALLBACK;
  const Icon = visual.icon;
  const tint = TONE_TINT[visual.tone];
  return (
    <span
      aria-hidden
      className="flex size-9 shrink-0 items-center justify-center rounded-xl"
      style={{ background: tint.bg, color: tint.fg }}
    >
      <Icon strokeWidth={1.8} className="size-[18px]" />
    </span>
  );
}
