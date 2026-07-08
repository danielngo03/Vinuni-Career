import {
  Bell,
  CalendarCheck,
  CalendarX,
  ChatText,
  CheckCircle,
  ClipboardText,
  Eye,
  Handshake,
  Megaphone,
  Money,
  SealCheck,
  UserPlus,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { NotifType } from "@/lib/api";

interface NotifVisual {
  icon: Icon;
  gradient: string;
}

/**
 * notif_type -> Phosphor duotone icon + bold gradient tone. Unknown types fall
 * back to a neutral bell so a new server-side type still renders cleanly.
 */
const VISUALS: Record<string, NotifVisual> = {
  "recruitment.reveal_requested": {
    icon: Eye,
    gradient: "icon-chip-primary",
  },
  "recruitment.reveal_responded": {
    icon: SealCheck,
    gradient: "icon-chip-primary",
  },
  "recruitment.application_received": {
    icon: UserPlus,
    gradient: "icon-chip-primary",
  },
  "recruitment.application_under_review": {
    icon: ClipboardText,
    gradient: "icon-chip-primary",
  },
  "recruitment.application_stage_advanced": {
    icon: CheckCircle,
    gradient: "icon-chip-success",
  },
  "recruitment.application_under_rereview": {
    icon: ClipboardText,
    gradient: "icon-chip-primary",
  },
  "recruitment.application_rejected": {
    icon: XCircle,
    gradient: "icon-chip-danger",
  },
  "recruitment.interview_scheduled": {
    icon: CalendarCheck,
    gradient: "icon-chip-success",
  },
  "recruitment.interview_rescheduled": {
    icon: CalendarCheck,
    gradient: "icon-chip-primary",
  },
  "recruitment.interview_cancelled": {
    icon: CalendarX,
    gradient: "icon-chip-danger",
  },
  "recruitment.interview_reminder": {
    icon: CalendarCheck,
    gradient: "icon-chip-primary",
  },
  "recruitment.interview_assigned": {
    icon: CalendarCheck,
    gradient: "icon-chip-primary",
  },
  "recruitment.interview_reminder_assignee": {
    icon: CalendarCheck,
    gradient: "icon-chip-primary",
  },
  "recruitment.offer_received": {
    icon: Money,
    gradient: "icon-chip-success",
  },
  "recruitment.offer_expiring": {
    icon: Money,
    gradient: "icon-chip-warning",
  },
  "recruitment.offer_expired": {
    icon: Money,
    gradient: "icon-chip-danger",
  },
  "recruitment.offer_accepted": {
    icon: Handshake,
    gradient: "icon-chip-success",
  },
  "recruitment.offer_declined": {
    icon: XCircle,
    gradient: "icon-chip-danger",
  },
  "recruitment.offer_rescinded": {
    icon: XCircle,
    gradient: "icon-chip-danger",
  },
  "opportunities.job_approved": {
    icon: CheckCircle,
    gradient: "icon-chip-success",
  },
  "opportunities.job_rejected": {
    icon: XCircle,
    gradient: "icon-chip-danger",
  },
  "opportunities.job_auto_closed": {
    icon: XCircle,
    gradient: "icon-chip-neutral",
  },
  "opportunities.event_registration_confirmed": {
    icon: CalendarCheck,
    gradient: "icon-chip-success",
  },
  "opportunities.event_waitlisted": {
    icon: CalendarCheck,
    gradient: "icon-chip-warning",
  },
  "opportunities.event_waitlist_promoted": {
    icon: CalendarCheck,
    gradient: "icon-chip-success",
  },
  "opportunities.event_cancelled": {
    icon: CalendarX,
    gradient: "icon-chip-danger",
  },
  "opportunities.event_reminder": {
    icon: CalendarCheck,
    gradient: "icon-chip-primary",
  },
  "organization.partner_approved": {
    icon: Handshake,
    gradient: "icon-chip-success",
  },
  "messaging.message.received": {
    icon: ChatText,
    gradient: "icon-chip-primary",
  },
  "advertising.placement_approved": {
    icon: Megaphone,
    gradient: "icon-chip-success",
  },
  "advertising.placement_rejected": {
    icon: Megaphone,
    gradient: "icon-chip-danger",
  },
};

const FALLBACK: NotifVisual = {
  icon: Bell,
  gradient: "icon-chip-neutral",
};

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

/** Neutral duotone glyph for a notification row. Decorative (aria-hidden). */
export function NotifIcon({
  type,
  active = false,
}: {
  type: NotifType;
  active?: boolean;
}) {
  const visual = VISUALS[type] ?? FALLBACK;
  const IconCmp = visual.icon;
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)]",
        active
          ? "bg-[var(--text-primary)] text-white"
          : "bg-[var(--bg-muted)] text-[var(--text-secondary)]",
      )}
    >
      <IconCmp weight="duotone" className="size-[18px]" />
    </span>
  );
}
