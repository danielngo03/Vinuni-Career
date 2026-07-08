"use client";

import { useTranslations } from "next-intl";
import type {
  EventModerationStatus,
  EventStatus,
  RegistrationState,
} from "@/lib/api";
import type { StatusTone } from "@/components/ui";

/**
 * Localized enum labels for events. The backend pairs every enum code with a
 * `*_label` (currently vi-only), so for vi/en parity we map the stable enum CODE
 * through next-intl here and fall back to the server label (then the raw code)
 * for any unknown value. Raw enum codes are never shown to the user.
 */
export function useEventLabels() {
  const t = useTranslations("events.enums");

  const make =
    (group: string) =>
    (code: string | null | undefined, serverLabel?: string | null): string => {
      if (!code) return serverLabel || "—";
      const key = `${group}.${code}`;
      if (t.has(key)) return t(key);
      return serverLabel || code;
    };

  return {
    eventType: make("eventType"),
    format: make("format"),
    registrationState: make("registrationState"),
    status: make("status"),
    moderation: make("moderation"),
    visibility: make("visibility"),
  };
}

/** Map a registration state to a StatusBadge tone (color + label, never color alone). */
export const REGISTRATION_STATE_TONE: Record<RegistrationState, StatusTone> = {
  confirmed: "accepted",
  waitlisted: "pending",
  cancelled: "closed",
  attended: "verified",
  no_show: "rejected",
};

/** Map an event lifecycle status to a StatusBadge tone. */
export const EVENT_STATUS_TONE: Record<EventStatus, StatusTone> = {
  draft: "draft",
  pending_review: "pending",
  published: "active",
  cancelled: "closed",
  completed: "accepted",
  rejected: "rejected",
};

export const EVENT_MODERATION_TONE: Record<EventModerationStatus, StatusTone> = {
  pending: "pending",
  approved: "accepted",
  rejected: "rejected",
  flagged: "featured",
};
