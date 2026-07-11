"use client";

import { useTranslations } from "next-intl";
import type { ChipTone } from "@/components/kit";
import type { CampaignStatus } from "@/lib/api";

/**
 * Localized labels for the campaign allocation engine (spec §7.0). The backend
 * pairs every enum code with a vi `*_label`; for strict vi/en parity we map the
 * stable CODE through next-intl and fall back to the server label (then the raw
 * code) for any unknown value. Raw enum codes / coarse tokens are never shown.
 *
 * Enum + coarse-targeting labels live in the shared `advertising.campaign`
 * namespace so BOTH the partner builder and the university queue read the same
 * source (all message files merge into one tree — see src/messages/load.ts).
 */
export function useCampaignLabels() {
  const t = useTranslations("advertising.campaign");

  const label =
    (group: string) =>
    (code: string | null | undefined, serverLabel?: string | null): string => {
      if (!code) return serverLabel || "—";
      const key = `${group}.${code}`;
      if (t.has(key)) return t(key);
      return serverLabel || code;
    };

  return {
    status: label("enums.status"),
    objective: label("enums.objective"),
    pacing: label("enums.pacing"),
    surface: label("enums.surface"),
    location: label("targeting.locations"),
    major: label("targeting.majors"),
    career: label("targeting.careers"),
    workMode: label("targeting.workModes"),
    yearCohort: label("targeting.yearCohorts"),
  };
}

/** Campaign lifecycle status → content-palette chip tone (never color alone). */
export const CAMPAIGN_STATUS_TONE: Record<CampaignStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  approved: "info",
  active: "success",
  paused: "amber",
  ended: "neutral",
  rejected: "danger",
};

/** Objective → chip tone for the inventory/goal chip. */
export const CAMPAIGN_OBJECTIVE_TONE: Record<string, ChipTone> = {
  awareness: "sky",
  traffic: "indigo",
  applications: "emerald",
  event_registration: "teal",
};
