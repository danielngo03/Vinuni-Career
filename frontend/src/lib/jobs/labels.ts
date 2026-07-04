"use client";

import { useTranslations } from "next-intl";

/**
 * Localized enum labels for jobs. The backend pairs every enum code with a
 * `*_label`, but those labels are currently rendered server-side in Vietnamese
 * only, so for correct vi/en parity we map the stable enum CODE through
 * next-intl here and fall back to the server label (then the raw code) for any
 * unknown value. Raw enum codes are never shown to the user.
 */
export function useJobLabels() {
  const t = useTranslations("jobs.enums");

  const make =
    (group: string) =>
    (code: string | null | undefined, serverLabel?: string | null): string => {
      if (!code) return serverLabel || "—";
      const key = `${group}.${code}`;
      if (t.has(key)) return t(key);
      return serverLabel || code;
    };

  return {
    status: make("status"),
    moderation: make("moderation"),
    employmentType: make("employmentType"),
    locationType: make("locationType"),
    visibility: make("visibility"),
    screeningType: make("screeningType"),
  };
}

import type { JobStatus, ModerationStatus } from "@/lib/api";
import type { StatusTone } from "@/components/ui";

/** Map a job lifecycle status to a StatusBadge tone (color + label, not color alone). */
export const JOB_STATUS_TONE: Record<JobStatus, StatusTone> = {
  draft: "draft",
  pending_review: "pending",
  active: "active",
  rejected: "rejected",
  closed: "closed",
  expired: "closed",
};

export const MODERATION_TONE: Record<ModerationStatus, StatusTone> = {
  pending: "pending",
  approved: "accepted",
  rejected: "rejected",
  flagged: "featured",
};
